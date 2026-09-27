"""
Layer 2a — AI Forecasting
==========================
Trains a lightweight gradient-boosting model to predict next-step total
consumption and PV generation.  Provides train / predict interface and
comparison against the dataset's own ``forecast_consumption`` /
``forecast_pv`` columns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


class Forecaster:
    """Gradient-boosting forecaster for consumption and PV output."""

    # Feature columns used for both targets.
    FEATURE_COLS: list[str] = [
        "occupancy",
        "temperature",
        "humidity",
        "solar_irradiance",
        "hour",
        "day_of_week",
        "pv_power_lag1",
        "consumption_lag1",
    ]

    def __init__(
        self,
        n_estimators: int = 200,
        max_depth: int = 5,
        learning_rate: float = 0.1,
    ) -> None:
        self.model_consumption = GradientBoostingRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            random_state=42,
        )
        self.model_pv = GradientBoostingRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            random_state=42,
        )
        self._fitted = False

    # ── Feature engineering ──────────────────────────────────────────────
    @staticmethod
    def _build_features(df: pd.DataFrame) -> pd.DataFrame:
        """Add lag and calendar features required by the models."""
        out = df.copy()
        out["hour"] = pd.to_datetime(out["timestamp"]).dt.hour
        out["day_of_week"] = pd.to_datetime(out["timestamp"]).dt.dayofweek
        out["pv_power_lag1"] = out["pv_power"].shift(1).bfill()
        out["consumption_lag1"] = out["total_consumption"].shift(1).bfill()
        return out

    # ── Training ─────────────────────────────────────────────────────────
    def train(self, df: pd.DataFrame) -> dict[str, float]:
        """Fit on the entire DataFrame (or a training slice).

        Returns a dict of in-sample MAE/RMSE for both targets.
        """
        feat = self._build_features(df)
        X = feat[self.FEATURE_COLS].values
        y_cons = feat["total_consumption"].values
        y_pv = feat["pv_power"].values

        self.model_consumption.fit(X, y_cons)
        self.model_pv.fit(X, y_pv)
        self._fitted = True

        pred_cons = self.model_consumption.predict(X)
        pred_pv = self.model_pv.predict(X)

        return {
            "consumption_mae": mean_absolute_error(y_cons, pred_cons),
            "consumption_rmse": np.sqrt(mean_squared_error(y_cons, pred_cons)),
            "pv_mae": mean_absolute_error(y_pv, pred_pv),
            "pv_rmse": np.sqrt(mean_squared_error(y_pv, pred_pv)),
        }

    # ── Prediction ───────────────────────────────────────────────────────
    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of *df* with added ``pred_consumption`` and
        ``pred_pv`` columns."""
        if not self._fitted:
            raise RuntimeError("Forecaster has not been trained yet.")
        feat = self._build_features(df)
        X = feat[self.FEATURE_COLS].values
        out = df.copy()
        out["pred_consumption"] = self.model_consumption.predict(X)
        out["pred_pv"] = self.model_pv.predict(X)
        return out

    # ── Evaluation against dataset's own forecasts ───────────────────────
    def evaluate_vs_dataset(self, df: pd.DataFrame) -> dict[str, float]:
        """Compare our model against the dataset's built-in forecast columns.

        Returns MAE of our model vs MAE of the dataset forecast, for both
        consumption and PV.
        """
        pred_df = self.predict(df)

        our_cons_mae = mean_absolute_error(
            pred_df["total_consumption"], pred_df["pred_consumption"]
        )
        ds_cons_mae = mean_absolute_error(
            pred_df["total_consumption"], pred_df["forecast_consumption"]
        )
        our_pv_mae = mean_absolute_error(
            pred_df["pv_power"], pred_df["pred_pv"]
        )
        ds_pv_mae = mean_absolute_error(
            pred_df["pv_power"], pred_df["forecast_pv"]
        )

        return {
            "our_consumption_mae": our_cons_mae,
            "dataset_consumption_mae": ds_cons_mae,
            "our_pv_mae": our_pv_mae,
            "dataset_pv_mae": ds_pv_mae,
        }
