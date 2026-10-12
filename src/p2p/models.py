from dataclasses import asdict, dataclass
from typing import Literal

MARKET_OPTIONAL_FIELDS = (
    "neighbors",
    "demand_kw",
    "pv_power",
    "p2p_import",
    "p2p_export",
    "p2p_trades",
    "p2p_savings",
    "cost",
    "revenue",
    "energy_price",
    "sell_price",
    "p2p_price",
)


@dataclass(frozen=True)
class NeighborStep:
    building_id: str
    building_type: str
    distance_km: float
    consumption_kw: float
    production: float
    production_type: str
    energy_offer_kw: float


@dataclass(frozen=True)
class Trade:
    counterparty_id: str
    building_type: str
    direction: Literal["buy", "sell"]
    quantity_kw: float
    quantity_kwh: float
    price_per_kwh: float  # Commodity price before wheeling, EUR/kWh.
    wheeling_fee: float  # Rate in EUR/kWh, paid by the supermarket in either direction.
    distance_km: float
    saving_vs_grid: float  # Money for this step in EUR, not a price or power.


@dataclass(frozen=True)
class MarketResult:
    grid_power: float
    p2p_energy: float
    p2p_import: float
    p2p_export: float
    p2p_trades: list[Trade]
    p2p_savings: float
    cost: float
    revenue: float
    energy_price: float
    sell_price: float
    p2p_price: float

    def to_dict(self) -> dict:
        return asdict(self)
