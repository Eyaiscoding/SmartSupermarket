#!/usr/bin/env python3
"""
MPC Service Unit Test (No Kafka Required)
==========================================
Tests MPCService.process_message() logic without requiring a live Kafka broker.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.mpc.coordinator import MPCCoordinator
from src.forecasting.flexibility import FlexBudget


def test_mpc_coordinator():
    """Test MPCCoordinator.decide() with sample inputs."""
    
    print("=" * 60)
    print("🧪 MPC Coordinator Unit Test")
    print("=" * 60)
    
    # Create coordinator
    coordinator = MPCCoordinator()
    
    # Sample flexibility budgets
    flex_budgets = [
        FlexBudget(group='hvac', current_power_kw=25.0, max_reduction_kw=12.5, max_duration_min=60.0, tier=3),
        FlexBudget(group='lighting', current_power_kw=16.6, max_reduction_kw=8.3, max_duration_min=240.0, tier=4),
        FlexBudget(group='checkout', current_power_kw=4.2, max_reduction_kw=2.1, max_duration_min=15.0, tier=2),
        FlexBudget(group='other_appliance', current_power_kw=10.8, max_reduction_kw=5.4, max_duration_min=240.0, tier=4),
    ]
    
    # Test case 1: Normal operation (no actions expected)
    print("\n1. Test case: Normal operation")
    action = coordinator.decide(
        total_consumption=150.5,
        pv_power=45.2,
        battery_soc=50.0,
        battery_capacity=200.0,
        energy_price=0.20,  # Below peak threshold
        demand_response=0,
        flex_budgets=flex_budgets,
        forecast_consumption=[150.0, 148.0, 155.0, 152.0],
        forecast_pv=[45.0, 46.0, 44.0, 45.0],
        forecast_prices=[0.20, 0.21, 0.19, 0.20],
    )
    
    print(f"   Peak shave: {action.peak_shave} ({action.peak_shave_kw:.1f} kW)")
    print(f"   Load shift HVAC: {action.load_shift_hvac} ({action.hvac_shed_kw:.1f} kW)")
    print(f"   Valley fill: {action.valley_fill} ({action.valley_fill_kw:.1f} kW)")
    print(f"   Hard shed tiers: {action.hard_shed_tiers} ({action.hard_shed_kw:.1f} kW)")
    print(f"   Active actions: {action.active_action_names}")
    print(f"   Battery request: {action.total_battery_request_kw:.1f} kW")
    
    assert isinstance(action.peak_shave, bool), "peak_shave should be bool"
    assert isinstance(action.peak_shave_kw, float), "peak_shave_kw should be float"
    assert isinstance(action.hard_shed_tiers, list), "hard_shed_tiers should be list"
    assert isinstance(action.active_action_names, list), "active_action_names should be list"
    print("   ✓ All fields have correct types")
    
    # Test case 2: High energy price (peak shaving expected)
    print("\n2. Test case: High energy price (peak shaving)")
    action = coordinator.decide(
        total_consumption=150.5,
        pv_power=45.2,
        battery_soc=60.0,  # Good battery level
        battery_capacity=200.0,
        energy_price=0.30,  # Above peak threshold (0.25)
        demand_response=0,
        flex_budgets=flex_budgets,
        forecast_consumption=[150.0, 148.0, 155.0, 152.0],
        forecast_pv=[45.0, 46.0, 44.0, 45.0],
        forecast_prices=[0.30, 0.31, 0.29, 0.30],
    )
    
    print(f"   Peak shave: {action.peak_shave} ({action.peak_shave_kw:.1f} kW)")
    print(f"   Active actions: {action.active_action_names}")
    
    assert action.peak_shave, "Peak shaving should be active with high price"
    assert action.peak_shave_kw > 0, "Peak shave kW should be positive"
    assert 'peak_shaving' in action.active_action_names, "peak_shaving should be in active actions"
    print("   ✓ Peak shaving triggered correctly")
    
    # Test case 3: Demand response event (load shifting expected)
    print("\n3. Test case: Demand response event (load shifting)")
    action = coordinator.decide(
        total_consumption=150.5,
        pv_power=45.2,
        battery_soc=50.0,
        battery_capacity=200.0,
        energy_price=0.20,
        demand_response=1,  # DR event active
        flex_budgets=flex_budgets,
        forecast_consumption=[150.0, 148.0, 155.0, 152.0],
        forecast_pv=[45.0, 46.0, 44.0, 45.0],
        forecast_prices=[0.20, 0.21, 0.19, 0.20],
    )
    
    print(f"   Load shift HVAC: {action.load_shift_hvac} ({action.hvac_shed_kw:.1f} kW)")
    print(f"   Active actions: {action.active_action_names}")
    
    assert action.load_shift_hvac, "HVAC load shifting should be active during DR"
    assert action.hvac_shed_kw > 0, "HVAC shed kW should be positive"
    assert 'hvac_soft_shed' in action.active_action_names, "hvac_soft_shed should be in active actions"
    print("   ✓ Load shifting triggered correctly")
    
    print("\n" + "=" * 60)
    print("🎉 All MPC Coordinator Tests PASSED")
    print("=" * 60)
    
    return True


if __name__ == '__main__':
    try:
        success = test_mpc_coordinator()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
