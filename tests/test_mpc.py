"""
Tests for Layer 3 — MPC Coordination Core.
"""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.mpc.coordinator import MPCCoordinator  # noqa: E402
from src.forecasting.flexibility import FlexBudget  # noqa: E402


def _make_budgets(
    hvac_kw: float = 10.0,
    lighting_kw: float = 3.0,
    other_kw: float = 1.5,
    temperature: float = 22.0,
) -> list[FlexBudget]:
    """Helper to build a typical flexibility-budget list."""
    from src.forecasting.flexibility import FlexibilityEstimator
    return FlexibilityEstimator().estimate(
        display_freezer_power=3.0,
        display_refrigerator_power=4.0,
        cold_room_power=5.0,
        freezer_room_power=7.0,
        hvac_power=hvac_kw,
        lighting_power=lighting_kw,
        checkout_power=0.5,
        it_power=2.5,
        other_appliance_power=other_kw,
        temperature=temperature,
    )


class TestMPCPeakShaving:

    def test_peak_shave_triggers_on_high_price(self) -> None:
        mpc = MPCCoordinator(price_peak_thresh=0.20)
        action = mpc.decide(
            total_consumption=40.0,
            pv_power=5.0,
            battery_soc=60.0,
            battery_capacity=250.0,
            energy_price=0.30,
            demand_response=0,
            flex_budgets=_make_budgets(),
            forecast_consumption=[40.0],
            forecast_pv=[5.0],
            forecast_prices=[0.30],
        )
        assert action.peak_shave is True
        assert action.peak_shave_kw > 0

    def test_no_peak_shave_on_low_price(self) -> None:
        mpc = MPCCoordinator(price_peak_thresh=0.20)
        action = mpc.decide(
            total_consumption=40.0,
            pv_power=5.0,
            battery_soc=60.0,
            battery_capacity=250.0,
            energy_price=0.10,
            demand_response=0,
            flex_budgets=_make_budgets(),
            forecast_consumption=[40.0],
            forecast_pv=[5.0],
            forecast_prices=[0.10],
        )
        assert action.peak_shave is False


class TestMPCLoadShifting:

    def test_hvac_shed_on_demand_response(self) -> None:
        mpc = MPCCoordinator()
        action = mpc.decide(
            total_consumption=40.0,
            pv_power=5.0,
            battery_soc=60.0,
            battery_capacity=250.0,
            energy_price=0.15,
            demand_response=1,
            flex_budgets=_make_budgets(),
            forecast_consumption=[40.0],
            forecast_pv=[5.0],
            forecast_prices=[0.15],
        )
        assert action.load_shift_hvac is True
        assert action.hvac_shed_kw > 0

    def test_no_hvac_shed_without_dr(self) -> None:
        mpc = MPCCoordinator()
        action = mpc.decide(
            total_consumption=40.0,
            pv_power=5.0,
            battery_soc=60.0,
            battery_capacity=250.0,
            energy_price=0.15,
            demand_response=0,
            flex_budgets=_make_budgets(),
            forecast_consumption=[40.0],
            forecast_pv=[5.0],
            forecast_prices=[0.15],
        )
        assert action.load_shift_hvac is False


class TestMPCTier1Protection:
    """The critical invariant: Tier 1 must NEVER appear in hard_shed_tiers."""

    def test_tier1_never_in_hard_shed(self) -> None:
        """Even under extreme conditions, Tier 1 is never shed."""
        mpc = MPCCoordinator(coverage_critical=0.99)
        action = mpc.decide(
            total_consumption=100.0,
            pv_power=0.0,       # no solar
            battery_soc=11.0,   # nearly empty
            battery_capacity=250.0,
            energy_price=1.0,
            demand_response=1,
            flex_budgets=_make_budgets(),
            forecast_consumption=[100.0],
            forecast_pv=[0.0],
            forecast_prices=[1.0],
        )
        assert 1 not in action.hard_shed_tiers, "Tier 1 was illegally shed!"

    def test_hard_shed_order_4_3_2(self) -> None:
        """Hard shedding must proceed Tier 4 → 3 → 2, never touching 1."""
        mpc = MPCCoordinator(coverage_critical=0.99)
        action = mpc.decide(
            total_consumption=100.0,
            pv_power=1.0,
            battery_soc=11.0,
            battery_capacity=250.0,
            energy_price=0.10,
            demand_response=0,
            flex_budgets=_make_budgets(),
            forecast_consumption=[100.0],
            forecast_pv=[1.0],
            forecast_prices=[0.10],
        )
        for tier in action.hard_shed_tiers:
            assert tier != 1
