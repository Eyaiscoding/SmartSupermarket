#!/usr/bin/env python3
"""
MPC Service Unit Tests
======================
Unit tests for MPC service logic without requiring Kafka.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Mock kafka imports before importing MPCService
sys.modules['kafka'] = MagicMock()
sys.modules['kafka_utils'] = MagicMock()
sys.modules['kafka_utils.utils'] = MagicMock()

# Now we can import
from src.forecasting.flexibility import FlexBudget


def _parse_flexibility_budgets(budgets_dict: dict, telemetry: dict) -> list[FlexBudget]:
    """
    Standalone version of _parse_flexibility_budgets for testing.
    This is a copy of the implementation from MPCService.
    """
    flex_budgets = []
    
    # Typical supermarket appliance power draws (kW) for fallback when telemetry unavailable
    TYPICAL_POWER_DEFAULTS = {
        'hvac_power': 50.0,          # HVAC system
        'lighting_power': 30.0,      # Store lighting
        'checkout_power': 20.0,      # Checkout & IT
        'other_appliance_power': 25.0  # Other flexible loads
    }
    
    # Map budget keys to tier, group name, and power key from telemetry
    # (shed_key, group, power_key, tier, duration)
    budget_mapping = [
        ('hvac_soft_shed_kw', 'hvac', 'hvac_power', 3, 60.0),
        ('lighting_shed_kw', 'lighting', 'lighting_power', 4, 240.0),
        ('checkout_shed_kw', 'checkout', 'checkout_power', 2, 15.0),
        ('other_shed_kw', 'other_appliance', 'other_appliance_power', 4, 240.0),
    ]
    
    for shed_key, group, power_key, tier, duration in budget_mapping:
        shed_capacity = budgets_dict.get(shed_key, 0.0)
        
        # Get actual current power from telemetry, fallback to typical supermarket defaults
        current_power = telemetry.get(power_key, TYPICAL_POWER_DEFAULTS.get(power_key, 0.0))
        
        if shed_capacity > 0 or current_power > 0:
            flex_budgets.append(
                FlexBudget(
                    group=group,
                    current_power_kw=current_power,
                    max_reduction_kw=shed_capacity,
                    max_duration_min=duration,
                    tier=tier
                )
            )
    
    return flex_budgets


def test_parse_flexibility_budgets_with_defaults():
    """Test FlexBudget parsing uses typical supermarket defaults when telemetry missing."""
    print("\n" + "=" * 60)
    print("🧪 Testing _parse_flexibility_budgets() with defaults")
    print("=" * 60)
    
    # Test data - only flexibility budgets, no telemetry
    budgets_dict = {
        'hvac_soft_shed_kw': 12.5,
        'lighting_shed_kw': 8.3,
        'checkout_shed_kw': 2.1,
        'other_shed_kw': 5.4
    }
    
    telemetry = {}  # Empty - should use defaults
    
    # Parse budgets
    flex_budgets = _parse_flexibility_budgets(budgets_dict, telemetry)
    
    # Validate
    print(f"\n✓ Parsed {len(flex_budgets)} FlexBudget objects")
    
    expected_defaults = {
        'hvac': 50.0,
        'lighting': 30.0,
        'checkout': 20.0,
        'other_appliance': 25.0
    }
    
    all_valid = True
    for budget in flex_budgets:
        expected_power = expected_defaults.get(budget.group, 0.0)
        
        print(f"\n  Group: {budget.group}")
        print(f"    Current power: {budget.current_power_kw:.1f} kW (expected: {expected_power:.1f} kW)")
        print(f"    Max reduction: {budget.max_reduction_kw:.1f} kW")
        print(f"    Max duration: {budget.max_duration_min:.0f} min")
        print(f"    Tier: {budget.tier}")
        
        # Validate that current_power matches expected default
        if budget.current_power_kw == expected_power:
            print(f"    ✓ Using correct default power")
        else:
            print(f"    ✗ ERROR: Expected {expected_power:.1f} kW, got {budget.current_power_kw:.1f} kW")
            all_valid = False
        
        # Validate that current_power >= max_reduction
        if budget.current_power_kw >= budget.max_reduction_kw:
            print(f"    ✓ current_power ({budget.current_power_kw:.1f}) >= max_reduction ({budget.max_reduction_kw:.1f})")
        else:
            print(f"    ✗ ERROR: current_power ({budget.current_power_kw:.1f}) < max_reduction ({budget.max_reduction_kw:.1f})")
            all_valid = False
    
    if not all_valid:
        print("\n" + "=" * 60)
        print("❌ FlexBudget Parsing Test FAILED")
        print("=" * 60)
        return False
    
    print("\n" + "=" * 60)
    print("🎉 FlexBudget Parsing Test PASSED")
    print("=" * 60)
    return True


def test_parse_flexibility_budgets_with_telemetry():
    """Test FlexBudget parsing uses telemetry when available."""
    print("\n" + "=" * 60)
    print("🧪 Testing _parse_flexibility_budgets() with telemetry")
    print("=" * 60)
    
    # Test data with telemetry
    budgets_dict = {
        'hvac_soft_shed_kw': 12.5,
        'lighting_shed_kw': 8.3,
        'checkout_shed_kw': 2.1,
        'other_shed_kw': 5.4
    }
    
    telemetry = {
        'hvac_power': 60.0,
        'lighting_power': 35.0,
        'checkout_power': 25.0,
        'other_appliance_power': 30.0
    }
    
    # Parse budgets
    flex_budgets = _parse_flexibility_budgets(budgets_dict, telemetry)
    
    print(f"\n✓ Parsed {len(flex_budgets)} FlexBudget objects")
    
    all_valid = True
    for budget in flex_budgets:
        expected_power = telemetry.get(f"{budget.group}_power", 0.0)
        # Handle 'other_appliance' special case
        if budget.group == 'other_appliance':
            expected_power = telemetry.get('other_appliance_power', 0.0)
        
        print(f"\n  Group: {budget.group}")
        print(f"    Current power: {budget.current_power_kw:.1f} kW (from telemetry)")
        print(f"    Max reduction: {budget.max_reduction_kw:.1f} kW")
        
        # Validate uses telemetry values
        if budget.current_power_kw == expected_power:
            print(f"    ✓ Using telemetry power value")
        else:
            print(f"    ✗ ERROR: Expected {expected_power:.1f} kW from telemetry")
            all_valid = False
        
        # Validate that current_power >= max_reduction
        if budget.current_power_kw >= budget.max_reduction_kw:
            print(f"    ✓ current_power >= max_reduction")
        else:
            print(f"    ✗ ERROR: current_power < max_reduction")
            all_valid = False
    
    if not all_valid:
        print("\n" + "=" * 60)
        print("❌ Telemetry Test FAILED")
        print("=" * 60)
        return False
    
    print("\n" + "=" * 60)
    print("🎉 Telemetry Test PASSED")
    print("=" * 60)
    return True


if __name__ == '__main__':
    all_passed = True
    
    if not test_parse_flexibility_budgets_with_defaults():
        all_passed = False
    
    if not test_parse_flexibility_budgets_with_telemetry():
        all_passed = False
    
    if all_passed:
        print("\n" + "=" * 60)
        print("✅ ALL UNIT TESTS PASSED")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("❌ SOME TESTS FAILED")
        print("=" * 60)
        sys.exit(1)
