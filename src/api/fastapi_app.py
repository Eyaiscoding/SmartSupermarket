"""
FastAPI Application -- B2G Smart Supermarket API
==================================================
Wraps the six-layer simulation pipeline in a production API with:

- REST endpoints: historical query by time range, latest state, scenario
  replay trigger.
- WebSocket endpoint streaming per-timestep output live as the pipeline runs.
- Pydantic models enforcing the existing output contract.

The pipeline continues to work in dual mode:
- ``csv`` mode (default, used by tests and scenario_runner.py) reads data
  directly from dataset.csv.
- ``mqtt`` mode subscribes to a Mosquitto broker for live/demo use.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is importable.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.models import (  # noqa: E402
    OutputRecordModel,
    LatestStateModel,
    ScenarioRequest,
    PipelineSummary,
)
from src.config import settings
from src.ingestion import load_dataset
from src.forecasting import Forecaster, AnomalyDetector, FlexibilityEstimator
from src.mpc import MPCCoordinator
from src.mpc.coordinator import COVERAGE_AT_RISK
from src.derms import DERMSDispatcher
from src.compliance import (
    ComplianceChecker,
    cold_chain_temps,
    tier_1_demand_kw,
)
from src.api import OutputWriter, OutputRecord
from src.api.output import compute_coverage_status
from src.api.models import NeighborModel, NeighborSummaryModel
from src.p2p.pipeline import NeighborMarket
from src.p2p.loader import load_neighbors
from src.p2p.matching import summarize
from src.monitoring.temperature import TemperatureMonitor
from src.api.models import TemperatureAlertHistoryModel

logger = logging.getLogger(__name__)

# -- Optional infrastructure (graceful degradation) ---------------------------

_timescale_store = None
_redis_cache = None


def _init_timescale():
    global _timescale_store
    try:
        from src.persistence import TimescaleStore
        _timescale_store = TimescaleStore()
        logger.info("TimescaleDB connected.")
    except Exception as exc:
        logger.warning("TimescaleDB unavailable: %s", exc)


def _init_redis():
    global _redis_cache
    try:
        from src.persistence import RedisCache
        _redis_cache = RedisCache()
        if not _redis_cache.available:
            _redis_cache = None
        else:
            logger.info("Redis connected.")
    except Exception as exc:
        logger.warning("Redis unavailable: %s", exc)


# -- FastAPI lifespan ---------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: connect to optional infrastructure. Shutdown: clean up."""
    _init_timescale()
    _init_redis()
    yield
    # cleanup if needed


