"""Phase A unit and integration checks; no changes to historical test cases."""

import json
from unittest.mock import Mock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.ingestion import load_dataset
from src.ingestion.loader import iter_timesteps
from src.p2p.config import MarketConfig, neighbors_csv, supermarket_csv
from src.p2p.loader import load_neighbors
from src.p2p.matching import match_neighbors, summarize
from src.p2p.models import NeighborStep
from src.p2p.pipeline import NeighborMarket


def neighbor(bid="B01", distance=0.5, offer=10.0, consumption=5.0, production=15.0):
    return NeighborStep(
        bid, "École", distance, consumption, production, "Solaire PV", offer
    )


def frame():
    return pd.DataFrame(
        [
            {
                "timestamp": f"2025-06-01 00:{minute:02d}:00",
                "building_id": bid,
                "building_type": "École",
                "distance_Km": 0.5,
                "consumption_kw": 5,
                "energy_production_kw": 15.0,
                "production_type": "Solaire PV",
                "energy_offer_kw": 10.0,
            }
            for minute in (0, 15)
            for bid in ("B01", "B02")
        ]
    )


def test_loader_unicode_and_case(tmp_path):
    path = tmp_path / "voisins_modifié.csv"
    data = frame().rename(columns={"distance_Km": " Distance_Km "})
    data.to_csv(path, index=False, encoding="utf-8-sig")
    book = load_neighbors(
        path, expected_timestamps=["2025-06-01 00:00:00", "2025-06-01 00:15:00"]
    )
    assert len(book.at("2025-06-01T00:00:00Z")) == 2
    assert book.neighbors[0]["type"] == "École"
    assert book.neighbors[0]["distance_km"] == 0.5


@pytest.mark.parametrize(
    "case", ["missing", "negative", "duplicate", "alignment", "off_grid", "metadata"]
)
def test_loader_rejects_invalid_data(tmp_path, case):
    data = frame()
    if case == "missing":
        data.loc[0, "energy_offer_kw"] = float("nan")
    elif case == "negative":
        data.loc[0, "distance_Km"] = -1
    elif case == "duplicate":
        data = pd.concat([data, data.iloc[:1]])
    elif case == "alignment":
        data = data.iloc[:-1]
    elif case == "off_grid":
        data.loc[0, "timestamp"] = "2025-06-01 00:01:00"
    elif case == "metadata":
        data.loc[2, "distance_Km"] = 9
    path = tmp_path / "bad.csv"
    data.to_csv(path, index=False)
    with pytest.raises(ValueError):
        load_neighbors(path)


def test_loader_checks_supermarket_alignment(tmp_path):
    path = tmp_path / "neighbors.csv"
    frame().to_csv(path, index=False)
    with pytest.raises(ValueError, match="alignment"):
        load_neighbors(path, expected_timestamps=["2025-06-01 00:30:00"])


def test_loader_caps_incoherent_offer(tmp_path):
    data = frame()
    data.loc[0, "energy_offer_kw"] = 10.1
    path = tmp_path / "neighbors.csv"
    data.to_csv(path, index=False)
    with pytest.warns(UserWarning, match="Capped 1"):
        book = load_neighbors(path)
    assert book.at("2025-06-01 00:00:00")[0].energy_offer_kw == 10


def test_optional_temperatures_and_legacy_default(monkeypatch, tmp_path):
    monkeypatch.delenv("B2G_P2P_ENABLED", raising=False)
    monkeypatch.delenv("B2G_SUPERMARKET_CSV", raising=False)
    legacy = load_dataset()
    assert legacy.shape == (11712, 30)
    assert next(iter_timesteps(legacy)).display_freezer_temp is None
    data = legacy.head(2).copy()
    data["display_freezer_temp"] = [-20.0, float("nan")]
    path = tmp_path / "dataset_modifié.csv"
    data.to_csv(path, index=False)
    monkeypatch.setenv("B2G_SUPERMARKET_CSV", str(path))
    extended = load_dataset()
    assert pd.isna(extended.iloc[1].display_freezer_temp)
    assert list(iter_timesteps(extended))[1].display_freezer_temp is None
    assert next(iter_timesteps(extended)).display_freezer_temp == -20.0


