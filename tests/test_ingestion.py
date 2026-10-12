"""
Tests for Layer 1 — Data Ingestion.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure project root is on path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion import load_dataset, TimestepState, EXPECTED_COLUMNS  # noqa: E402
from src.ingestion.loader import iter_timesteps  # noqa: E402


class TestLoadDataset:
    """Validates schema, types, shape, and timestamp range."""

    @pytest.fixture(scope="class")
    def df(self) -> pd.DataFrame:
        return load_dataset()

    def test_expected_shape(self, df: pd.DataFrame) -> None:
        assert df.shape == (11712, 30), f"Unexpected shape: {df.shape}"

    def test_columns_match(self, df: pd.DataFrame) -> None:
        assert list(df.columns) == EXPECTED_COLUMNS

    def test_no_missing_values(self, df: pd.DataFrame) -> None:
        assert df.isnull().sum().sum() == 0

    def test_timestamp_range(self, df: pd.DataFrame) -> None:
        assert str(df["timestamp"].min()) == "2025-06-01 00:00:00"
        assert str(df["timestamp"].max()) == "2025-09-30 23:45:00"

    def test_timestamp_sorted(self, df: pd.DataFrame) -> None:
        assert (df["timestamp"].diff().dropna() >= pd.Timedelta(0)).all()


class TestTimestepState:
    """Validates the per-row dataclass conversion."""

    @pytest.fixture(scope="class")
    def df(self) -> pd.DataFrame:
        return load_dataset()

    def test_iter_yields_correct_type(self, df: pd.DataFrame) -> None:
        first = next(iter_timesteps(df))
        assert isinstance(first, TimestepState)

    def test_iter_count(self, df: pd.DataFrame) -> None:
        count = sum(1 for _ in iter_timesteps(df.head(10)))
        assert count == 10