app = FastAPI(
    title="B2G Smart Supermarket API",
    description=(
        "Building-to-Grid backend simulation engine API. "
        "Provides REST and WebSocket access to the six-layer energy "
        "management pipeline."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Active WebSocket connections ---------------------------------------------

_ws_clients: list[WebSocket] = []


# -- Pipeline runner (reuses scenario_runner logic) ---------------------------

SCENARIOS = {
    "forced_grid_outage": "inject_grid_outage",
    "price_spike": "inject_price_spike",
    "sensor_corruption": "inject_sensor_corruption",
}


def _run_pipeline_sync(
    label: str = "normal",
    scenario: str = "none",
    ws_broadcast: list | None = None,
) -> tuple[list[dict], PipelineSummary]:
    """Run the full pipeline synchronously. Returns (records, summary)."""

    df = load_dataset()
    market = NeighborMarket.for_run(df["timestamp"])
    temperature_monitor = TemperatureMonitor.from_env()

    # Inject stress scenario if requested.
    if scenario == "forced_grid_outage":
        df = df.copy()
        end = min(216, len(df))
        df.loc[200:end - 1, "grid_power"] = 0.0
    elif scenario == "price_spike":
        df = df.copy()
        end = min(508, len(df))
        df.loc[500:end - 1, "energy_price"] *= 5.0
    elif scenario == "sensor_corruption":
        df = df.copy()
        end = min(1004, len(df))
        df.loc[1000:end - 1, "temperature"] = 99.0

    n = len(df)

    # Train models.
    forecaster = Forecaster(n_estimators=100, max_depth=4)
    forecaster.train(df)
    _ = forecaster.predict(df)

    anomaly_det = AnomalyDetector()
    anomaly_det.train(df)
    anom_df = anomaly_det.detect(df)

    flex_est = FlexibilityEstimator()
    mpc = MPCCoordinator()
    dispatcher = DERMSDispatcher()
    checker = ComplianceChecker()

    battery_soc = float(df.iloc[0]["battery_soc"])
    battery_capacity = float(df.iloc[0]["battery_capacity"])

    records: list[dict] = []

    for i in range(n):
        row = df.iloc[i]

        budgets = flex_est.estimate(
            display_freezer_power=float(row["display_freezer_power"]),
            display_refrigerator_power=float(row["display_refrigerator_power"]),
            cold_room_power=float(row["cold_room_power"]),
            freezer_room_power=float(row["freezer_room_power"]),
            hvac_power=float(row["hvac_power"]),
            lighting_power=float(row["lighting_power"]),
            checkout_power=float(row["checkout_power"]),
            it_power=float(row["it_power"]),
            other_appliance_power=float(row["other_appliance_power"]),
            temperature=float(row["temperature"]),
        )

        horizon = min(4, n - i - 1)
        if horizon > 0:
            fwd = df.iloc[i + 1: i + 1 + horizon]
            fc_cons = fwd["forecast_consumption"].tolist()
            fc_pv = fwd["forecast_pv"].tolist()
            fc_price = fwd["energy_price"].tolist()
        else:
            fc_cons, fc_pv, fc_price = [], [], []

        action = mpc.decide(
            total_consumption=float(row["total_consumption"]),
            pv_power=float(row["pv_power"]),
            battery_soc=battery_soc,
            battery_capacity=battery_capacity,
            energy_price=float(row["energy_price"]),
            demand_response=int(row["demand_response"]),
            flex_budgets=budgets,
            forecast_consumption=fc_cons,
            forecast_pv=fc_pv,
            forecast_prices=fc_price,
        )

        dispatch = dispatcher.dispatch(
            action=action,
            total_consumption=float(row["total_consumption"]),
            pv_power=float(row["pv_power"]),
            battery_soc=battery_soc,
            battery_capacity=battery_capacity,
            current_grid_power=float(row["grid_power"]),
            current_p2p=float(row["p2p_energy"]),
        )
        battery_soc = dispatch.battery_soc_after
        market_output = market.settle(row["timestamp"], dispatch.grid_power,
                                      float(row["energy_price"])) if market else {}

        supply = float(row["pv_power"]) + max(dispatch.battery_power, 0.0)
        supply += max(dispatch.grid_power, 0.0)
        tier_1_ok = checker.check_step(
            action,
            timestamp=str(row["timestamp"]),
            tier_1_demand_kw=tier_1_demand_kw(row),
            supply_kw=supply,
            battery_soc=battery_soc,
            battery_power_kw=dispatch.battery_power,
            cold_temps=cold_chain_temps(row),
        )

        supply = float(row["pv_power"]) + max(dispatch.battery_power, 0.0)
        supply += max(dispatch.grid_power, 0.0)
        total_c = float(row["total_consumption"])
        coverage = supply / total_c if total_c > 0 else 1.0
        coverage = min(coverage, 1.0)

        anomaly_flag = bool(anom_df.iloc[i].get("anomaly_flag", False))
        anomaly_source = (
            anomaly_det.identify_source(anom_df.iloc[i])
            if anomaly_flag else None
        )

        rec = {
            "timestamp": str(row["timestamp"]),
            "coverage_ratio": round(coverage, 4),
            "coverage_status": compute_coverage_status(coverage),
            "active_actions": action.active_action_names,
            "tier_1_protected": tier_1_ok,
            "battery_soc": round(battery_soc, 2),
            "grid_power": round(dispatch.grid_power, 2),
            "p2p_energy": round(dispatch.p2p_energy, 2),
            "anomaly_flag": anomaly_flag,
            "anomaly_source": anomaly_source,
            **market_output,
            **({"demand_kw": max(float(row["total_consumption"]) - dispatch.shed_kw, 0),
                "pv_power": float(row["pv_power"])} if market else {}),
            **temperature_monitor.observe(row["timestamp"], row),
        }
        records.append(rec)

        # Persist to TimescaleDB if available.
        if _timescale_store:
            try:
                _timescale_store.write_record(rec, scenario_label=label)
            except Exception:
                pass

        # Update Redis cache with latest.
        if _redis_cache:
            _redis_cache.set_latest(rec)

        # Collect for WebSocket broadcast.
        if ws_broadcast is not None:
            ws_broadcast.append(rec)

    report = checker.report()
    anomaly_count = sum(1 for r in records if r["anomaly_flag"])
    ratios = [r["coverage_ratio"] for r in records]

    summary = PipelineSummary(
        label=label,
        total_timesteps=report.total_timesteps,
        tier_1_breaches=report.tier_1_breaches,
        tier_1_protected=report.tier_1_protected,
        peak_shave_count=report.peak_shave_count,
        valley_fill_count=report.valley_fill_count,
        load_shift_count=report.load_shift_count,
        hard_shed_count=report.hard_shed_count,
        total_peak_shaved_kwh=report.total_peak_shaved_kwh,
        ancillary_value_estimate=report.ancillary_value_estimate,
        coverage_ratio_mean=round(sum(ratios) / len(ratios), 4) if ratios else 0.0,
        coverage_ratio_min=round(min(ratios), 4) if ratios else 0.0,
        anomaly_count=anomaly_count,
    )

    return records, summary


# -- REST Endpoints -----------------------------------------------------------

@app.get("/api/v1/neighbors", response_model=list[NeighborModel])
async def get_neighbors():
    try:
        book = await asyncio.to_thread(load_neighbors)
        return book.neighbors
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=503, detail=f"Neighbour data unavailable: {exc}") from exc


@app.get("/api/v1/p2p/summary", response_model=list[NeighborSummaryModel])
async def get_p2p_summary(start: datetime, end: datetime, scenario: str = "normal"):
    def simulation_time(value: datetime) -> str:
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(sep=" ")
    first, last = simulation_time(start), simulation_time(end)
    if first > last:
        raise HTTPException(status_code=422, detail="start must not be after end")
    if not _timescale_store:
        raise HTTPException(status_code=503, detail="TimescaleDB not available.")
    rows = await asyncio.to_thread(_timescale_store.query_range, first, last, scenario_label=scenario)
    return summarize(rows)

@app.get("/api/v1/alerts/temperature", response_model=list[TemperatureAlertHistoryModel])
async def get_temperature_alerts(start: datetime, end: datetime, scenario: str = "normal"):
    def normalize(value: datetime) -> str:
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(sep=" ")
    first, last = normalize(start), normalize(end)
    if first > last:
        raise HTTPException(status_code=422, detail="start must not be after end")
    if not _timescale_store:
        raise HTTPException(status_code=503, detail="TimescaleDB not available.")
    rows = await asyncio.to_thread(_timescale_store.query_range, first, last, scenario_label=scenario)
    return [{"timestamp": row["timestamp"], **alert}
            for row in rows for alert in row.get("temperature_alerts") or []]


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "healthy",
        "timescaledb": _timescale_store is not None,
        "redis": _redis_cache is not None,
    }


