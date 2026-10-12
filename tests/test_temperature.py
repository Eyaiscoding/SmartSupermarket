"""Temperature state, transport and dispatch-isolation regression tests."""

import json
from unittest.mock import Mock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.monitoring.temperature import SENSORS, SensorLimits, TemperatureMonitor


def readings(**overrides):
    return {**dict(zip(SENSORS, (-20.0, -24.0, 3.0, 2.0), strict=True)), **overrides}


def observe(monitor, minute=0, **overrides):
    return monitor.observe(f"2025-06-01 00:{minute:02d}:00", readings(**overrides))


def test_in_band_inclusive_boundaries():
    result = observe(
        TemperatureMonitor(),
        display_freezer_temp=-18,
        freezer_room_temp=-30,
        display_refrigerator_temp=0,
        cold_room_temp=5,
    )
    assert result["temperature_status"] == "OK"
    assert result["temperature_alerts"] == []
    assert len(result["temperatures"]) == 4


@pytest.mark.parametrize("value", [-31, -17])
def test_excursion_persistence_and_recovery(value):
    monitor = TemperatureMonitor()
    first = observe(monitor, display_freezer_temp=value)
    assert first["temperature_status"] == "WARNING"
    second = observe(monitor, 15, display_freezer_temp=value)
    assert second["temperature_status"] == "CRITICAL"
    alert = second["temperature_alerts"][0]
    assert alert == {
        "sensor": "display_freezer_temp",
        "value": value,
        "status": "CRITICAL",
        "limit_low": -30,
        "limit_high": -18,
        "since": "2025-06-01 00:00:00",
    }
    assert observe(monitor, 30)["temperature_status"] == "OK"
    reset = observe(monitor, 45, display_freezer_temp=value)
    assert reset["temperature_status"] == "WARNING"
    assert reset["temperature_alerts"][0]["since"] == "2025-06-01 00:45:00"


@pytest.mark.parametrize(
    "sensor,value",
    [(SENSORS[0], -11.9), (SENSORS[1], -11), (SENSORS[2], 8.1), (SENSORS[3], 9)],
)
def test_hard_limit_immediate_and_overall_worst(sensor, value):
    result = observe(TemperatureMonitor(), **{sensor: value})
    assert result["temperature_status"] == "CRITICAL"
    assert result["temperature_alerts"][0]["status"] == "CRITICAL"


def test_hard_limit_equality_is_warning_and_counters_are_per_sensor():
    monitor = TemperatureMonitor()
    assert observe(monitor, cold_room_temp=8)["temperature_status"] == "WARNING"
    result = observe(monitor, 15, display_freezer_temp=-17)
    assert result["temperature_status"] == "WARNING"
    assert result["temperature_alerts"][0]["sensor"] == "display_freezer_temp"


@pytest.mark.parametrize("missing", [None, float("nan"), float("inf"), "invalid"])
def test_missing_readings_do_not_claim_ok_or_continue_excursion(missing):
    monitor = TemperatureMonitor()
    observe(monitor, display_freezer_temp=-17)
    result = monitor.observe("2025-06-01 00:15:00", {"display_freezer_temp": missing})
    assert result == {}
    assert (
        observe(monitor, 30, display_freezer_temp=-17)["temperature_status"]
        == "WARNING"
    )


def test_missing_column_partial_data_and_time_gap():
    monitor = TemperatureMonitor()
    assert monitor.observe("2025-06-01 00:00:00", {}) == {}
    partial = monitor.observe("2025-06-01 00:15:00", {"cold_room_temp": 6})
    assert partial["temperatures"] == {"cold_room_temp": 6}
    assert (
        monitor.observe("2025-06-01 00:45:00", {"cold_room_temp": 6})[
            "temperature_status"
        ]
        == "WARNING"
    )
    with pytest.raises(ValueError, match="chronological"):
        monitor.observe("2025-06-01 00:45:00", {})


def test_env_configuration(monkeypatch):
    monkeypatch.setenv("B2G_TEMP_COLD_ROOM_LOW", "1")
    monkeypatch.setenv("B2G_TEMP_COLD_ROOM_HIGH", "4")
    monkeypatch.setenv("B2G_TEMP_COLD_ROOM_HARD_LIMIT", "7")
    monkeypatch.setenv("B2G_TEMP_CRITICAL_AFTER_STEPS", "3")
    monitor = TemperatureMonitor.from_env()
    assert monitor.limits["cold_room_temp"] == SensorLimits(1, 4, 7)
    assert observe(monitor, cold_room_temp=5)["temperature_status"] == "WARNING"
    assert observe(monitor, 15, cold_room_temp=5)["temperature_status"] == "WARNING"
    assert observe(monitor, 30, cold_room_temp=5)["temperature_status"] == "CRITICAL"
    with pytest.raises(ValueError):
        SensorLimits(5, 0, 8)
    with pytest.raises(ValueError):
        SensorLimits(0, 5, float("nan"))
    with pytest.raises(ValueError):
        TemperatureMonitor(critical_after_steps=0)


