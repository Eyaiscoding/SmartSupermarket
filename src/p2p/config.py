"""Placeholder market parameters until real tariffs and transport fees exist."""

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def enabled() -> bool:
    return os.getenv("B2G_P2P_ENABLED", "false").strip().lower() in {"true", "1", "yes"}


def supermarket_csv() -> Path:
    # File roles are intentionally based on inspected schemas, not misleading filenames.
    return Path(
        os.getenv("B2G_SUPERMARKET_CSV", str(ROOT / "data1/dataset_modified.csv"))
    )


def neighbors_csv() -> Path:
    return Path(
        os.getenv(
            "B2G_NEIGHBORS_CSV",
            str(ROOT / "data1/smart_supermarket_neighbor_buildings_4months_15min1.csv"),
        )
    )


@dataclass(frozen=True)
class MarketConfig:
    # All prices are placeholders in EUR/kWh. BUY_PRICE always comes from each dataset row.
    sell_price: float = 0.08
    wheeling_base_fee: float = 0.005
    wheeling_per_km: float = 0.02
    step_hours: float = 0.25
    production_type_price_factor: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        values = [
            self.sell_price,
            self.wheeling_base_fee,
            self.wheeling_per_km,
            self.step_hours,
            *self.production_type_price_factor.values(),
        ]
        if any(not math.isfinite(v) for v in values):
            raise ValueError("Market parameters must be finite")
        if (
            min(self.wheeling_base_fee, self.wheeling_per_km) < 0
            or self.step_hours <= 0
        ):
            raise ValueError("Fees must be non-negative and step_hours positive")
        if any(v <= 0 for v in self.production_type_price_factor.values()):
            raise ValueError("Production price factors must be positive")

    @classmethod
    def from_env(cls) -> "MarketConfig":
        factors = json.loads(os.getenv("B2G_PRODUCTION_TYPE_PRICE_FACTOR", "{}"))
        if not isinstance(factors, dict):
            raise TypeError("B2G_PRODUCTION_TYPE_PRICE_FACTOR must be a JSON object")
        return cls(
            sell_price=float(os.getenv("B2G_SELL_PRICE", "0.08")),
            wheeling_base_fee=float(os.getenv("B2G_WHEELING_BASE_FEE", "0.005")),
            wheeling_per_km=float(os.getenv("B2G_WHEELING_PER_KM", "0.02")),
            step_hours=float(os.getenv("B2G_STEP_HOURS", "0.25")),
            production_type_price_factor={str(k): float(v) for k, v in factors.items()},
        )