@app.get("/api/v1/latest", response_model=LatestStateModel)
async def get_latest_state():
    """Return the latest pipeline state (from Redis if available, else
    TimescaleDB, else 404)."""
    # Try Redis first (low latency).
    if _redis_cache:
        cached = _redis_cache.get_latest()
        if cached:
            return LatestStateModel(**cached)

    # Fall back to TimescaleDB.
    if _timescale_store:
        row = _timescale_store.query_latest()
        if row:
            return LatestStateModel(**row)

    raise HTTPException(
        status_code=404,
        detail="No pipeline results available. Run a scenario first.",
    )


@app.get("/api/v1/history", response_model=list[OutputRecordModel])
async def get_history(
    start: str = Query(..., description="Start timestamp"),
    end: str = Query(..., description="End timestamp"),
    scenario: str = Query("normal", description="Scenario label"),
):
    """Query historical records by time range from TimescaleDB."""
    if not _timescale_store:
        raise HTTPException(
            status_code=503,
            detail="TimescaleDB not available.",
        )
    rows = _timescale_store.query_range(start, end, scenario_label=scenario)
    return [OutputRecordModel(**r) for r in rows]


@app.post("/api/v1/scenario", response_model=PipelineSummary)
async def run_scenario(request: ScenarioRequest):
    """Trigger a full pipeline replay with optional stress scenario."""
    scenario = request.scenario
    valid = {"none", "forced_grid_outage", "price_spike", "sensor_corruption"}
    if scenario not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scenario. Choose from: {sorted(valid)}",
        )

    label = scenario if scenario != "none" else "normal"

    # Run synchronously (pipeline is CPU-bound, ~5s).
    loop = asyncio.get_event_loop()
    records, summary = await loop.run_in_executor(
        None, lambda: _run_pipeline_sync(label=label, scenario=scenario)
    )

    return summary


# -- WebSocket Endpoint -------------------------------------------------------

@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """Stream per-timestep output records live as the pipeline runs.

    Client sends a JSON message to start: ``{"scenario": "none"}``
    Server streams one JSON record per timestep, then a final summary.
    """
    await websocket.accept()
    _ws_clients.append(websocket)

    try:
        # Wait for client to send a start command.
        data = await websocket.receive_json()
        scenario = data.get("scenario", "none")
        label = scenario if scenario != "none" else "normal"

        ws_records: list[dict] = []

        # Run pipeline in executor (CPU-bound).
        loop = asyncio.get_event_loop()
        records, summary = await loop.run_in_executor(
            None,
            lambda: _run_pipeline_sync(
                label=label, scenario=scenario, ws_broadcast=ws_records
            ),
        )

        # Stream all records to the client.
        for rec in records:
            await websocket.send_json(rec)

        # Send summary as final message.
        await websocket.send_json({
            "type": "summary",
            "data": summary.model_dump(),
        })

    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


# -- Main (uvicorn) -----------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.fastapi_app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
