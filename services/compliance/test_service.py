"""
Unit tests for Compliance Service
"""

import unittest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.compliance.checker import ComplianceChecker, ComplianceStatus
from src.mpc.coordinator import MPCAction


class TestComplianceService(unittest.TestCase):
    """Test compliance rule verification."""
    
    def setUp(self):
        """Initialize checker for each test."""
        self.checker = ComplianceChecker()
    
    def test_r1_tier1_never_shed(self):
        """R1: Tier 1 loads must never be shed."""
        action = MPCAction(
            peak_shave=False,
            peak_shave_kw=0.0,
            load_shift_hvac=False,
            hvac_shed_kw=0.0,
            valley_fill=False,
            valley_fill_kw=0.0,
            hard_shed_tiers=[1],  # VIOLATION: shedding Tier 1
            hard_shed_kw=10.0,
            active_action_names=[]
        )
        
        tier_1_protected = self.checker.check_step(
            action=action,
            timestamp='2026-10-13T14:00:00Z'
        )
        
        self.assertFalse(tier_1_protected, "Tier 1 should not be protected when shed")
        self.assertEqual(self.checker.last_status, ComplianceStatus.RED)
    
    def test_r2_tier1_physically_supplied(self):
        """R2: Tier 1 demand must be met by available supply."""
        action = MPCAction(
            peak_shave=False,
            peak_shave_kw=0.0,
            load_shift_hvac=False,
            hvac_shed_kw=0.0,
            valley_fill=False,
            valley_fill_kw=0.0,
            hard_shed_tiers=[],
            hard_shed_kw=0.0,
            active_action_names=[]
        )
        
        # Tier 1 demand exceeds supply
        tier_1_protected = self.checker.check_step(
            action=action,
            timestamp='2026-10-13T14:00:00Z',
            tier_1_demand_kw=80.0,  # Tier 1 needs 80 kW
            supply_kw=60.0          # Only 60 kW available
        )
        
        self.assertFalse(tier_1_protected, "Tier 1 undersupplied should fail")
        self.assertEqual(self.checker.last_status, ComplianceStatus.RED)
    
    def test_r3_cascade_order(self):
        """R3: Load shedding must follow cascade order (4→3→2)."""
        action = MPCAction(
            peak_shave=False,
            peak_shave_kw=0.0,
            load_shift_hvac=False,
            hvac_shed_kw=0.0,
            valley_fill=False,
            valley_fill_kw=0.0,
            hard_shed_tiers=[2],  # Shedding Tier 2 without shedding Tier 4
            hard_shed_kw=10.0,
            active_action_names=[]
        )
        
        tier_1_protected = self.checker.check_step(
            action=action,
            timestamp='2026-10-13T14:00:00Z'
        )
        
        # Tier 1 is protected but cascade order violated
        self.assertTrue(tier_1_protected)
        self.assertEqual(self.checker.last_status, ComplianceStatus.YELLOW)
        report = self.checker.report()
        self.assertGreater(report.cascade_order_warnings, 0)
    
    def test_r4_battery_soc_limits(self):
        """R4: Battery SOC must stay within 10-95%."""
        action = MPCAction(
            peak_shave=True,
            peak_shave_kw=20.0,
            load_shift_hvac=False,
            hvac_shed_kw=0.0,
            valley_fill=False,
            valley_fill_kw=0.0,
            hard_shed_tiers=[],
            hard_shed_kw=0.0,
            active_action_names=['peak_shave']
        )
        
        # SOC below minimum
        tier_1_protected = self.checker.check_step(
            action=action,
            timestamp='2026-10-13T14:00:00Z',
            battery_soc=8.0  # Below 10% minimum
        )
        
        self.assertTrue(tier_1_protected)
        self.assertEqual(self.checker.last_status, ComplianceStatus.YELLOW)
        report = self.checker.report()
        self.assertGreater(report.battery_limit_warnings, 0)
    
    def test_r4_battery_rate_limits(self):
        """R4: Battery power must not exceed rate limit (50 kW)."""
        action = MPCAction(
            peak_shave=True,
            peak_shave_kw=60.0,  # Exceeds 50 kW limit
            load_shift_hvac=False,
            hvac_shed_kw=0.0,
            valley_fill=False,
            valley_fill_kw=0.0,
            hard_shed_tiers=[],
            hard_shed_kw=0.0,
            active_action_names=['peak_shave']
        )
        
        tier_1_protected = self.checker.check_step(
            action=action,
            timestamp='2026-10-13T14:00:00Z',
            battery_power_kw=60.0  # Exceeds 50 kW max
        )
        
        self.assertTrue(tier_1_protected)
        self.assertEqual(self.checker.last_status, ComplianceStatus.YELLOW)
        report = self.checker.report()
        self.assertGreater(report.battery_limit_warnings, 0)
    
    def test_green_status_normal_operation(self):
        """Verify GREEN status for normal compliant operation."""
        action = MPCAction(
            peak_shave=False,
            peak_shave_kw=0.0,
            load_shift_hvac=False,
            hvac_shed_kw=0.0,
            valley_fill=True,
            valley_fill_kw=30.0,
            hard_shed_tiers=[],
            hard_shed_kw=0.0,
            active_action_names=['valley_fill']
        )
        
        tier_1_protected = self.checker.check_step(
            action=action,
            timestamp='2026-10-13T14:00:00Z',
            battery_soc=65.0,
            battery_power_kw=30.0
        )
        
        self.assertTrue(tier_1_protected)
        self.assertEqual(self.checker.last_status, ComplianceStatus.GREEN)
    
    def test_compliance_report_generation(self):
        """Verify full compliance report generation."""
        # Run multiple steps
        for i in range(5):
            action = MPCAction(
                peak_shave=(i % 2 == 0),
                peak_shave_kw=20.0 if i % 2 == 0 else 0.0,
                load_shift_hvac=False,
                hvac_shed_kw=0.0,
                valley_fill=(i % 2 == 1),
                valley_fill_kw=30.0 if i % 2 == 1 else 0.0,
                hard_shed_tiers=[],
                hard_shed_kw=0.0,
                active_action_names=[]
            )
            
            self.checker.check_step(
                action=action,
                timestamp=f'2026-10-13T14:{i:02d}:00Z',
                battery_soc=50.0 + i,
                battery_power_kw=20.0 if i % 2 == 0 else -30.0
            )
        
        report = self.checker.report()
        
        self.assertEqual(report.total_timesteps, 5)
        self.assertTrue(report.tier_1_protected)
        self.assertEqual(report.tier_1_breaches, 0)
        self.assertGreater(report.peak_shave_count, 0)
        self.assertGreater(report.valley_fill_count, 0)


if __name__ == '__main__':
    unittest.main()
