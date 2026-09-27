"""
Tests for Layer 6 — API Output.
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.output import OutputWriter, OutputRecord, compute_coverage_status


class TestCoverageStatus:

    def test_normal(self) -> None:
        assert compute_coverage_status(0.98) == "NORMAL"

    def test_at_risk(self) -> None:
        assert compute_coverage_status(0.92) == "AT_RISK"

    def test_critical(self) -> None:
        assert compute_coverage_status(0.85) == "CRITICAL"


class TestOutputWriter:

    def _make_record(self, **overrides) -> OutputRecord:
        defaults = dict(
            timestamp="2025-06-01 00:00:00",
            coverage_ratio=0.97,
            coverage_status="NORMAL",
            active_actions=["peak_shaving"],
            tier_1_protected=True,
            battery_soc=55.0,
            grid_power=20.0,
            p2p_energy=0.0,
            anomaly_flag=False,
            anomaly_source=None,
        )
        defaults.update(overrides)
        return OutputRecord(**defaults)

    def test_json_roundtrip(self, tmp_path: Path) -> None:
        writer = OutputWriter()
        writer.add(self._make_record())
        writer.add(self._make_record(timestamp="2025-06-01 00:15:00"))
        json_path = tmp_path / "test.json"
        writer.to_json(json_path)

        with open(json_path) as f:
            data = json.load(f)
        assert len(data) == 2
        assert data[0]["coverage_status"] == "NORMAL"

    def test_csv_roundtrip(self, tmp_path: Path) -> None:
        import pandas as pd

        writer = OutputWriter()
        writer.add(self._make_record())
        csv_path = tmp_path / "test.csv"
        writer.to_csv(csv_path)

        df = pd.read_csv(csv_path)
        assert len(df) == 1
        assert "coverage_ratio" in df.columns

    def test_summary(self) -> None:
        writer = OutputWriter()
        writer.add(self._make_record(coverage_ratio=0.98, coverage_status="NORMAL"))
        writer.add(self._make_record(coverage_ratio=0.88, coverage_status="CRITICAL"))
        summary = writer.summary()
        assert summary["total_records"] == 2
        assert summary["tier_1_always_protected"] is True
