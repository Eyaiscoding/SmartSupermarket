"""
Scenario Runner
================
Replays the full 4-month dataset through the six-layer B2G pipeline and
supports injecting synthetic stress scenarios on top of it for demo
purposes.

Stress scenarios
----------------
* **forced_grid_outage** -- sets grid_power to 0 for a span of timesteps.
* **price_spike** -- multiplies energy_price by a factor for a span.
* **sensor_corruption** -- sets temperature to NaN / extreme value for a span.

Usage::

    python scenario_runner.py                          # normal run
    python scenario_runner.py --scenario price_spike   # with stress test
    python scenario_runner.py --scenario all           # all stress tests
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

# Ensure the project root is on sys.path so that ``src`` is importable.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion import load_dataset
from src.forecasting import Forecaster, AnomalyDetector, FlexibilityEstimator
from src.mpc import MPCCoordinator
from src.mpc.coordinator import COVERAGE_AT_RISK
from src.derms import DERMSDispatcher
from src.compliance import (
    ComplianceChecker,
    cold_chain_temps,
    tier_1_demand_kw,
)
from src.api import OutputWriter, OutputRecord
from src.api.output import compute_coverage_status
from src.p2p.pipeline import NeighborMarket
from src.monitoring.temperature import TemperatureMonitor


# -- Stress-scenario injection ------------------------------------------------

def inject_grid_outage(
    df: pd.DataFrame,
    start_idx: int = 200,
    duration: int = 16,  # 4 hours
) -> pd.DataFrame:
    """Force grid_power to 0 for *duration* timesteps starting at *start_idx*."""
    df = df.copy()
    end = min(start_idx + duration, len(df))
    df.loc[start_idx:end - 1, "grid_power"] = 0.0
    print(f"  [stress] Grid outage injected at rows {start_idx}-{end - 1}")
    return df


def inject_price_spike(
    df: pd.DataFrame,
    start_idx: int = 500,
    duration: int = 8,
    factor: float = 5.0,
) -> pd.DataFrame:
    """Multiply energy_price by *factor* for a window."""
    df = df.copy()
    end = min(start_idx + duration, len(df))
    df.loc[start_idx:end - 1, "energy_price"] *= factor
    print(f"  [stress] Price spike (x{factor}) injected at rows {start_idx}-{end - 1}")
    return df


def inject_sensor_corruption(
    df: pd.DataFrame,
    start_idx: int = 1000,
    duration: int = 4,
) -> pd.DataFrame:
    """Set temperature to an extreme value to simulate a corrupt sensor."""
    df = df.copy()
    end = min(start_idx + duration, len(df))
    df.loc[start_idx:end - 1, "temperature"] = 99.0
    print(f"  [stress] Sensor corruption injected at rows {start_idx}-{end - 1}")
    return df


SCENARIOS: dict[str, callable] = {
    "forced_grid_outage": inject_grid_outage,
    "price_spike": inject_price_spike,
    "sensor_corruption": inject_sensor_corruption,
}


# -- Main pipeline ------------------------------------------------------------

def run_pipeline(
    df: pd.DataFrame,
    label: str = "normal",
    output_dir: Path | None = None,
) -> dict:
    """Execute the full six-layer pipeline on *df* and return a summary dict."""
    if output_dir is None:
        output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    n = len(df)
    market = NeighborMarket.for_run(df["timestamp"])
    temperature_monitor = TemperatureMonitor.from_env()
    print(f"\n{'='*60}")
    print(f"  Running pipeline: {label}  ({n} timesteps)")
    print(f"{'='*60}")

    # -- Layer 2: Forecasting & anomaly detection -----------------------------
    t0 = time.time()
    print("  [1/5] Training forecaster...")
    forecaster = Forecaster(n_estimators=100, max_depth=4)
    train_metrics = forecaster.train(df)
    _ = forecaster.predict(df)
    print(f"         Consumption MAE: {train_metrics['consumption_mae']:.3f} kW")
    print(f"         PV MAE:          {train_metrics['pv_mae']:.3f} kW")

    print("  [2/5] Training anomaly detector...")
    anomaly_det = AnomalyDetector()
    anomaly_det.train(df)
    anom_df = anomaly_det.detect(df)

    flex_est = FlexibilityEstimator()
    mpc = MPCCoordinator()
    dispatcher = DERMSDispatcher()
    checker = ComplianceChecker()
    writer = OutputWriter()

    print("  [3/5] Running MPC + DERMS dispatch...")
    battery_soc = float(df.iloc[0]["battery_soc"])
    battery_capacity = float(df.iloc[0]["battery_capacity"])

    for i in range(n):
        row = df.iloc[i]

        # Flexibility budgets.
        budgets = flex_est.estimate(
            display_freezer_power=float(row["display_freezer_power"]),
            display_refrigerator_power=float(row["display_refrigerator_power"]),
            cold_room_power=float(row["cold_room_power"]),
            freezer_room_power=float(row["freezer_room_power"]),
            hvac_power=float(row["hvac_power"]),
            lighting_power=float(row["lighting_power"]),
            checkout_power=float(row["checkout_power"]),
            it_power=float(row["it_power"]),
            other_appliance_power=float(row["other_appliance_power"]),
            temperature=float(row["temperature"]),
        )

        # Build look-ahead vectors (up to HORIZON steps).
        horizon = min(4, n - i - 1)
        if horizon > 0:
            fwd = df.iloc[i + 1 : i + 1 + horizon]
            fc_cons = fwd["forecast_consumption"].tolist()
            fc_pv = fwd["forecast_pv"].tolist()
            fc_price = fwd["energy_price"].tolist()
        else:
            fc_cons, fc_pv, fc_price = [], [], []

        # MPC decision.
        action = mpc.decide(
            total_consumption=float(row["total_consumption"]),
            pv_power=float(row["pv_power"]),
            battery_soc=battery_soc,
            battery_capacity=battery_capacity,
            energy_price=float(row["energy_price"]),
            demand_response=int(row["demand_response"]),
            flex_budgets=budgets,
            forecast_consumption=fc_cons,
            forecast_pv=fc_pv,
            forecast_prices=fc_price,
        )

        # DERMS dispatch.
        dispatch = dispatcher.dispatch(
            action=action,
            total_consumption=float(row["total_consumption"]),
            pv_power=float(row["pv_power"]),
            battery_soc=battery_soc,
            battery_capacity=battery_capacity,
            current_grid_power=float(row["grid_power"]),
            current_p2p=float(row["p2p_energy"]),
        )
        battery_soc = dispatch.battery_soc_after
        market_output = market.settle(row["timestamp"], dispatch.grid_power,
                                      float(row["energy_price"])) if market else {}

        # Compliance.
        supply = float(row["pv_power"]) + max(dispatch.battery_power, 0.0)
        supply += max(dispatch.grid_power, 0.0)
        tier_1_ok = checker.check_step(
            action,
            timestamp=str(row["timestamp"]),
            tier_1_demand_kw=tier_1_demand_kw(row),
            supply_kw=supply,
            battery_soc=battery_soc,
            battery_power_kw=dispatch.battery_power,
            cold_temps=cold_chain_temps(row),
        )

        # Coverage ratio.
        total_c = float(row["total_consumption"])
        coverage = supply / total_c if total_c > 0 else 1.0
        coverage = min(coverage, 1.0)

        # Anomaly info for this row.
        anomaly_flag = bool(anom_df.iloc[i].get("anomaly_flag", False))
        anomaly_source = (
            anomaly_det.identify_source(anom_df.iloc[i])
            if anomaly_flag
            else None
        )

        # Build output record.
        record_values = dict(
            timestamp=str(row["timestamp"]),
            coverage_ratio=round(coverage, 4),
            coverage_status=compute_coverage_status(coverage),
            active_actions=action.active_action_names,
            tier_1_protected=tier_1_ok,
            battery_soc=round(battery_soc, 2),
            grid_power=round(dispatch.grid_power, 2),
            p2p_energy=round(dispatch.p2p_energy, 2),
            anomaly_flag=anomaly_flag,
            anomaly_source=anomaly_source,
        )
        record_values.update(market_output)
        if market:
            record_values.update(demand_kw=max(float(row["total_consumption"]) - dispatch.shed_kw, 0),
                                 pv_power=float(row["pv_power"]))
        record_values.update(temperature_monitor.observe(row["timestamp"], row))
        record = OutputRecord(**record_values)
        writer.add(record)

    # -- Layer 5: Compliance report -------------------------------------------
    print("  [4/5] Generating compliance report...")
    report = checker.report()

    # -- Layer 6: Write output ------------------------------------------------
    json_path = output_dir / f"output_{label}.json"
    csv_path = output_dir / f"output_{label}.csv"
    writer.to_json(json_path)
    writer.to_csv(csv_path)

    # Full compliance report (violation log, counters, regulatory references).
    compliance_path = output_dir / f"compliance_{label}.json"
    compliance_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary = writer.summary()
    elapsed = time.time() - t0

    print("  [5/5] Done.")
    print(f"\n  -- Results ({label}) --")
    print(f"  Timesteps processed:       {report.total_timesteps}")
    print(f"  Tier 1 breaches:           {report.tier_1_breaches}")
    print(f"  Tier 1 always protected:   {report.tier_1_protected}")
    print(f"  Compliance status:         {report.overall_status} "
          f"(G/Y/R steps: {report.green_steps}/{report.yellow_steps}/{report.red_steps})")
    print(f"  Cascade-order warnings:    {report.cascade_order_warnings}")
    print(f"  Battery-limit warnings:    {report.battery_limit_warnings}")
    print(f"  Cold-chain breaches:       {report.cold_chain_breaches} "
          f"(monitored: {report.cold_chain_monitored})")
    print(f"  Peak-shave events:         {report.peak_shave_count}")
    print(f"  Valley-fill events:        {report.valley_fill_count}")
    print(f"  Load-shift (HVAC) events:  {report.load_shift_count}")
    print(f"  Hard-shed events:          {report.hard_shed_count}")
    print(f"  Total peak-shaved:         {report.total_peak_shaved_kwh:.1f} kWh")
    print(f"  Ancillary value estimate:  EUR {report.ancillary_value_estimate:.2f}")
    print(f"  Coverage ratio (mean):     {summary.get('coverage_ratio_mean', 'N/A')}")
    print(f"  Coverage ratio (min):      {summary.get('coverage_ratio_min', 'N/A')}")
    print(f"  Status Normal:             {summary.get('status_normal_pct', 'N/A')}%")
    print(f"  Status At-Risk:            {summary.get('status_at_risk_pct', 'N/A')}%")
    print(f"  Status Critical:           {summary.get('status_critical_pct', 'N/A')}%")
    print(f"  Anomalies flagged:         {summary.get('anomaly_count', 'N/A')}")
    print(f"  Elapsed time:              {elapsed:.1f}s")
    print(f"  Output files:              {json_path}")
    print(f"                             {csv_path}")
    print(f"                             {compliance_path}")

    return {
        "label": label,
        "compliance_report": report,
        "output_summary": summary,
        "train_metrics": train_metrics,
    }


# -- CLI ----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="B2G Smart Supermarket scenario runner"
    )
    parser.add_argument(
        "--scenario",
        choices=[*SCENARIOS.keys(), "all", "none"],
        default="none",
        help="Stress scenario to inject (default: none = normal run)",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="Path to dataset.csv (auto-detected if omitted)",
    )
    args = parser.parse_args()

    # Load dataset.
    print("Loading dataset...")
    df = load_dataset(path=args.dataset)
    print(f"  {len(df)} rows loaded, {df['timestamp'].min()} -> {df['timestamp'].max()}")

    # Normal run.
    results = [run_pipeline(df, label="normal")]

    # Stress scenarios.
    if args.scenario == "all":
        for name, fn in SCENARIOS.items():
            stressed = fn(df)
            results.append(run_pipeline(stressed, label=name))
    elif args.scenario != "none":
        fn = SCENARIOS[args.scenario]
        stressed = fn(df)
        results.append(run_pipeline(stressed, label=args.scenario))

    # Final summary.
    print(f"\n{'='*60}")
    print("  All runs complete.")
    for r in results:
        rpt = r["compliance_report"]
        print(f"  [{r['label']}] Tier-1 protected: {rpt.tier_1_protected}, "
              f"Peak-shaved: {rpt.total_peak_shaved_kwh:.0f} kWh, "
              f"Ancillary value: EUR {rpt.ancillary_value_estimate:.2f}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()