def record():
    return {
        "timestamp": "2025-06-01 00:00:00",
        "coverage_ratio": 1.0,
        "coverage_status": "NORMAL",
        "active_actions": [],
        "tier_1_protected": True,
        "battery_soc": 60.0,
        "grid_power": 10.0,
        "p2p_energy": 0.0,
        "anomaly_flag": False,
        "anomaly_source": None,
        **observe(TemperatureMonitor(), cold_room_temp=9),
    }


def test_json_csv_redis_and_contract_roundtrip(tmp_path):
    from src.api.models import LatestStateModel, OutputRecordModel
    from src.api.output import OutputRecord, OutputWriter
    from src.persistence.redis_cache import RedisCache

    data = record()
    for model in (LatestStateModel, OutputRecordModel):
        assert model(**data).temperature_status == "CRITICAL"
    writer = OutputWriter()
    writer.add(OutputRecord(**data))
    writer.to_json(tmp_path / "records.json")
    writer.to_csv(tmp_path / "records.csv")
    assert (
        json.loads((tmp_path / "records.json").read_text(encoding="utf-8"))[0] == data
    )
    row = pd.read_csv(tmp_path / "records.csv").iloc[0]
    for field in ("temperatures", "temperature_alerts"):
        assert json.loads(row[field]) == data[field]
    cache = RedisCache.__new__(RedisCache)
    cache._client = Mock()
    cache.set_latest(data)
    cache._client.get.return_value = cache._client.set.call_args.args[1]
    assert cache.get_latest() == data


def test_persistence_api_history_and_websocket(tmp_path, monkeypatch):
    import src.api.fastapi_app as api
    import src.persistence.timescale as ts

    monkeypatch.setattr(ts, "_engine", None)
    monkeypatch.setattr(ts, "_SessionLocal", None)
    store = ts.TimescaleStore(f"sqlite:///{tmp_path / 'temperatures.db'}")
    monkeypatch.setattr(api, "_timescale_store", store)
    monkeypatch.setattr(api, "_redis_cache", None)
    data = record()
    store.write_record(data)
    store.write_records_bulk([data])
    assert store.query_latest() == data
    store.write_record(
        {
            **data,
            "timestamp": "2025-06-01 00:15:00",
            "temperature_alerts": [],
            "temperature_status": "OK",
        }
    )
    store.write_record(data, scenario_label="other")
    client = TestClient(api.app)
    params = {"start": "2025-06-01T00:00:00Z", "end": "2025-06-01T00:15:00Z"}
    assert client.get("/api/v1/latest").json()["temperature_status"] == "OK"
    history = client.get("/api/v1/alerts/temperature", params=params)
    assert history.status_code == 200
    assert history.json() == [
        {"timestamp": data["timestamp"], **data["temperature_alerts"][0]}
    ]
    assert (
        client.get(
            "/api/v1/alerts/temperature", params={**params, "scenario": "absent"}
        ).json()
        == []
    )
    assert (
        client.get(
            "/api/v1/alerts/temperature", params={**params, "end": "2025-05-01"}
        ).status_code
        == 422
    )
    rows = client.get(
        "/api/v1/history", params={"start": data["timestamp"], "end": data["timestamp"]}
    ).json()
    assert rows[0]["temperatures"] == data["temperatures"]
    summary = Mock()
    summary.model_dump.return_value = {}
    monkeypatch.setattr(api, "_run_pipeline_sync", lambda **kwargs: ([data], summary))
    with client.websocket_connect("/ws/stream") as ws:
        ws.send_json({"scenario": "none"})
        assert ws.receive_json() == data
        assert ws.receive_json()["type"] == "summary"
    monkeypatch.setattr(api, "_timescale_store", None)
    assert client.get("/api/v1/alerts/temperature", params=params).status_code == 503
    ts._engine.dispose()


def test_pipeline_temperatures_do_not_change_dispatch_or_tier1(monkeypatch, tmp_path):
    import src.api.fastapi_app as api
    from scenario_runner import run_pipeline
    from src.ingestion import load_dataset

    monkeypatch.setenv("B2G_P2P_ENABLED", "false")
    monkeypatch.delenv("B2G_SUPERMARKET_CSV", raising=False)
    data = load_dataset().head(48)
    monkeypatch.setattr(api, "load_dataset", lambda: data.copy())
    monkeypatch.setattr(api, "_timescale_store", None)
    monkeypatch.setattr(api, "_redis_cache", None)
    baseline, _ = api._run_pipeline_sync()
    data["cold_room_temp"] = 9.0
    actual, _ = api._run_pipeline_sync()
    for old, new in zip(baseline, actual, strict=True):
        assert "temperature_status" not in old
        assert new["temperature_status"] == "CRITICAL"
        assert {key: new[key] for key in old} == old
    result = run_pipeline(data, output_dir=tmp_path)
    assert result["compliance_report"].tier_1_protected
    exported = json.loads((tmp_path / "output_normal.json").read_text(encoding="utf-8"))
    assert all(row["temperature_status"] == "CRITICAL" for row in exported)
