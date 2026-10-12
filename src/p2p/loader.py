"""Strict, indexed neighbour time series with conservative surplus clipping."""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from src.ingestion.schema import normalize_column, resolve_csv

from .config import neighbors_csv
from .models import NeighborStep

REQUIRED = {
    "timestamp",
    "building_id",
    "building_type",
    "distance_km",
    "consumption_kw",
    "production",
    "production_type",
    "energy_offer_kw",
}


class NeighborBook:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._steps: dict[pd.Timestamp, list[NeighborStep]] = {}
        self.neighbors: list[dict] = []
        for timestamp, group in frame.groupby("timestamp", sort=True):
            self._steps[timestamp] = [
                NeighborStep(**row)
                for row in group.drop(columns="timestamp").to_dict("records")
            ]
        for bid, group in frame.groupby("building_id", sort=True):
            production_types = sorted(group.production_type.unique().tolist())
            technology = [
                p
                for p in production_types
                if normalize_column(p) not in {"aucune", "none"}
            ]
            self.neighbors.append(
                {
                    "id": bid,
                    "type": group.iloc[0].building_type,
                    "distance_km": float(group.iloc[0].distance_km),
                    "production_type": ", ".join(technology)
                    if technology
                    else production_types[0],
                    "production_types": production_types,
                }
            )

    def at(self, timestamp: object) -> list[NeighborStep]:
        timestamp = pd.Timestamp(timestamp)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("UTC").tz_localize(None)
        if timestamp not in self._steps:
            raise ValueError(f"No neighbours aligned with timestamp {timestamp}")
        return self._steps[timestamp]


def load_neighbors(
    path: str | Path | None = None, *, expected_timestamps=None
) -> NeighborBook:
    frame = pd.read_csv(
        resolve_csv(path if path is not None else neighbors_csv()),
        encoding="utf-8-sig",
        dtype={"building_id": str},
    )
    frame.columns = [normalize_column(c) for c in frame.columns]
    frame = frame.rename(columns={"energy_production_kw": "production"})
    if frame.columns.duplicated().any():
        raise ValueError("Ambiguous duplicate neighbour columns after normalization")
    if not REQUIRED.issubset(frame.columns):
        raise ValueError(
            f"Missing neighbour columns: {sorted(REQUIRED - set(frame.columns))}"
        )
    frame = frame[sorted(REQUIRED)].copy()
    if frame.empty or frame.isna().any().any():
        raise ValueError("Neighbour dataset is empty or contains missing values")
    for key in ("building_id", "building_type", "production_type"):
        frame[key] = frame[key].astype(str).str.strip()
        if frame[key].eq("").any():
            raise ValueError(f"Missing neighbour {key}")
    for key in ("distance_km", "consumption_kw", "production", "energy_offer_kw"):
        frame[key] = pd.to_numeric(frame[key], errors="raise")
        if not np.isfinite(frame[key]).all() or frame[key].lt(0).any():
            raise ValueError(f"Invalid non-negative neighbour measure: {key}")
    frame.timestamp = pd.to_datetime(
        frame.timestamp, errors="raise", utc=True
    ).dt.tz_localize(None)
    if (
        frame.timestamp.isna().any()
        or not frame.timestamp.eq(frame.timestamp.dt.floor("15min")).all()
    ):
        raise ValueError("Neighbour timestamps must lie on 15-minute boundaries")
    if frame.duplicated(["timestamp", "building_id"]).any():
        raise ValueError("Duplicate neighbour timestamp/building_id")
    times = pd.DatetimeIndex(sorted(frame.timestamp.unique()))
    if (
        len(times) > 1
        and not (times[1:] - times[:-1] == pd.Timedelta(minutes=15)).all()
    ):
        raise ValueError("Missing 15-minute timestamps in neighbour dataset")
    expected = (
        set(times)
        if expected_timestamps is None
        else set(pd.to_datetime(list(expected_timestamps), utc=True).tz_localize(None))
    )
    for bid, group in frame.groupby("building_id"):
        if set(group.timestamp) != set(times) or not expected.issubset(
            set(group.timestamp)
        ):
            raise ValueError(f"Timestamp alignment failure for neighbour {bid}")
        if group.building_type.nunique() != 1 or group.distance_km.nunique() != 1:
            raise ValueError(f"Inconsistent static metadata for neighbour {bid}")
    surplus = (frame.production - frame.consumption_kw).clip(lower=0)
    excess = frame.energy_offer_kw > surplus + 1e-9
    if excess.any():
        warnings.warn(
            f"Capped {int(excess.sum())} neighbour offers to physical surplus",
            stacklevel=2,
        )
    frame.energy_offer_kw = np.minimum(frame.energy_offer_kw, surplus)
    return NeighborBook(frame.sort_values(["timestamp", "building_id"]))
