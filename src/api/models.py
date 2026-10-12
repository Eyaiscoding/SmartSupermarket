"""
Pydantic models for the B2G API.
================================
These serve as both the internal dataclass and the API response model,
enforcing the existing output contract without duplication.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional
from typing import Literal


class P2PTradeModel(BaseModel):
    counterparty_id: str
    building_type: str
    direction: Literal["buy", "sell"]
    quantity_kw: float = Field(ge=0)
    quantity_kwh: float = Field(ge=0)
    price_per_kwh: float
    wheeling_fee: float = Field(ge=0, description="EUR/kWh, not total fee")
    distance_km: float = Field(ge=0)
    saving_vs_grid: float = Field(ge=0, description="EUR for this timestep")


class TemperatureAlertModel(BaseModel):
    sensor: Literal["display_freezer_temp", "freezer_room_temp", "display_refrigerator_temp", "cold_room_temp"]
    value: float
    status: Literal["WARNING", "CRITICAL"]
    limit_low: float
    limit_high: float
    since: str


class TemperatureAlertHistoryModel(TemperatureAlertModel):
    timestamp: str


class MarketFields(BaseModel):
    neighbors: list[dict] | None = None
    demand_kw: float | None = None
    pv_power: float | None = None
    temperature_limits: dict[str, dict[str, float]] | None = None
    temperatures: dict[str, float] | None = None
    temperature_alerts: list[TemperatureAlertModel] | None = None
    temperature_status: Literal["OK", "WARNING", "CRITICAL"] | None = None
    p2p_import: float | None = Field(default=None, ge=0)
    p2p_export: float | None = Field(default=None, ge=0)
    p2p_trades: list[P2PTradeModel] | None = None
    p2p_savings: float | None = None
    cost: float | None = None
    revenue: float | None = None
    energy_price: float | None = None
    sell_price: float | None = None
    p2p_price: float | None = None


class NeighborModel(BaseModel):
    id: str
    type: str
    distance_km: float
    production_type: str
    production_types: list[str]


class NeighborSummaryModel(BaseModel):
    counterparty_id: str
    building_type: str
    bought_kwh: float
    sold_kwh: float
    money_saved: float


class OutputRecordModel(MarketFields):
    """Pydantic model matching the v1 output contract exactly."""

    timestamp: str
    coverage_ratio: float = Field(..., ge=0.0, le=1.0)
    coverage_status: str = Field(..., pattern=r"^(NORMAL|AT_RISK|CRITICAL)$")
    active_actions: list[str] = Field(default_factory=list)
    tier_1_protected: bool
    battery_soc: float
    grid_power: float
    p2p_energy: float
    anomaly_flag: bool
    anomaly_source: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "timestamp": "2025-06-01 00:00:00",
                    "coverage_ratio": 0.94,
                    "coverage_status": "AT_RISK",
                    "active_actions": ["hvac_soft_shed"],
                    "tier_1_protected": True,
                    "battery_soc": 62.3,
                    "grid_power": 12.4,
                    "p2p_energy": 0.0,
                    "anomaly_flag": False,
                    "anomaly_source": None,
                }
            ]
        }
    }


class LatestStateModel(MarketFields):
    """The current/latest state cached in Redis."""

    timestamp: str
    coverage_ratio: float
    coverage_status: str
    active_actions: list[str]
    tier_1_protected: bool
    battery_soc: float
    grid_power: float
    p2p_energy: float
    anomaly_flag: bool
    anomaly_source: Optional[str] = None


class TimeRangeQuery(BaseModel):
    """Query parameters for historical time range lookups."""

    start: str = Field(..., description="Start timestamp (ISO format)")
    end: str = Field(..., description="End timestamp (ISO format)")


class ScenarioRequest(BaseModel):
    """Request body for triggering a scenario replay."""

    scenario: str = Field(
        default="none",
        description="Stress scenario: none, forced_grid_outage, price_spike, sensor_corruption, all",
    )


class PipelineSummary(BaseModel):
    """Summary returned after a pipeline run completes."""

    label: str
    total_timesteps: int
    tier_1_breaches: int
    tier_1_protected: bool
    peak_shave_count: int
    valley_fill_count: int
    load_shift_count: int
    hard_shed_count: int
    total_peak_shaved_kwh: float
    ancillary_value_estimate: float
    coverage_ratio_mean: float
    coverage_ratio_min: float
    anomaly_count: int
