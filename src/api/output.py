"""
Layer 6 — Visualization & API Output
======================================
Produces the per-timestep output as a documented JSON stream and/or CSV
file matching the output contract defined in the project spec.

Output schema per record::

    {
      "timestamp": "...",
      "coverage_ratio": 0.94,
      "coverage_status": "AT_RISK",
      "active_actions": ["hvac_soft_shed"],
      "tier_1_protected": true,
      "battery_soc": 62.3,
      "grid_power": 12.4,
      "p2p_energy": 0,
      "anomaly_flag": false,
      "anomaly_source": null
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Sequence

import pandas as pd

from src.mpc.coordinator import COVERAGE_AT_RISK
from src.p2p.models import MARKET_OPTIONAL_FIELDS
from src.monitoring.temperature import TEMPERATURE_OPTIONAL_FIELDS


@dataclass
class OutputRecord:
    """One row of the output contract."""

    timestamp: str
    coverage_ratio: float
    coverage_status: str            # "NORMAL", "AT_RISK", "CRITICAL"
    active_actions: list[str]
    tier_1_protected: bool
    battery_soc: float
    grid_power: float
    p2p_energy: float
    anomaly_flag: bool
    anomaly_source: str | None
    p2p_import: float | None = None
    p2p_export: float | None = None
    p2p_trades: list[dict] | None = None
    p2p_savings: float | None = None
    cost: float | None = None
    revenue: float | None = None
    energy_price: float | None = None
    sell_price: float | None = None
    p2p_price: float | None = None
    temperatures: dict[str, float] | None = None
    temperature_alerts: list[dict] | None = None
    temperature_status: str | None = None
    temperature_limits: dict | None = None
    neighbors: list[dict] | None = None
    demand_kw: float | None = None
    pv_power: float | None = None

    def to_dict(self) -> dict:
        return {key: value for key, value in asdict(self).items()
                if key not in MARKET_OPTIONAL_FIELDS + TEMPERATURE_OPTIONAL_FIELDS or value is not None}


def compute_coverage_status(ratio: float) -> str:
    """Classify coverage ratio into a status string."""
    if ratio >= COVERAGE_AT_RISK:
        return "NORMAL"
    elif ratio >= 0.90:
        return "AT_RISK"
    else:
        return "CRITICAL"


class OutputWriter:
    """Collects ``OutputRecord`` objects and writes them to JSON / CSV."""

    def __init__(self) -> None:
        self.records: list[OutputRecord] = []

    def add(self, record: OutputRecord) -> None:
        self.records.append(record)

    def to_json(self, path: str | Path) -> None:
        """Write all records as a JSON array."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                [r.to_dict() for r in self.records],
                f,
                indent=2,
                ensure_ascii=False,
            )

    def to_csv(self, path: str | Path) -> None:
        """Write all records as a flat CSV."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame([r.to_dict() for r in self.records])
        # active_actions is a list — serialise for CSV.
        df["active_actions"] = df["active_actions"].apply(
            lambda x: ";".join(x) if x else ""
        )
        for column in ("p2p_trades", "temperatures", "temperature_alerts", "temperature_limits", "neighbors"):
            if column in df.columns:
                df[column] = df[column].apply(
                    lambda value: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else "")
        df.to_csv(path, index=False)

    def summary(self) -> dict:
        """Quick statistics over the collected records."""
        if not self.records:
            return {}
        ratios = [r.coverage_ratio for r in self.records]
        statuses = [r.coverage_status for r in self.records]
        anomalies = sum(1 for r in self.records if r.anomaly_flag)
        return {
            "total_records": len(self.records),
            "coverage_ratio_mean": round(sum(ratios) / len(ratios), 4),
            "coverage_ratio_min": round(min(ratios), 4),
            "status_normal_pct": round(
                statuses.count("NORMAL") / len(statuses) * 100, 1
            ),
            "status_at_risk_pct": round(
                statuses.count("AT_RISK") / len(statuses) * 100, 1
            ),
            "status_critical_pct": round(
                statuses.count("CRITICAL") / len(statuses) * 100, 1
            ),
            "anomaly_count": anomalies,
            "tier_1_always_protected": all(
                r.tier_1_protected for r in self.records
            ),
        }
