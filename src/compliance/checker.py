"""
Layer 5 — Reliability & Compliance
====================================
Tags each appliance group with a criticality tier, audits every simulation
step against a small set of explicit compliance rules (inspired by the
NFPA 70 / NEC "critical branch" principle: life-safety / critical loads are
never sacrificed), and estimates the ancillary-service value of peak shaving.

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

Compliance rules audited per step
---------------------------------
* **R1 — Tier 1 never shed**: the MPC must never request shedding of Tier 1.
  (breach -> RED)
* **R2 — Tier 1 physically supplied**: when supply data is provided, the
  available supply (PV + battery discharge + grid import) must cover the
  Tier 1 demand.  (breach -> RED)
* **R3 — Shedding cascade order**: loads are shed from the least critical
  tier first (4, then 3, then 2).  Shedding a more critical tier while a
  less critical one is spared is flagged.  (warning -> YELLOW)
* **R4 — Battery operating limits**: SOC within [soc_min, soc_max] and
  |power| <= max rate.  (warning -> YELLOW)
* **R5 — Cold chain**: when cabinet / cold-room temperature readings are
  provided, frozen units must stay at or below -18 C and chilled units at
  or below +4 C.  (breach -> RED)  Inactive if no readings are provided.
* **R6 — Tier 1 interruption duration**: not a pass/fail rule (no legal
  threshold is assumed); the longest uninterrupted Tier 1 breach is
  reported in minutes so the team can judge food-safety exposure.

Every rule is linked to its source in ``REGULATORY_REFERENCES`` (exposed in
``ComplianceReport.to_dict()``), with an explicit flag saying whether it is
simulated here, only a design-time check, or just an inspiration.

Per-step status
---------------
* ``GREEN``  — all rules satisfied, no Tier 2 shedding.
* ``YELLOW`` — Tier 1 safe, but Tier 2 was shed or a warning rule (R3/R4)
  was triggered.
* ``RED``    — Tier 1 is not protected (R1 or R2 breached).

``check_step(action)`` keeps its original signature and return value
(``True`` iff Tier 1 is protected).  The extra keyword arguments are
optional and enable the physical / battery rules.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import Enum, IntEnum
from typing import Any

from src.mpc.coordinator import MPCAction


class CriticalityTier(IntEnum):
    TIER_1 = 1   # Refrigeration — NEVER shed
    TIER_2 = 2   # IT & Checkout
    TIER_3 = 3   # HVAC
    TIER_4 = 4   # Lighting & Other


class ComplianceStatus(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


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

TIER_1_COLUMNS: list[str] = [
    col for col, t in APPLIANCE_TIER_MAP.items() if t == CriticalityTier.TIER_1
]

# Shedding order: least critical first.
SHED_CASCADE: tuple[int, ...] = (4, 3, 2)

# Battery limits (kept in sync with src/derms/dispatch.py).
BATTERY_SOC_MIN: float = 10.0
BATTERY_SOC_MAX: float = 95.0
BATTERY_MAX_RATE_KW: float = 50.0

# Time resolution of the dataset.
STEP_MINUTES: float = 15.0

# R5 — cold-chain temperature limits (deg C) per OPTIONAL temperature column.
# Limits: frozen <= -18 C, chilled <= +4 C (see REGULATORY_REFERENCES).
# The column names are a proposal: the current dataset has no cabinet
# temperature sensor, so R5 stays inactive until these columns exist.
COLD_CHAIN_LIMIT_C: dict[str, float] = {
    "display_freezer_temp": -18.0,
    "freezer_room_temp": -18.0,
    "display_refrigerator_temp": 4.0,
    "cold_room_temp": 4.0,
}
# Allowed excess above the limit before a step is flagged (deg C).
COLD_CHAIN_TOLERANCE_C: float = 0.0

# Traceability: which norm backs which rule, and how it is used here.
#   scope = "simulated"  -> checked by this module
#   scope = "design"     -> must be verified on the real installation
#   scope = "inspiration"-> conceptual basis only, not a legal claim
REGULATORY_REFERENCES: list[dict[str, str]] = [
    {
        "id": "R5_cold_chain_frozen",
        "scope": "simulated",
        "requirement": "Frozen food kept at -18 C or colder along the chain.",
        "source": "Codes of practice (e.g. Australian code, Codex/EU "
                  "positions); https://iifiir.org/en/fridoc/the-australian-"
                  "retail-grocery-cold-chain-18455",
    },
    {
        "id": "R5_cold_chain_chilled",
        "scope": "simulated",
        "requirement": "Chilled perishable food at +4 C or colder "
                       "(+2 C for minced meat in some codes; product-specific).",
        "source": "https://www.healthbureau.gov.hk/en/legco/replies/2016/"
                  "lq160622_q13.htm ; https://www.traqfood.com/en/blog-haccp-"
                  "method/haccp-measures/the-regulatory-obligations-of-the-"
                  "restaurateur/article/food-storage-temperatures",
    },
    {
        "id": "audit_trail",
        "scope": "simulated",
        "requirement": "Temperature records kept >= 1 year (EC 37/2005, "
                       "quick-frozen food); mirrored by the dated violation log.",
        "source": "https://www.legislation.gov.uk/cy/eur/2005/37/data.htm",
    },
    {
        "id": "R3_shedding_order",
        "scope": "inspiration",
        "requirement": "Load shedding is addressed in NEC (Art. 750.30 cited "
                       "in microgrid guidance); the 4->3->2 cascade is a "
                       "project design choice.",
        "source": "https://eaton.com/content/dam/eaton/services/eess/eess-"
                  "documents/eaton_microgrid_codes_standards_whitepaper_"
                  "WP180003EN.pdf",
    },
    {
        "id": "tier_hierarchy",
        "scope": "inspiration",
        "requirement": "NEC Art. 700/701/702 distinguish emergency, legally "
                       "required and optional standby systems. Refrigeration "
                       "is justified by cold-chain rules, not by NEC life-safety.",
        "source": "NFPA 70 (NEC), Art. 700-702",
    },
    {
        "id": "battery_ess_design",
        "scope": "design",
        "requirement": "ESS > 1 kWh: NEC Art. 706, UL 9540 listing, NFPA 855 "
                       "siting/spacing/ventilation; IEEE 1547 for DER "
                       "interconnection.",
        "source": "https://expertce.com/learn-articles/nec-rules-pv-energy-"
                  "storage-article-706/",
    },
    {
        "id": "tunisia_grid_connection",
        "scope": "design",
        "requirement": "Law 2015-12, decree 2016-1123 (rev. 2020-105) and the "
                       "9 Feb 2017 STEG grid-code decisions (LV and HV/MV). "
                       "Applicability to a supermarket (LV vs MV) and to "
                       "battery storage must be confirmed with STEG.",
        "source": "https://rise.esmap.org/data/files/library/tunisia/"
                  "Renewable Energy/Tunisia_Law N°2015-12 Renewable energy "
                  "-Fr.pdf",
    },
]


def cold_chain_temps(row: Any) -> dict[str, float] | None:
    """Collect the optional cabinet temperature readings of a dataset row.

    Returns ``None`` when the row has none of the expected columns, which
    keeps rule R5 inactive on the current dataset.
    """
    temps = {
        col: float(row[col]) for col in COLD_CHAIN_LIMIT_C if col in row
    }
    return temps or None


# Max number of individual violations stored PER RULE in the report log.
# The cap is per rule so that frequent low-severity warnings (e.g. R3) can
# never crowd out rare but critical ones (e.g. R1/R2/R5).  The counters in
# ``violation_counts`` always stay exact.
MAX_LOGGED_PER_RULE: int = 50


def tier_1_demand_kw(row: Any) -> float:
    """Sum the Tier 1 appliance columns of a dataset row (kW)."""
    return float(sum(float(row[c]) for c in TIER_1_COLUMNS))


@dataclass
class Violation:
    """One rule violation, kept for the audit trail."""

    step: int
    timestamp: str | None
    rule: str
    severity: str     # "RED" or "YELLOW"
    detail: str


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
    # --- audit extensions (all optional / defaulted) ---------------------
    physical_tier_1_breaches: int = 0       # R2
    cascade_order_warnings: int = 0         # R3
    battery_limit_warnings: int = 0         # R4
    green_steps: int = 0
    yellow_steps: int = 0
    red_steps: int = 0
    overall_status: str = "GREEN"
    violations: list[Violation] = field(default_factory=list)
    cold_chain_breaches: int = 0            # R5 (0 if no sensor data)
    cold_chain_monitored: bool = False      # were temperatures provided?
    longest_cold_chain_breach_min: float = 0.0
    longest_tier_1_breach_min: float = 0.0  # R6
    violation_counts: dict[str, int] = field(default_factory=dict)

    @property
    def compliance_rate(self) -> float:
        """Share of steps that are not RED (1.0 = fully compliant)."""
        if self.total_timesteps == 0:
            return 1.0
        return round(1.0 - self.red_steps / self.total_timesteps, 6)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable form, ready for the API / dashboard."""
        d = asdict(self)
        d["compliance_rate"] = self.compliance_rate
        d["regulatory_references"] = REGULATORY_REFERENCES
        return d


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
        # audit extensions
        self._physical_breaches: int = 0
        self._cascade_warnings: int = 0
        self._battery_warnings: int = 0
        self._green: int = 0
        self._yellow: int = 0
        self._red: int = 0
        self._violations: list[Violation] = []
        self._violation_counts: dict[str, int] = {}
        self._cold_breaches: int = 0
        self._cold_monitored: bool = False
        self._cold_run: int = 0
        self._cold_longest: int = 0
        self._t1_run: int = 0
        self._t1_longest: int = 0
        self.last_status: ComplianceStatus = ComplianceStatus.GREEN

    # ------------------------------------------------------------------
    def _log(self, rule: str, severity: str, detail: str,
             timestamp: str | None) -> None:
        n = self._violation_counts.get(rule, 0)
        self._violation_counts[rule] = n + 1
        if n < MAX_LOGGED_PER_RULE:
            self._violations.append(
                Violation(self._n, timestamp, rule, severity, detail)
            )

    def check_step(
        self,
        action: MPCAction,
        *,
        timestamp: str | None = None,
        tier_1_demand_kw: float | None = None,
        supply_kw: float | None = None,
        battery_soc: float | None = None,
        battery_power_kw: float | None = None,
        cold_temps: Mapping[str, float] | None = None,
    ) -> bool:
        """Record one timestep.  Returns ``True`` if Tier 1 is protected.

        Only ``action`` is required.  Passing ``tier_1_demand_kw`` and
        ``supply_kw`` enables rule R2; passing ``battery_soc`` /
        ``battery_power_kw`` enables rule R4; passing ``cold_temps`` (column name
        -> deg C, see ``cold_chain_temps``) enables rule R5.
        """
        self._n += 1
        red = False
        yellow = False

        # R1 — Tier 1 never shed by the MPC.
        tier_1_ok = 1 not in action.hard_shed_tiers
        if not tier_1_ok:
            self._tier_1_breaches += 1
            red = True
            self._log("R1_tier1_shed", "RED",
                      "MPC requested shedding of Tier 1 loads", timestamp)

        # R2 — Tier 1 physically supplied.
        if (
            tier_1_demand_kw is not None
            and supply_kw is not None
            and supply_kw + 1e-9 < tier_1_demand_kw
        ):
            self._physical_breaches += 1
            red = True
            tier_1_ok = False
            self._log(
                "R2_tier1_unsupplied", "RED",
                f"supply {supply_kw:.2f} kW < Tier 1 demand "
                f"{tier_1_demand_kw:.2f} kW", timestamp,
            )

        # R5 — cold chain (only when temperature readings are provided).
        if cold_temps:
            self._cold_monitored = True
            too_warm = {
                col: t for col, t in cold_temps.items()
                if col in COLD_CHAIN_LIMIT_C
                and t > COLD_CHAIN_LIMIT_C[col] + COLD_CHAIN_TOLERANCE_C
            }
            if too_warm:
                self._cold_breaches += 1
                self._cold_run += 1
                self._cold_longest = max(self._cold_longest, self._cold_run)
                red = True
                self._log(
                    "R5_cold_chain", "RED",
                    "; ".join(
                        f"{c}={t:.1f}C > {COLD_CHAIN_LIMIT_C[c]:.0f}C"
                        for c, t in too_warm.items()
                    ), timestamp,
                )
            else:
                self._cold_run = 0

        # R6 — track how long Tier 1 stays in breach (not pass/fail).
        if tier_1_ok:
            self._t1_run = 0
        else:
            self._t1_run += 1
            self._t1_longest = max(self._t1_longest, self._t1_run)

        # Shed counters per tier.
        shed = set(action.hard_shed_tiers)
        if 2 in shed:
            self._tier_2_sheds += 1
            yellow = True
        if 3 in shed:
            self._tier_3_sheds += 1
        if 4 in shed:
            self._tier_4_sheds += 1

        # R3 — cascade order: shedding tier t while a less critical tier
        # (t+1 .. 4) is spared is out of order.
        for t in SHED_CASCADE:
            if t in shed:
                spared = [u for u in SHED_CASCADE if u > t and u not in shed]
                if spared:
                    self._cascade_warnings += 1
                    yellow = True
                    self._log(
                        "R3_cascade_order", "YELLOW",
                        f"Tier {t} shed while Tier {spared} not shed",
                        timestamp,
                    )
                    break

        # R4 — battery operating limits.
        if battery_soc is not None and not (
            BATTERY_SOC_MIN - 1e-6 <= battery_soc <= BATTERY_SOC_MAX + 1e-6
        ):
            self._battery_warnings += 1
            yellow = True
            self._log("R4_battery_soc", "YELLOW",
                      f"SOC {battery_soc:.1f}% outside "
                      f"[{BATTERY_SOC_MIN}, {BATTERY_SOC_MAX}]", timestamp)
        if battery_power_kw is not None and (
            abs(battery_power_kw) > BATTERY_MAX_RATE_KW + 1e-6
        ):
            self._battery_warnings += 1
            yellow = True
            self._log("R4_battery_rate", "YELLOW",
                      f"|battery power| {abs(battery_power_kw):.1f} kW > "
                      f"{BATTERY_MAX_RATE_KW} kW", timestamp)

        # Other action counters.
        if action.peak_shave:
            self._peak_shave_count += 1
            self._total_peak_shaved_kwh += action.peak_shave_kw * 0.25
        if action.valley_fill:
            self._valley_fill_count += 1
        if action.load_shift_hvac:
            self._load_shift_count += 1
        if action.hard_shed_kw > 0:
            self._hard_shed_count += 1

        # Per-step status.
        if red:
            self._red += 1
            self.last_status = ComplianceStatus.RED
        elif yellow:
            self._yellow += 1
            self.last_status = ComplianceStatus.YELLOW
        else:
            self._green += 1
            self.last_status = ComplianceStatus.GREEN

        return tier_1_ok

    def report(self) -> ComplianceReport:
        """Generate the final compliance report."""
        if self._red > 0:
            overall = ComplianceStatus.RED
        elif self._yellow > 0:
            overall = ComplianceStatus.YELLOW
        else:
            overall = ComplianceStatus.GREEN

        return ComplianceReport(
            total_timesteps=self._n,
            tier_1_breaches=self._tier_1_breaches + self._physical_breaches,
            tier_1_protected=(
                self._tier_1_breaches + self._physical_breaches == 0
            ),
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
            physical_tier_1_breaches=self._physical_breaches,
            cascade_order_warnings=self._cascade_warnings,
            battery_limit_warnings=self._battery_warnings,
            green_steps=self._green,
            yellow_steps=self._yellow,
            red_steps=self._red,
            overall_status=overall.value,
            violations=list(self._violations),
            cold_chain_breaches=self._cold_breaches,
            cold_chain_monitored=self._cold_monitored,
            longest_cold_chain_breach_min=self._cold_longest * STEP_MINUTES,
            longest_tier_1_breach_min=self._t1_longest * STEP_MINUTES,
            violation_counts=dict(self._violation_counts),
        )

    @staticmethod
    def tier_for(appliance: str) -> CriticalityTier:
        """Look up the criticality tier for an appliance column name."""
        return APPLIANCE_TIER_MAP[appliance]
