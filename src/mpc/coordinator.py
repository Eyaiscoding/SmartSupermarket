"""
Layer 3 — MPC Coordination Core
=================================
A simplified receding-horizon controller.  At each timestep the controller
looks a few steps ahead using forecasted consumption/PV and selects the
combination of actions that minimises a composite cost function:

    cost = grid_import_cost
         + shedding_penalty  (weighted by criticality tier)
         + comfort_penalty   (for HVAC soft-shedding)

Actions available
-----------------
* **Peak shaving** — discharge battery instead of grid import when price
  is high.
* **Load shifting** — soft-shed HVAC when a demand-response event is active.
* **Valley filling** — pre-charge battery ahead of a forecasted PV dip.
* **Hard shedding** — cut Tier 4 → Tier 3 → Tier 2 loads (never Tier 1)
  if coverage ratio drops below a safety threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src.forecasting.flexibility import FlexBudget


# ── Tuning knobs ─────────────────────────────────────────────────────────────
PRICE_PEAK_THRESHOLD: float = 0.25    # €/kWh above which we peak-shave
COVERAGE_CRITICAL: float = 0.90       # below this → hard shedding kicks in
COVERAGE_AT_RISK: float = 0.95        # below this → coverage status = AT_RISK
HORIZON: int = 4                      # look-ahead steps (4 × 15 min = 1 h)

# Penalties per tier for shedding (higher = more expensive to shed).
TIER_SHED_PENALTY: dict[int, float] = {
    1: 1e9,   # effectively infinite — Tier 1 never shed
    2: 100.0,
    3: 10.0,
    4: 1.0,
}


@dataclass
class MPCAction:
    """The set of actions decided by the MPC for one timestep."""

    peak_shave: bool = False
    peak_shave_kw: float = 0.0

    load_shift_hvac: bool = False
    hvac_shed_kw: float = 0.0

    valley_fill: bool = False
    valley_fill_kw: float = 0.0

    hard_shed_tiers: list[int] = field(default_factory=list)
    hard_shed_kw: float = 0.0

    active_action_names: list[str] = field(default_factory=list)

    @property
    def total_battery_request_kw(self) -> float:
        """Net battery action: positive = discharge, negative = charge."""
        discharge = self.peak_shave_kw
        charge = self.valley_fill_kw
        return discharge - charge


class MPCCoordinator:
    """Simplified receding-horizon energy-management controller."""

    def __init__(
        self,
        price_peak_thresh: float = PRICE_PEAK_THRESHOLD,
        coverage_critical: float = COVERAGE_CRITICAL,
        horizon: int = HORIZON,
    ) -> None:
        self.price_peak_thresh = price_peak_thresh
        self.coverage_critical = coverage_critical
        self.horizon = horizon

    # ──────────────────────────────────────────────────────────────────────
    def decide(
        self,
        *,
        total_consumption: float,
        pv_power: float,
        battery_soc: float,
        battery_capacity: float,
        energy_price: float,
        demand_response: int,
        flex_budgets: list[FlexBudget],
        forecast_consumption: list[float],
        forecast_pv: list[float],
        forecast_prices: list[float],
    ) -> MPCAction:
        """Run one step of the MPC and return the decided action set.

        Parameters
        ----------
        total_consumption, pv_power, battery_soc, battery_capacity,
        energy_price, demand_response
            Current-timestep values read from the dataset / state.
        flex_budgets
            Output of ``FlexibilityEstimator.estimate()`` for this step.
        forecast_consumption, forecast_pv, forecast_prices
            Look-ahead vectors (length up to ``self.horizon``).
        """
        action = MPCAction()
        net_demand = total_consumption - pv_power  # kW still needed

        # ── 1. Peak shaving ──────────────────────────────────────────────
        if energy_price > self.price_peak_thresh and battery_soc > 20.0:
            # Discharge up to 50 kW or remaining demand, whichever is less.
            max_discharge = min(50.0, battery_capacity * (battery_soc - 10) / 100.0)
            discharge = min(max(net_demand, 0.0), max_discharge)
            if discharge > 0:
                action.peak_shave = True
                action.peak_shave_kw = discharge
                net_demand -= discharge
                action.active_action_names.append("peak_shaving")

        # ── 2. Load shifting (HVAC soft-shed on DR event) ────────────────
        if demand_response == 1:
            hvac_budget = next(
                (b for b in flex_budgets if b.group == "hvac"), None
            )
            if hvac_budget and hvac_budget.max_reduction_kw > 0:
                action.load_shift_hvac = True
                # Only shed 50% of HVAC during DR to reserve capacity for hard shedding
                action.hvac_shed_kw = hvac_budget.max_reduction_kw * 0.5
                net_demand -= action.hvac_shed_kw
                action.active_action_names.append("hvac_soft_shed")

        # ── 3. Valley filling ────────────────────────────────────────────
        # If upcoming PV is expected to dip and battery has room, pre-charge.
        if len(forecast_pv) >= 2:
            avg_future_pv = np.mean(forecast_pv)
            if avg_future_pv < pv_power * 0.5 and battery_soc < 80.0:
                # Charge at up to 25 kW.
                charge_room = battery_capacity * (90 - battery_soc) / 100.0
                charge_kw = min(25.0, charge_room)
                if charge_kw > 0:
                    action.valley_fill = True
                    action.valley_fill_kw = charge_kw
                    action.active_action_names.append("valley_filling")

        # ── 4. Hard shedding (coverage-based) ────────────────────────────
        supply = pv_power + max(action.peak_shave_kw, 0.0)
        coverage = supply / total_consumption if total_consumption > 0 else 1.0
        if coverage < self.coverage_critical and net_demand > 0:
            # Shed from Tier 4 upward, never touching Tier 1.
            remaining = net_demand
            for tier in [4, 3, 2]:
                if remaining <= 0:
                    break
                tier_budgets = [b for b in flex_budgets if b.tier == tier]
                for b in tier_budgets:
                    shed = min(b.max_reduction_kw, remaining)
                    if shed > 0:
                        remaining -= shed
                        action.hard_shed_kw += shed
                        if tier not in action.hard_shed_tiers:
                            action.hard_shed_tiers.append(tier)
            if action.hard_shed_kw > 0:
                action.active_action_names.append("hard_shedding")

        return action