def test_inspected_files_and_alias(monkeypatch):
    monkeypatch.setenv("B2G_P2P_ENABLED", "true")
    data = load_dataset()
    assert len(data.columns) == 34
    assert supermarket_csv().name == "dataset_modified.csv"
    with pytest.warns(UserWarning, match="Capped 1320"):
        book = load_neighbors(expected_timestamps=data.timestamp)
    assert len(book.neighbors) == 6
    assert neighbors_csv().name.startswith("smart_supermarket_neighbor")
    assert book.neighbors[0]["production_types"] == ["Aucune", "Solaire PV"]


def test_import_greedy_order_remainder_and_accounting():
    sellers = [
        neighbor("far", 1, 10),
        neighbor("small", 0.5, 2),
        neighbor("large", 0.5, 6),
    ]
    result = match_neighbors(22, 0.2, sellers)
    assert [t.counterparty_id for t in result.p2p_trades] == ["large", "small", "far"]
    assert [t.quantity_kw for t in result.p2p_trades] == [6, 2, 10]
    assert result.grid_power == 4
    assert result.p2p_import == 18 and result.p2p_export == 0
    assert result.cost == pytest.approx(
        4 * 0.25 * 0.2 + 8 * 0.25 * 0.155 + 10 * 0.25 * 0.165
    )
    assert result.p2p_savings == pytest.approx(22 * 0.25 * 0.2 - result.cost)
    assert result.revenue == 0


def test_partial_offer_and_deterministic_tie():
    a, b = neighbor("A"), neighbor("B")
    first = match_neighbors(3, 0.2, [b, a])
    second = match_neighbors(3, 0.2, [a, b])
    assert first == second
    assert first.p2p_trades[0].counterparty_id == "A"
    assert first.p2p_trades[0].quantity_kwh == 0.75
    assert first.grid_power == 0


def test_export_matches_nearest_and_preserves_supply():
    buyers = [neighbor("far", 2, 0, 10, 0), neighbor("near", 0.5, 0, 5, 0)]
    result = match_neighbors(-12, 0.2, buyers)
    assert [t.counterparty_id for t in result.p2p_trades] == ["near", "far"]
    assert [t.quantity_kw for t in result.p2p_trades] == [5, 7]
    assert result.p2p_energy == -12 and result.p2p_import == 0
    assert result.revenue == pytest.approx(5 * 0.25 * 0.125 + 7 * 0.25 * 0.095)
    assert result.p2p_savings == pytest.approx(result.revenue - 12 * 0.25 * 0.08)
    assert result.cost == 0


@pytest.mark.parametrize("power", [-200, -10, 0, 10, 200])
def test_balance_identity_and_one_direction(power):
    result = match_neighbors(
        power, 0.2, [neighbor("seller"), neighbor("buyer", 0.5, 0, 10, 0)]
    )
    assert result.grid_power + result.p2p_import - result.p2p_export == pytest.approx(
        power
    )
    assert not (result.p2p_import and result.p2p_export)
    assert all(t.quantity_kw > 0 for t in result.p2p_trades)
    assert result == match_neighbors(
        power, 0.2, [neighbor("seller"), neighbor("buyer", 0.5, 0, 10, 0)]
    )


def test_rejects_equal_price_high_fees_and_handles_negative_tariff():
    config = MarketConfig(sell_price=0.2, wheeling_base_fee=0, wheeling_per_km=0)
    assert not match_neighbors(10, 0.2, [neighbor()], config).p2p_trades
    assert not match_neighbors(
        -10, 0.2, [neighbor(offer=0, consumption=10, production=0)], config
    ).p2p_trades
    assert not match_neighbors(10, 0.2, [neighbor(distance=100)]).p2p_trades
    assert match_neighbors(10, -0.1, [neighbor()]).cost == pytest.approx(-0.25)


def test_env_config_and_factor(monkeypatch):
    monkeypatch.setenv("B2G_SELL_PRICE", ".06")
    monkeypatch.setenv("B2G_PRODUCTION_TYPE_PRICE_FACTOR", '{"Solaire PV": 2}')
    config = MarketConfig.from_env()
    assert config.sell_price == 0.06
    assert not match_neighbors(10, 0.2, [neighbor()], config).p2p_trades
    with pytest.raises(ValueError):
        MarketConfig(wheeling_per_km=-1)
    with pytest.raises(ValueError):
        match_neighbors(float("nan"), 0.2, [])
    with pytest.raises(ValueError):
        match_neighbors(1, 0.2, [neighbor(), neighbor()])


