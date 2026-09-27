"""
Layer 2b — Anomaly Detection
==============================
Lightweight anomaly detector using Isolation Forest, producing an anomaly
signal that can be compared against the dataset's own ``anomaly_score``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


class AnomalyDetector:
    """Isolation-Forest anomaly detector on energy-related signals."""

    FEATURE_COLS: list[str] = [
        "total_consumption",
        "pv_power",
        "grid_power",
        "battery_power",
        "temperature",
        "solar_irradiance",
    ]

    def __init__(
        self,
        contamination: float = 0.05,
        n_estimators: int = 100,
        random_state: int = 42,
    ) -> None:
        self.model = IsolationForest(
            contamination=contamination,
            n_estimators=n_estimators,
            random_state=random_state,
        )
        self._fitted = False

    def train(self, df: pd.DataFrame) -> None:
        """Fit the Isolation Forest on the dataset."""
        X = df[self.FEATURE_COLS].values
        self.model.fit(X)
        self._fitted = True

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of *df* with ``anomaly_flag`` (bool) and
        ``anomaly_model_score`` (float) columns added.

        The Isolation Forest ``decision_function`` produces *negative* scores
        for anomalies; we invert and normalise to [0, 1] so that *higher*
        values mean *more anomalous*, matching the dataset's ``anomaly_score``
        convention.
        """
        if not self._fitted:
            raise RuntimeError("AnomalyDetector has not been trained yet.")

        X = df[self.FEATURE_COLS].values
        raw_scores = self.model.decision_function(X)

        # Invert: lower decision_function → more anomalous.
        inverted = -raw_scores
        # Min–max normalise to [0, 1].
        s_min, s_max = inverted.min(), inverted.max()
        if s_max - s_min > 0:
            normalised = (inverted - s_min) / (s_max - s_min)
        else:
            normalised = np.zeros_like(inverted)

        labels = self.model.predict(X)  # +1 = normal, -1 = anomaly

        out = df.copy()
        out["anomaly_flag"] = labels == -1
        out["anomaly_model_score"] = normalised
        return out

    def identify_source(self, row: pd.Series) -> str | None:
        """Heuristic to attribute an anomaly to a probable source column.

        Compares each feature value to the column-wise z-score and returns
        the column with the highest absolute deviation.  Returns ``None``
        if no anomaly flag is present.
        """
        if not row.get("anomaly_flag", False):
            return None
        deviations: dict[str, float] = {}
        for col in self.FEATURE_COLS:
            deviations[col] = abs(float(row.get(col, 0)))
        # Highest raw absolute value is a simple heuristic; in production
        # you'd use SHAP or column-drop importance.
        return max(deviations, key=deviations.get)  # type: ignore[arg-type]
