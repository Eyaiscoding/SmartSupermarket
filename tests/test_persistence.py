"""
Tests for the Persistence Layer (v2).
======================================
Tests TimescaleDB round-trip (write pipeline output, read it back, verify
the Tier 1 invariant holds from storage) and Redis cache get/set.

These tests use SQLite as a stand-in for PostgreSQL/TimescaleDB so they
can run without Docker.  The hypertable setup is skipped (SQLite doesn't
support it), but the ORM read/write logic is exercised identically.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestTimescaleStore:
    """Tests using SQLite as a local stand-in for TimescaleDB."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a TimescaleStore backed by a temporary SQLite DB."""
        from src.persistence.timescale import TimescaleStore
        import src.persistence.timescale as ts_module

        # Reset module-level engine to force re-creation.
        ts_module._engine = None
        ts_module._SessionLocal = None

        db_path = tmp_path / "test.db"
        url = f"sqlite:///{db_path}"
        store = TimescaleStore(url=url)
        return store

    def test_write_and_read_back(self, store):
        """Write a record, read it back, verify fields match."""
        rec = {
            "timestamp": "2025-06-01 00:00:00",
            "coverage_ratio": 0.97,
            "coverage_status": "NORMAL",
            "active_actions": ["peak_shaving"],
            "tier_1_protected": True,
            "battery_soc": 55.0,
            "grid_power": 20.0,
            "p2p_energy": 0.0,
            "anomaly_flag": False,
            "anomaly_source": None,
        }
        store.write_record(rec, scenario_label="test")
        rows = store.query_all(scenario_label="test")
        assert len(rows) == 1
        assert rows[0]["coverage_ratio"] == 0.97
        assert rows[0]["tier_1_protected"] is True
        assert rows[0]["active_actions"] == ["peak_shaving"]

    def test_bulk_write_and_range_query(self, store):
        """Bulk-write records, query a time range, verify count."""
        records = [
            {
                "timestamp": f"2025-06-01 00:{i*15:02d}:00",
                "coverage_ratio": 0.95 + i * 0.01,
                "coverage_status": "NORMAL",
                "active_actions": [],
                "tier_1_protected": True,
                "battery_soc": 50.0 + i,
                "grid_power": 10.0,
                "p2p_energy": 0.0,
                "anomaly_flag": False,
                "anomaly_source": None,
            }
            for i in range(4)
        ]
        count = store.write_records_bulk(records, scenario_label="bulk")
        assert count == 4

        result = store.query_range(
            "2025-06-01 00:00:00",
            "2025-06-01 00:20:00",
            scenario_label="bulk",
        )
        assert len(result) == 2  # 00:00 and 00:15 (00:30 excluded by range)

    def test_tier1_invariant_from_storage(self, store):
        """The critical test: run a mini pipeline, persist to DB, read
        back, and verify Tier 1 was never breached when read from storage."""
        from src.ingestion import load_dataset
        from src.forecasting import Forecaster, AnomalyDetector, FlexibilityEstimator
        from src.mpc import MPCCoordinator
        from src.derms import DERMSDispatcher
        from src.compliance import ComplianceChecker
        from src.api.output import compute_coverage_status

        # Use first 100 rows for speed.
        df = load_dataset()
        df = df.head(100)

        forecaster = Forecaster(n_estimators=20, max_depth=3)
        forecaster.train(df)
        anomaly_det = AnomalyDetector()
        anomaly_det.train(df)
        anom_df = anomaly_det.detect(df)
        flex_est = FlexibilityEstimator()
        mpc = MPCCoordinator()
        dispatcher = DERMSDispatcher()
        checker = ComplianceChecker()

        battery_soc = float(df.iloc[0]["battery_soc"])
        battery_capacity = float(df.iloc[0]["battery_capacity"])
        records = []

        for i in range(len(df)):
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
            horizon = min(4, len(df) - i - 1)
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
            tier_1_ok = checker.check_step(action)

            supply = float(row["pv_power"]) + max(dispatch.battery_power, 0.0)
            supply += max(dispatch.grid_power, 0.0)
            total_c = float(row["total_consumption"])
            coverage = min(supply / total_c if total_c > 0 else 1.0, 1.0)

            anomaly_flag = bool(anom_df.iloc[i].get("anomaly_flag", False))
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
                "anomaly_source": None,
            }
            records.append(rec)

        # Persist all records to the DB.
        store.write_records_bulk(records, scenario_label="tier1_test")

        # Read back from DB and verify Tier 1 invariant.
        stored = store.query_all(scenario_label="tier1_test")
        assert len(stored) == 100
        for row in stored:
            assert row["tier_1_protected"] is True, (
                f"Tier 1 breached at {row['timestamp']} when read from storage!"
            )


class TestRedisCache:
    """Tests for the Redis cache wrapper (no Redis needed -- tests the
    graceful degradation path)."""

    def test_cache_unavailable_returns_none(self):
        """When Redis is not running, get_latest returns None, not an error."""
        from src.persistence.redis_cache import RedisCache
        cache = RedisCache(url="redis://localhost:59999/0")  # bogus port
        assert cache.available is False
        assert cache.get_latest() is None

    def test_set_latest_noop_when_unavailable(self):
        """set_latest should not raise when Redis is unavailable."""
        from src.persistence.redis_cache import RedisCache
        cache = RedisCache(url="redis://localhost:59999/0")
        cache.set_latest({"test": True})  # should not raise
