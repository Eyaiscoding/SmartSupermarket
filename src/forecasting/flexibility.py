"""
Layer 2c — Flexibility Quantification
=======================================
For each appliance group, estimates how much load can be shifted or reduced
and for how long without exceeding comfort or operational limits.

Rules
-----
* **Tier 1 — Refrigeration** (display_freezer, display_refrigerator,
  cold_room, freezer_room): **zero** flexibility.  These loads must never
  be shed or shifted.
* **Tier 2 — IT & Checkout** (checkout_power, it_power): very small
  flexibility (≤5 % reduction for ≤15 min) — modelled but almost never
  exercised.
* **Tier 3 — HVAC**: soft flexibility budget derived from thermal inertia.
  When indoor temperature is well within comfort bounds (18–26 °C) the HVAC
  can reduce by up to 50 % of its current power for up to 60 min before the
  zone drifts out of band.
* **Tier 4 — Lighting & Other**: high flexibility; can be shed entirely
  during a demand-response event.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FlexBudget:
    """How much a given appliance group can flex at this timestep."""

    group: str
    current_power_kw: float
    max_reduction_kw: float      # how much can be cut
    max_duration_min: float       # how long the cut can last
    tier: int


class FlexibilityEstimator:
    """Compute per-appliance-group flexibility budgets for one timestep."""

    # Comfort bounds for HVAC soft-shedding.
    COMFORT_TEMP_LOW: float = 18.0
    COMFORT_TEMP_HIGH: float = 26.0
    HVAC_MAX_SHED_FRACTION: float = 0.50
    HVAC_MAX_SHED_DURATION_MIN: float = 60.0

    # Tier 2 flex (very conservative).
    TIER2_MAX_SHED_FRACTION: float = 0.05
    TIER2_MAX_SHED_DURATION_MIN: float = 15.0

    def estimate(
        self,
        *,
        display_freezer_power: float,
        display_refrigerator_power: float,
        cold_room_power: float,
        freezer_room_power: float,
        hvac_power: float,
        lighting_power: float,
        checkout_power: float,
        it_power: float,
        other_appliance_power: float,
        temperature: float,
    ) -> list[FlexBudget]:
        budgets: list[FlexBudget] = []

        # ── Tier 1: Refrigeration — NO flexibility ───────────────────────
        for name, pwr in [
            ("display_freezer", display_freezer_power),
            ("display_refrigerator", display_refrigerator_power),
            ("cold_room", cold_room_power),
            ("freezer_room", freezer_room_power),
        ]:
            budgets.append(FlexBudget(name, pwr, 0.0, 0.0, tier=1))

        # ── Tier 2: IT & Checkout — minimal flexibility ──────────────────
        for name, pwr in [
            ("checkout", checkout_power),
            ("it", it_power),
        ]:
            budgets.append(
                FlexBudget(
                    name,
                    pwr,
                    pwr * self.TIER2_MAX_SHED_FRACTION,
                    self.TIER2_MAX_SHED_DURATION_MIN,
                    tier=2,
                )
            )

        # ── Tier 3: HVAC — soft flexibility from thermal inertia ────────
        if self.COMFORT_TEMP_LOW < temperature < self.COMFORT_TEMP_HIGH:
            # Margin from comfort edge → more margin = can shed longer.
            margin = min(
                temperature - self.COMFORT_TEMP_LOW,
                self.COMFORT_TEMP_HIGH - temperature,
            )
            frac = min(
                self.HVAC_MAX_SHED_FRACTION,
                margin / (self.COMFORT_TEMP_HIGH - self.COMFORT_TEMP_LOW) * 2,
            )
            duration = min(
                self.HVAC_MAX_SHED_DURATION_MIN,
                margin * 15.0,  # ~15 min per °C of margin
            )
        else:
            frac = 0.0
            duration = 0.0

        budgets.append(
            FlexBudget("hvac", hvac_power, hvac_power * frac, duration, tier=3)
        )

        # ── Tier 4: Lighting & Other — fully flexible ────────────────────
        for name, pwr in [
            ("lighting", lighting_power),
            ("other_appliance", other_appliance_power),
        ]:
            budgets.append(FlexBudget(name, pwr, pwr, 240.0, tier=4))

        return budgets
