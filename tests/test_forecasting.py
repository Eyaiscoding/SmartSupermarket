"""
Tests for Layer 2 — AI Forecasting, Anomaly Detection, Flexibility.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion import load_dataset
from src.forecasting import Forecaster, AnomalyDetector, FlexibilityEstimator


class TestForecaster:

    @pytest.fixture(scope="class")
    def trained(self):
        df = load_dataset()
        fc = Forecaster(n_estimators=50, max_depth=3)
        metrics = fc.train(df)
        return fc, df, metrics

    def test_training_returns_metrics(self, trained) -> None:
        _, _, metrics = trained
        for key in ["consumption_mae", "consumption_rmse", "pv_mae", "pv_rmse"]:
            assert key in metrics
            assert metrics[key] >= 0

    def test_prediction_adds_columns(self, trained) -> None:
        fc, df, _ = trained
        out = fc.predict(df.head(100))
        assert "pred_consumption" in out.columns
        assert "pred_pv" in out.columns

    def test_prediction_not_fitted_raises(self) -> None:
        fc = Forecaster()
        with pytest.raises(RuntimeError):
            fc.predict(pd.DataFrame())


class TestAnomalyDetector:

    @pytest.fixture(scope="class")
    def detector(self):
        df = load_dataset()
        det = AnomalyDetector()
        det.train(df)
        return det, df

    def test_detect_adds_columns(self, detector) -> None:
        det, df = detector
        out = det.detect(df.head(100))
        assert "anomaly_flag" in out.columns
        assert "anomaly_model_score" in out.columns

    def test_anomaly_scores_in_range(self, detector) -> None:
        det, df = detector
        out = det.detect(df)
        assert out["anomaly_model_score"].min() >= 0.0
        assert out["anomaly_model_score"].max() <= 1.0


class TestFlexibilityEstimator:

    def test_tier1_zero_flexibility(self) -> None:
        fe = FlexibilityEstimator()
        budgets = fe.estimate(
            display_freezer_power=3.0,
            display_refrigerator_power=4.0,
            cold_room_power=5.0,
            freezer_room_power=7.0,
            hvac_power=10.0,
            lighting_power=3.0,
            checkout_power=0.5,
            it_power=2.5,
            other_appliance_power=1.5,
            temperature=22.0,
        )
        tier1 = [b for b in budgets if b.tier == 1]
        assert len(tier1) == 4
        for b in tier1:
            assert b.max_reduction_kw == 0.0, f"{b.group} should have zero flex"

    def test_tier4_full_flexibility(self) -> None:
        fe = FlexibilityEstimator()
        budgets = fe.estimate(
            display_freezer_power=3.0,
            display_refrigerator_power=4.0,
            cold_room_power=5.0,
            freezer_room_power=7.0,
            hvac_power=10.0,
            lighting_power=3.0,
            checkout_power=0.5,
            it_power=2.5,
            other_appliance_power=1.5,
            temperature=22.0,
        )
        tier4 = [b for b in budgets if b.tier == 4]
        for b in tier4:
            assert b.max_reduction_kw == b.current_power_kw

    def test_hvac_no_flex_outside_comfort(self) -> None:
        fe = FlexibilityEstimator()
        budgets = fe.estimate(
            display_freezer_power=3.0,
            display_refrigerator_power=4.0,
            cold_room_power=5.0,
            freezer_room_power=7.0,
            hvac_power=10.0,
            lighting_power=3.0,
            checkout_power=0.5,
            it_power=2.5,
            other_appliance_power=1.5,
            temperature=35.0,  # way outside comfort
        )
        hvac = [b for b in budgets if b.group == "hvac"][0]
        assert hvac.max_reduction_kw == 0.0
