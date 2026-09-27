"""
Layer 4 — DERMS Dispatch
=========================
Executes the MPC core's decision: computes actual ``battery_power``,
``grid_power``, and ``p2p_energy`` for the step, respecting battery SOC
limits and charge/discharge power limits.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.mpc.coordinator import MPCAction


# ── Battery physical limits ──────────────────────────────────────────────────
BATTERY_MAX_CHARGE_KW: float = 50.0      # max charge rate (kW)
BATTERY_MAX_DISCHARGE_KW: float = 50.0   # max discharge rate (kW)
BATTERY_SOC_MIN: float = 10.0            # % — never discharge below this
BATTERY_SOC_MAX: float = 95.0            # % — never charge above this


@dataclass
class DispatchResult:
    """Physical dispatch values for one timestep."""

    battery_power: float    # positive = discharge, negative = charge
    grid_power: float       # positive = import, negative = export
    p2p_energy: float       # positive = import, negative = export
    shed_kw: float          # total load shed in this step
    battery_soc_after: float


class DERMSDispatcher:
    """Translate MPC actions into physically feasible dispatch commands."""

    def __init__(
        self,
        max_charge_kw: float = BATTERY_MAX_CHARGE_KW,
        max_discharge_kw: float = BATTERY_MAX_DISCHARGE_KW,
        soc_min: float = BATTERY_SOC_MIN,
        soc_max: float = BATTERY_SOC_MAX,
    ) -> None:
        self.max_charge_kw = max_charge_kw
        self.max_discharge_kw = max_discharge_kw
        self.soc_min = soc_min
        self.soc_max = soc_max

    def dispatch(
        self,
        *,
        action: MPCAction,
        total_consumption: float,
        pv_power: float,
        battery_soc: float,
        battery_capacity: float,
        current_grid_power: float,
        current_p2p: float,
    ) -> DispatchResult:
        """Compute physically-clamped dispatch.

        Parameters
        ----------
        action : MPCAction
            Decision from the MPC coordinator.
        total_consumption, pv_power, battery_soc, battery_capacity
            Current state values.
        current_grid_power, current_p2p
            Baseline grid and P2P values from the dataset (used as
            fallback / starting point).
        """

        # ── Battery action ───────────────────────────────────────────────
        raw_battery = action.total_battery_request_kw  # +discharge, -charge
        battery_power = self._clamp_battery(
            raw_battery, battery_soc, battery_capacity
        )

        # ── Load shedding ────────────────────────────────────────────────
        shed_kw = action.hvac_shed_kw + action.hard_shed_kw

        # ── Energy balance: what the grid must supply ────────────────────
        effective_consumption = total_consumption - shed_kw
        residual = effective_consumption - pv_power - battery_power
        # residual > 0 → need grid import; < 0 → can export.
        grid_power = residual

        # P2P: keep the dataset's value (the P2P market logic is external).
        p2p_energy = current_p2p

        # ── SOC update (simplified linear model) ─────────────────────────
        # Energy in kWh this 15-min interval.
        energy_kwh = battery_power * 0.25  # 15 min = 0.25 h
        soc_delta_pct = (energy_kwh / battery_capacity) * 100.0 if battery_capacity > 0 else 0.0
        soc_after = battery_soc - soc_delta_pct  # discharge lowers SOC
        soc_after = max(self.soc_min, min(self.soc_max, soc_after))

        return DispatchResult(
            battery_power=round(battery_power, 3),
            grid_power=round(grid_power, 3),
            p2p_energy=round(p2p_energy, 3),
            shed_kw=round(shed_kw, 3),
            battery_soc_after=round(soc_after, 2),
        )

    # ── Internal helpers ─────────────────────────────────────────────────
    def _clamp_battery(
        self,
        requested: float,
        soc: float,
        capacity: float,
    ) -> float:
        """Clamp the battery request to physical limits."""
        if requested > 0:
            # Discharge: can't go below SOC min.
            max_energy = capacity * (soc - self.soc_min) / 100.0  # kWh
            max_power = max_energy / 0.25  # over 15 min
            clamped = min(requested, self.max_discharge_kw, max(max_power, 0.0))
        else:
            # Charge: can't go above SOC max.
            room_kwh = capacity * (self.soc_max - soc) / 100.0
            max_power = room_kwh / 0.25
            clamped = max(requested, -self.max_charge_kw, -max(max_power, 0.0))
        return clamped