def test_disabled_flag_never_reads_new_data(monkeypatch):
    monkeypatch.setenv("B2G_P2P_ENABLED", "false")
    monkeypatch.setenv("B2G_NEIGHBORS_CSV", "does-not-exist.csv")
    assert NeighborMarket.for_run([]) is None


def output_record():
    return {
        "timestamp": "2025-06-01 00:00:00",
        "coverage_ratio": 0.97,
        "coverage_status": "NORMAL",
        "active_actions": [],
        "tier_1_protected": True,
        "battery_soc": 60.0,
        "grid_power": 10.0,
        "p2p_energy": 0.0,
        "anomaly_flag": False,
        "anomaly_source": None,
        **match_neighbors(10, 0.2, [neighbor()]).to_dict(),
    }


def test_contract_json_csv_redis_and_summary(tmp_path):
    from src.api.models import LatestStateModel, OutputRecordModel
    from src.api.output import OutputRecord, OutputWriter
    from src.persistence.redis_cache import RedisCache

    record = output_record()
    assert LatestStateModel(**record).p2p_trades[0].direction == "buy"
    assert OutputRecordModel(**record).cost == record["cost"]
    writer = OutputWriter()
    writer.add(OutputRecord(**record))
    writer.to_json(tmp_path / "out.json")
    writer.to_csv(tmp_path / "out.csv")
    assert json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))[0] == record
    assert (
        json.loads(pd.read_csv(tmp_path / "out.csv").iloc[0].p2p_trades)
        == record["p2p_trades"]
    )
    cache = RedisCache.__new__(RedisCache)
    cache._client = Mock()
    cache.set_latest(record)
    payload = cache._client.set.call_args.args[1]
    cache._client.get.return_value = payload
    assert cache.get_latest() == record
    assert summarize([record])[0]["bought_kwh"] == 2.5


@pytest.fixture
def store(tmp_path, monkeypatch):
    import src.persistence.timescale as ts

    monkeypatch.setattr(ts, "_engine", None)
    monkeypatch.setattr(ts, "_SessionLocal", None)
    result = ts.TimescaleStore(f"sqlite:///{tmp_path / 'market.db'}")
    yield result
    ts._engine.dispose()


def test_persistence_roundtrip_upsert_and_legacy(store):
    record = output_record()
    store.write_record(record)
    store.write_records_bulk([record])
    assert store.query_latest() == record
    assert store.query_all() == [record]
    legacy = {
        k: v
        for k, v in record.items()
        if k not in match_neighbors(10, 0.2, []).to_dict()
    }
    legacy.update(grid_power=10.0, p2p_energy=0.0)
    store.write_record(legacy, scenario_label="legacy")
    assert "p2p_trades" not in store.query_latest("legacy")


def test_new_api_routes_and_history(store, monkeypatch):
    import src.api.fastapi_app as api

    monkeypatch.setattr(api, "_timescale_store", store)
    monkeypatch.setattr(api, "_redis_cache", None)
    record = output_record()
    store.write_record(record)
    client = TestClient(api.app)
    assert client.get("/api/v1/latest").json()["p2p_trades"] == record["p2p_trades"]
    params = {"start": "2025-06-01 00:00:00", "end": "2025-06-01 00:15:00"}
    assert (
        client.get("/api/v1/history", params=params).json()[0]["cost"] == record["cost"]
    )
    assert client.get("/api/v1/p2p/summary", params=params).json() == summarize(
        [record]
    )
    assert (
        client.get(
            "/api/v1/p2p/summary",
            params={"start": params["end"], "end": params["start"]},
        ).status_code
        == 422
    )
    with pytest.warns(UserWarning, match="Capped"):
        response = client.get("/api/v1/neighbors")
    assert response.status_code == 200 and len(response.json()) == 6
    monkeypatch.setattr(api, "_timescale_store", None)
    assert client.get("/api/v1/p2p/summary", params=params).status_code == 503


