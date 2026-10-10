"""
Tests for Layer 5 — Reliability & Compliance.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.compliance.checker import (  # noqa: E402
    APPLIANCE_TIER_MAP,
    REGULATORY_REFERENCES,
    ComplianceChecker,
    ComplianceStatus,
    CriticalityTier,
    cold_chain_temps,
)
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


class TestAuditRules:
    """Extended audit rules R2-R4 and per-step GREEN/YELLOW/RED status."""

    def test_green_when_nothing_shed(self) -> None:
        checker = ComplianceChecker()
        checker.check_step(MPCAction(), tier_1_demand_kw=20.0, supply_kw=50.0)
        assert checker.last_status == ComplianceStatus.GREEN
        assert checker.report().overall_status == "GREEN"

    def test_red_when_tier1_shed(self) -> None:
        checker = ComplianceChecker()
        checker.check_step(MPCAction(hard_shed_tiers=[1, 4], hard_shed_kw=5.0))
        assert checker.last_status == ComplianceStatus.RED
        rep = checker.report()
        assert rep.overall_status == "RED"
        assert rep.violations[0].rule == "R1_tier1_shed"

    def test_physical_breach_when_supply_below_tier1_demand(self) -> None:
        checker = ComplianceChecker()
        ok = checker.check_step(MPCAction(), tier_1_demand_kw=30.0, supply_kw=12.0)
        assert ok is False
        rep = checker.report()
        assert rep.physical_tier_1_breaches == 1
        assert rep.tier_1_protected is False
        assert rep.red_steps == 1

    def test_yellow_when_tier2_shed(self) -> None:
        checker = ComplianceChecker()
        checker.check_step(MPCAction(hard_shed_tiers=[4, 3, 2], hard_shed_kw=9.0))
        assert checker.last_status == ComplianceStatus.YELLOW

    def test_cascade_order_warning(self) -> None:
        checker = ComplianceChecker()
        # Tier 2 shed while Tier 3 spared -> out of cascade order.
        checker.check_step(MPCAction(hard_shed_tiers=[4, 2], hard_shed_kw=9.0))
        rep = checker.report()
        assert rep.cascade_order_warnings == 1
        assert rep.yellow_steps == 1
        assert rep.tier_1_protected is True

    def test_battery_limits_flagged(self) -> None:
        checker = ComplianceChecker()
        checker.check_step(MPCAction(), battery_soc=5.0, battery_power_kw=60.0)
        assert checker.report().battery_limit_warnings == 2
        assert checker.last_status == ComplianceStatus.YELLOW

    def test_report_to_dict_is_json_serialisable(self) -> None:
        import json
        checker = ComplianceChecker()
        checker.check_step(MPCAction(hard_shed_tiers=[1]), timestamp="2025-06-01 00:00:00")
        d = checker.report().to_dict()
        assert json.dumps(d)
        assert d["compliance_rate"] == 0.0


class TestColdChainAndReferences:
    """R5 (cold chain), R6 (breach duration) and the norms registry."""

    def test_r5_inactive_without_temperatures(self) -> None:
        checker = ComplianceChecker()
        checker.check_step(MPCAction())
        rep = checker.report()
        assert rep.cold_chain_monitored is False
        assert rep.cold_chain_breaches == 0

    def test_r5_ok_within_limits(self) -> None:
        checker = ComplianceChecker()
        checker.check_step(
            MPCAction(),
            cold_temps={"display_freezer_temp": -19.5, "cold_room_temp": 3.2},
        )
        rep = checker.report()
        assert rep.cold_chain_monitored is True
        assert rep.cold_chain_breaches == 0
        assert rep.overall_status == "GREEN"

    def test_r5_frozen_above_minus_18_is_red(self) -> None:
        checker = ComplianceChecker()
        checker.check_step(
            MPCAction(), timestamp="2025-07-01 12:00:00",
            cold_temps={"freezer_room_temp": -15.0},
        )
        rep = checker.report()
        assert checker.last_status == ComplianceStatus.RED
        assert rep.cold_chain_breaches == 1
        assert rep.violations[0].rule == "R5_cold_chain"

    def test_r5_chilled_above_4_is_red(self) -> None:
        checker = ComplianceChecker()
        checker.check_step(MPCAction(), cold_temps={"cold_room_temp": 6.0})
        assert checker.report().cold_chain_breaches == 1

    def test_r5_longest_breach_duration(self) -> None:
        checker = ComplianceChecker()
        for t in (5.0, 6.0, 7.0, 3.0, 5.0):   # 3 consecutive, then 1
            checker.check_step(MPCAction(), cold_temps={"cold_room_temp": t})
        rep = checker.report()
        assert rep.cold_chain_breaches == 4
        assert rep.longest_cold_chain_breach_min == 45.0  # 3 steps x 15 min

    def test_r6_longest_tier1_breach_minutes(self) -> None:
        checker = ComplianceChecker()
        for shed in ([4], [1], [1], [1], [4], [1]):
            checker.check_step(MPCAction(hard_shed_tiers=shed))
        assert checker.report().longest_tier_1_breach_min == 45.0

    def test_cold_chain_temps_helper(self) -> None:
        assert cold_chain_temps({"timestamp": "x", "hvac_power": 3.0}) is None
        got = cold_chain_temps({"cold_room_temp": 2.5, "other": 1})
        assert got == {"cold_room_temp": 2.5}

    def test_references_registry_is_explicit_about_scope(self) -> None:
        scopes = {r["scope"] for r in REGULATORY_REFERENCES}
        assert scopes <= {"simulated", "design", "inspiration"}
        assert all(r["source"] and r["requirement"] for r in REGULATORY_REFERENCES)
        d = ComplianceChecker().report().to_dict()
        assert d["regulatory_references"]

    def test_frequent_warnings_do_not_crowd_out_critical_violations(self) -> None:
        checker = ComplianceChecker()
        # 500 low-severity R3 warnings first ...
        for _ in range(500):
            checker.check_step(MPCAction(hard_shed_tiers=[4, 2], hard_shed_kw=1.0))
        # ... then one critical cold-chain breach.
        checker.check_step(
            MPCAction(), timestamp="2025-08-01 00:00:00",
            cold_temps={"freezer_room_temp": -10.0},
        )
        rep = checker.report()
        assert rep.violation_counts["R3_cascade_order"] == 500   # exact count
        assert rep.violation_counts["R5_cold_chain"] == 1
        assert any(v.rule == "R5_cold_chain" for v in rep.violations)