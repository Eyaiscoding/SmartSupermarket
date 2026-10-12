"""
Tests for Layer 5 — Reliability & Compliance.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compliance.checker import ComplianceChecker, CriticalityTier, APPLIANCE_TIER_MAP  # noqa: E402
from src.mpc.coordinator import MPCAction  # noqa: E402


class TestCriticalityMapping:

    def test_refrigeration_is_tier1(self) -> None:
        for col in [
            "display_freezer_power",
            "display_refrigerator_power",
            "cold_room_power",
            "freezer_room_power",
        ]:
            assert ComplianceChecker.tier_for(col) == CriticalityTier.TIER_1

    def test_all_appliances_mapped(self) -> None:
        assert len(APPLIANCE_TIER_MAP) == 9


class TestComplianceChecker:

    def test_no_breach_for_normal_actions(self) -> None:
        checker = ComplianceChecker()
        for _ in range(100):
            action = MPCAction(
                peak_shave=True,
                peak_shave_kw=10.0,
                hard_shed_tiers=[4],
                hard_shed_kw=3.0,
            )
            tier_1_ok = checker.check_step(action)
            assert tier_1_ok is True
        report = checker.report()
        assert report.tier_1_breaches == 0
        assert report.tier_1_protected is True

    def test_breach_detected_if_tier1_shed(self) -> None:
        checker = ComplianceChecker()
        bad_action = MPCAction(hard_shed_tiers=[1, 4], hard_shed_kw=10.0)
        tier_1_ok = checker.check_step(bad_action)
        assert tier_1_ok is False
        report = checker.report()
        assert report.tier_1_breaches == 1
        assert report.tier_1_protected is False

    def test_peak_shave_value_accumulation(self) -> None:
        checker = ComplianceChecker()
        for _ in range(4):
            action = MPCAction(peak_shave=True, peak_shave_kw=20.0)
            checker.check_step(action)
        report = checker.report()
        # 4 steps × 20 kW × 0.25 h = 20 kWh
        assert report.total_peak_shaved_kwh == pytest.approx(20.0, abs=0.1)