def test_api_pipeline_preserves_mpc_and_tier1(monkeypatch):
    import src.api.fastapi_app as api

    # Same source rows, same MPC inputs; only settlement is enabled on the second run.
    monkeypatch.setenv("B2G_P2P_ENABLED", "false")
    data = load_dataset().head(96)
    monkeypatch.setattr(api, "load_dataset", lambda: data.copy())
    monkeypatch.setattr(api, "_timescale_store", None)
    monkeypatch.setattr(api, "_redis_cache", None)
    baseline, _ = api._run_pipeline_sync()
    monkeypatch.setenv("B2G_P2P_ENABLED", "true")
    with pytest.warns(UserWarning, match="Capped"):
        actual, summary = api._run_pipeline_sync()
    assert summary.tier_1_protected
    for old, new in zip(baseline, actual):
        for key in (
            "active_actions",
            "tier_1_protected",
            "coverage_ratio",
            "battery_soc",
        ):
            assert old[key] == new[key]
        assert new["grid_power"] + new["p2p_energy"] == pytest.approx(
            old["grid_power"], abs=0.0051
        )
    assert any(r["p2p_trades"] for r in actual)


def test_websocket_retains_optional_payload(monkeypatch):
    import src.api.fastapi_app as api

    record = output_record()
    summary = api.PipelineSummary(
        label="normal",
        total_timesteps=1,
        tier_1_breaches=0,
        tier_1_protected=True,
        peak_shave_count=0,
        valley_fill_count=0,
        load_shift_count=0,
        hard_shed_count=0,
        total_peak_shaved_kwh=0,
        ancillary_value_estimate=0,
        coverage_ratio_mean=0.97,
        coverage_ratio_min=0.97,
        anomaly_count=0,
    )
    monkeypatch.setattr(api, "_run_pipeline_sync", lambda **kwargs: ([record], summary))
    with TestClient(api.app).websocket_connect("/ws/stream") as ws:
        ws.send_json({"scenario": "none"})
        assert ws.receive_json() == record
        assert ws.receive_json()["type"] == "summary"


def test_accented_default_filename_fallback(tmp_path):
    from src.ingestion.schema import resolve_csv

    actual = tmp_path / "dataset_modifié.csv"
    actual.write_text("timestamp\n", encoding="utf-8")
    assert resolve_csv(tmp_path / "dataset_modified.csv") == actual


def test_cli_pipeline_writes_market_outputs(monkeypatch, tmp_path):
    from scenario_runner import run_pipeline

    monkeypatch.setenv("B2G_P2P_ENABLED", "true")
    data = load_dataset().head(96)
    with pytest.warns(UserWarning, match="Capped"):
        result = run_pipeline(data, output_dir=tmp_path)
    assert result["compliance_report"].tier_1_protected
    records = json.loads((tmp_path / "output_normal.json").read_text(encoding="utf-8"))
    assert len(records) == 96
    assert all("p2p_trades" in record for record in records)
    assert any(record["p2p_trades"] for record in records)
    csv_records = pd.read_csv(tmp_path / "output_normal.csv")
    assert csv_records.p2p_trades.map(json.loads).tolist() == [
        r["p2p_trades"] for r in records
    ]


def test_entire_dataset_matching_balance_and_caps(monkeypatch):
    monkeypatch.setenv("B2G_P2P_ENABLED", "true")
    data = load_dataset()
    with pytest.warns(UserWarning, match="Capped"):
        book = load_neighbors(expected_timestamps=data.timestamp)
    directions = set()
    for row in data.itertuples(index=False):
        neighbors = book.at(row.timestamp)
        result = match_neighbors(row.grid_power, row.energy_price, neighbors)
        assert result.grid_power + result.p2p_energy == pytest.approx(row.grid_power)
        assert result.p2p_savings >= 0
        assert abs(result.grid_power) <= abs(row.grid_power) + 1e-9
        assert not (result.p2p_import and result.p2p_export)
        by_id = {n.building_id: n for n in neighbors}
        for trade in result.p2p_trades:
            counterparty = by_id[trade.counterparty_id]
            cap = (
                counterparty.energy_offer_kw
                if trade.direction == "buy"
                else max(counterparty.consumption_kw - counterparty.production, 0)
            )
            assert 0 < trade.quantity_kw <= cap + 1e-9
            directions.add(trade.direction)
        baseline = (
            max(-row.grid_power, 0) * 0.25 * 0.08
            - max(row.grid_power, 0) * 0.25 * row.energy_price
        )
        assert result.revenue - result.cost - baseline == pytest.approx(
            result.p2p_savings
        )
    assert directions == {"buy", "sell"}
