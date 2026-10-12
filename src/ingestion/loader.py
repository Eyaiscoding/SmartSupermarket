"""
Layer 1 — Data Ingestion
=========================
Loads dataset.csv, validates the schema and types, handles missing values,
and exposes a clean per-timestamp dataclass (TimestepState) for downstream
layers to consume.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd
from .schema import normalize_column, resolve_csv

# ── Expected schema ──────────────────────────────────────────────────────────
EXPECTED_COLUMNS: list[str] = [
    "timestamp",
    "occupancy",
    "temperature",
    "humidity",
    "solar_irradiance",
    "pv_voltage",
    "pv_current",
    "pv_power",
    "total_consumption",
    "display_freezer_power",
    "display_refrigerator_power",
    "cold_room_power",
    "freezer_room_power",
    "hvac_power",
    "lighting_power",
    "checkout_power",
    "it_power",
    "other_appliance_power",
    "battery_voltage",
    "battery_current",
    "battery_capacity",
    "battery_soc",
    "battery_power",
    "grid_power",
    "energy_price",
    "demand_response",
    "p2p_energy",
    "forecast_consumption",
    "forecast_pv",
    "anomaly_score",
]

TEMPERATURE_COLUMNS = ["display_freezer_temp", "freezer_room_temp",
                       "display_refrigerator_temp", "cold_room_temp"]


@dataclass
class TimestepState:
    """Immutable snapshot of the supermarket state at one 15-min interval."""

    timestamp: str
    occupancy: int
    temperature: float
    humidity: float
    solar_irradiance: float
    pv_voltage: float
    pv_current: float
    pv_power: float
    total_consumption: float
    display_freezer_power: float
    display_refrigerator_power: float
    cold_room_power: float
    freezer_room_power: float
    hvac_power: float
    lighting_power: float
    checkout_power: float
    it_power: float
    other_appliance_power: float
    battery_voltage: float
    battery_current: float
    battery_capacity: float
    battery_soc: float
    battery_power: float
    grid_power: float
    energy_price: float
    demand_response: int
    p2p_energy: float
    forecast_consumption: float
    forecast_pv: float
    anomaly_score: float
    display_freezer_temp: float | None = None
    freezer_room_temp: float | None = None
    display_refrigerator_temp: float | None = None
    cold_room_temp: float | None = None


# ── Loader ───────────────────────────────────────────────────────────────────

def _find_dataset(project_root: str | Path | None = None) -> Path:
    """Locate dataset.csv in the repo.  Checks data/ first, then repo root."""
    if project_root is None:
        project_root = Path(__file__).resolve().parents[2]
    project_root = Path(project_root)

    candidates = [
        project_root / "data" / "dataset.csv",
        project_root / "dataset.csv",
    ]
    for p in candidates:
        if p.is_file():
            return p
    raise FileNotFoundError(
        f"dataset.csv not found in {[str(c) for c in candidates]}"
    )


def load_dataset(
    path: str | Path | None = None,
    *,
    project_root: str | Path | None = None,
) -> pd.DataFrame:
    """Load, validate, and clean the supermarket dataset.

    Parameters
    ----------
    path : str | Path | None
        Explicit path to the CSV.  If *None*, auto-discovered via
        ``_find_dataset``.
    project_root : str | Path | None
        Root directory of the project (used only when *path* is None).

    Returns
    -------
    pd.DataFrame
        Validated DataFrame with ``timestamp`` parsed as datetime, sorted
        chronologically, and with an ``index`` column (if present) dropped.
    """
    if path is None:
        from src.p2p.config import enabled, supermarket_csv
        path = supermarket_csv() if enabled() or os.getenv("B2G_SUPERMARKET_CSV") else _find_dataset(project_root)
    path = resolve_csv(path)
    if not path.is_file():
        raise FileNotFoundError(f"Cannot open {path}")

    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [normalize_column(c) for c in df.columns]
    if df.columns.duplicated().any():
        raise ValueError("Duplicate columns after normalization")
    optional = [c for c in TEMPERATURE_COLUMNS if c in df.columns]

    # ── Schema validation ────────────────────────────────────────────────
    missing_cols = set(EXPECTED_COLUMNS) - set(df.columns)
    extra_cols = set(df.columns) - set(EXPECTED_COLUMNS) - set(TEMPERATURE_COLUMNS)
    if missing_cols:
        raise ValueError(f"Missing expected columns: {sorted(missing_cols)}")
    if extra_cols:
        # Warn but don't crash — extra cols may be benign.
        import warnings
        warnings.warn(f"Unexpected extra columns (ignored): {sorted(extra_cols)}")

    # Keep only expected columns in canonical order.
    df = df[EXPECTED_COLUMNS + optional].copy()
    for column in optional:
        # Never invent a safe temperature by copying another sensor reading.
        df[column] = pd.to_numeric(df[column], errors="coerce").replace([np.inf, -np.inf], np.nan)

    # ── Type coercions ───────────────────────────────────────────────────
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["occupancy"] = df["occupancy"].astype(int)
    df["demand_response"] = df["demand_response"].astype(int)

    # ── Missing-value handling ───────────────────────────────────────────
    # For numeric columns: forward-fill then back-fill (sensor continuity).
    numeric_cols = df[EXPECTED_COLUMNS].select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].ffill().bfill()

    # ── Sort by time ─────────────────────────────────────────────────────
    df = df.sort_values("timestamp").reset_index(drop=True)

    return df


def iter_timesteps(df: pd.DataFrame) -> Iterator[TimestepState]:
    """Yield one ``TimestepState`` per row of *df*."""
    for row in df.itertuples(index=False):
        yield TimestepState(
            timestamp=str(row.timestamp),
            occupancy=int(row.occupancy),
            temperature=float(row.temperature),
            humidity=float(row.humidity),
            solar_irradiance=float(row.solar_irradiance),
            pv_voltage=float(row.pv_voltage),
            pv_current=float(row.pv_current),
            pv_power=float(row.pv_power),
            total_consumption=float(row.total_consumption),
            display_freezer_power=float(row.display_freezer_power),
            display_refrigerator_power=float(row.display_refrigerator_power),
            cold_room_power=float(row.cold_room_power),
            freezer_room_power=float(row.freezer_room_power),
            hvac_power=float(row.hvac_power),
            lighting_power=float(row.lighting_power),
            checkout_power=float(row.checkout_power),
            it_power=float(row.it_power),
            other_appliance_power=float(row.other_appliance_power),
            battery_voltage=float(row.battery_voltage),
            battery_current=float(row.battery_current),
            battery_capacity=float(row.battery_capacity),
            battery_soc=float(row.battery_soc),
            battery_power=float(row.battery_power),
            grid_power=float(row.grid_power),
            energy_price=float(row.energy_price),
            demand_response=int(row.demand_response),
            p2p_energy=float(row.p2p_energy),
            forecast_consumption=float(row.forecast_consumption),
            forecast_pv=float(row.forecast_pv),
            anomaly_score=float(row.anomaly_score),
            **{key: (float(getattr(row, key)) if pd.notna(getattr(row, key, None)) else None)
               for key in TEMPERATURE_COLUMNS},
        )
