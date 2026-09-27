"""
Tests for Layer 4 — DERMS Dispatch.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.derms.dispatch import DERMSDispatcher, DispatchResult
from src.mpc.coordinator import MPCAction


class TestDERMSDispatcher:

    def test_soc_never_below_min(self) -> None:
        dispatcher = DERMSDispatcher(soc_min=10.0)
        action = MPCAction(peak_shave=True, peak_shave_kw=999.0)
        action.active_action_names.append("peak_shaving")
        result = dispatcher.dispatch(
            action=action,
            total_consumption=50.0,
            pv_power=5.0,
            battery_soc=12.0,
            battery_capacity=250.0,
            current_grid_power=45.0,
            current_p2p=0.0,
        )
        assert result.battery_soc_after >= 10.0

    def test_soc_never_above_max(self) -> None:
        dispatcher = DERMSDispatcher(soc_max=95.0)
        action = MPCAction(valley_fill=True, valley_fill_kw=999.0)
        action.active_action_names.append("valley_filling")
        result = dispatcher.dispatch(
            action=action,
            total_consumption=10.0,
            pv_power=50.0,
            battery_soc=93.0,
            battery_capacity=250.0,
            current_grid_power=-40.0,
            current_p2p=0.0,
        )
        assert result.battery_soc_after <= 95.0

    def test_discharge_positive_sign(self) -> None:
        dispatcher = DERMSDispatcher()
        action = MPCAction(peak_shave=True, peak_shave_kw=20.0)
        result = dispatcher.dispatch(
            action=action,
            total_consumption=40.0,
            pv_power=5.0,
            battery_soc=60.0,
            battery_capacity=250.0,
            current_grid_power=35.0,
            current_p2p=0.0,
        )
        assert result.battery_power > 0  # discharge is positive


class TestEnergyBalance:
    """The approximate energy-balance identity should hold."""

    def test_balance_simple_case(self) -> None:
        dispatcher = DERMSDispatcher()
        action = MPCAction(peak_shave=True, peak_shave_kw=10.0)
        result = dispatcher.dispatch(
            action=action,
            total_consumption=40.0,
            pv_power=5.0,
            battery_soc=60.0,
            battery_capacity=250.0,
            current_grid_power=25.0,
            current_p2p=0.0,
        )
        # Supply side = pv + battery_discharge + grid_import
        supply = 5.0 + max(result.battery_power, 0.0) + max(result.grid_power, 0.0)
        # Demand side = effective consumption (after shed)
        demand = 40.0 - result.shed_kw
        # Battery charge and grid export go on the demand side.
        demand += abs(min(result.battery_power, 0.0)) + abs(min(result.grid_power, 0.0))
        assert abs(supply - demand) < 1.0, (
            f"Energy balance violated: supply={supply}, demand={demand}"
        )
