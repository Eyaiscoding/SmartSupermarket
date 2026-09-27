"""
Layer 5 — Reliability & Compliance
====================================
Tags each appliance group with a criticality tier, verifies Tier 1 was
never interrupted across a full simulation run, and estimates the
ancillary-service value from peak-shaving actions.

Criticality Tiers
-----------------
* **Tier 1** (must never lose power):
  display_freezer_power, display_refrigerator_power,
  cold_room_power, freezer_room_power
* **Tier 2** (business-critical):
  checkout_power, it_power
* **Tier 3** (comfort):
  hvac_power
* **Tier 4** (non-essential):
  lighting_power, other_appliance_power
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Sequence

from src.mpc.coordinator import MPCAction


class CriticalityTier(IntEnum):
    TIER_1 = 1   # Refrigeration — NEVER shed
    TIER_2 = 2   # IT & Checkout
    TIER_3 = 3   # HVAC
    TIER_4 = 4   # Lighting & Other


# Map appliance column names to tiers.
APPLIANCE_TIER_MAP: dict[str, CriticalityTier] = {
    "display_freezer_power": CriticalityTier.TIER_1,
    "display_refrigerator_power": CriticalityTier.TIER_1,
    "cold_room_power": CriticalityTier.TIER_1,
    "freezer_room_power": CriticalityTier.TIER_1,
    "checkout_power": CriticalityTier.TIER_2,
    "it_power": CriticalityTier.TIER_2,
    "hvac_power": CriticalityTier.TIER_3,
    "lighting_power": CriticalityTier.TIER_4,
    "other_appliance_power": CriticalityTier.TIER_4,
}


@dataclass
class ComplianceReport:
    """Summary compliance report over a full simulation run."""

    total_timesteps: int
    tier_1_breaches: int       # Must be 0 for a valid run
    tier_1_protected: bool     # True iff tier_1_breaches == 0
    tier_2_shed_count: int
    tier_3_shed_count: int
    tier_4_shed_count: int
    peak_shave_count: int
    valley_fill_count: int
    load_shift_count: int
    hard_shed_count: int
    total_peak_shaved_kwh: float
    ancillary_value_estimate: float  # avoided cost €


class ComplianceChecker:
    """Accumulates per-timestep results and produces a compliance report."""

    # Rough avoided-cost rate for peak shaving (€/kWh).
    PEAK_SHAVE_VALUE_EUR_KWH: float = 0.15

    def __init__(self) -> None:
        self._tier_1_breaches: int = 0
        self._tier_2_sheds: int = 0
        self._tier_3_sheds: int = 0
        self._tier_4_sheds: int = 0
        self._peak_shave_count: int = 0
        self._valley_fill_count: int = 0
        self._load_shift_count: int = 0
        self._hard_shed_count: int = 0
        self._total_peak_shaved_kwh: float = 0.0
        self._n: int = 0

    def check_step(self, action: MPCAction) -> bool:
        """Record one timestep.  Returns ``True`` if Tier 1 is protected."""
        self._n += 1

        tier_1_ok = 1 not in action.hard_shed_tiers
        if not tier_1_ok:
            self._tier_1_breaches += 1

        if 2 in action.hard_shed_tiers:
            self._tier_2_sheds += 1
        if 3 in action.hard_shed_tiers:
            self._tier_3_sheds += 1
        if 4 in action.hard_shed_tiers:
            self._tier_4_sheds += 1

        if action.peak_shave:
            self._peak_shave_count += 1
            self._total_peak_shaved_kwh += action.peak_shave_kw * 0.25
        if action.valley_fill:
            self._valley_fill_count += 1
        if action.load_shift_hvac:
            self._load_shift_count += 1
        if action.hard_shed_kw > 0:
            self._hard_shed_count += 1

        return tier_1_ok

    def report(self) -> ComplianceReport:
        """Generate the final compliance report."""
        return ComplianceReport(
            total_timesteps=self._n,
            tier_1_breaches=self._tier_1_breaches,
            tier_1_protected=self._tier_1_breaches == 0,
            tier_2_shed_count=self._tier_2_sheds,
            tier_3_shed_count=self._tier_3_sheds,
            tier_4_shed_count=self._tier_4_sheds,
            peak_shave_count=self._peak_shave_count,
            valley_fill_count=self._valley_fill_count,
            load_shift_count=self._load_shift_count,
            hard_shed_count=self._hard_shed_count,
            total_peak_shaved_kwh=round(self._total_peak_shaved_kwh, 2),
            ancillary_value_estimate=round(
                self._total_peak_shaved_kwh * self.PEAK_SHAVE_VALUE_EUR_KWH, 2
            ),
        )

    @staticmethod
    def tier_for(appliance: str) -> CriticalityTier:
        """Look up the criticality tier for an appliance column name."""
        return APPLIANCE_TIER_MAP[appliance]
