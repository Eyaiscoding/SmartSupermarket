# Coding agent prompt — Smart Supermarket B2G backend

Paste everything below into your coding agent (Claude Code or similar).

---

## Context

We are building a **Building-to-Grid (B2G) simulation** for a smart supermarket connected to a local microgrid and, through it, to the macrogrid. The supermarket consumes grid electricity, produces solar PV, stores energy in a battery, and can trade energy peer-to-peer (P2P) with other participants. The system must continuously guarantee **reliable electrical coverage** of the building while respecting a **priority/criticality hierarchy** on its loads (refrigeration must never lose power; lighting can).

You are implementing the **backend simulation engine** only — a layered pipeline that reads the dataset, runs AI forecasting, makes coordinated energy-management decisions, dispatches the DERs (battery/PV/grid/P2P), checks compliance, and exposes a clean output for a separate dashboard (built by someone else, out of scope here) to consume.

### Dataset

- File: `dataset.csv`, already provided in this project, at the repo root (or wherever it currently sits — locate it first).
- Synthetic, 15-minute resolution, 1 June – 30 September 2025 (4 months), **11,712 rows**, **30 columns**.
- Columns cover: site context (`occupancy`, `temperature`, `humidity`, `solar_irradiance`), PV (`pv_voltage`, `pv_current`, `pv_power`), total + per-appliance consumption (`total_consumption`, `display_freezer_power`, `display_refrigerator_power`, `cold_room_power`, `freezer_room_power`, `hvac_power`, `lighting_power`, `checkout_power`, `it_power`, `other_appliance_power`), battery (`battery_voltage`, `battery_current`, `battery_capacity`, `battery_soc`, `battery_power`), grid & market (`grid_power`, `energy_price`, `demand_response`, `p2p_energy`), forecasts (`forecast_consumption`, `forecast_pv`), and `anomaly_score`.
- Sign conventions: `battery_power` positive = discharge, negative = charge. `grid_power` positive = import, negative = export.
- Energy balance identity that should approximately hold at every timestamp: `pv_power + grid_import + battery_discharge + p2p_import ≈ total_consumption + battery_charge + grid_export + p2p_export`.

### Architecture to implement

Implement these six layers as separate, clearly-separated Python modules (not one monolithic script):

1. **Data ingestion layer** — loads `dataset.csv`, validates schema/types, handles missing values, exposes a clean per-timestamp state object/dataclass.
2. **AI forecasting & flexibility layer** —
   - Forecasting: train/use a simple model (gradient boosting or similar — no need for deep learning) to predict next-step consumption and PV, validate against the dataset's own `forecast_consumption`/`forecast_pv` columns.
   - Anomaly detection: a lightweight model (e.g. Isolation Forest or a z-score/rolling-statistics baseline) producing an anomaly signal, compared against the dataset's `anomaly_score`.
   - Flexibility quantification: for each appliance group, estimate how much load can be shifted/reduced and for how long without exceeding comfort/operational limits (HVAC gets a soft flexibility budget from thermal inertia; refrigeration gets none).
3. **MPC coordination core** — a simplified receding-horizon controller. At each timestep, look ahead over the next few forecasted steps and pick the action that minimizes a cost function combining: grid import cost (`energy_price`), a shedding penalty (weighted by criticality tier), and a comfort penalty (for HVAC soft-shedding). The action set is: **peak shaving** (discharge battery instead of importing when price is high), **load shifting** (soft-shed HVAC when a demand-response event is active), **valley filling** (pre-charge battery ahead of a forecasted PV dip), and **hard shedding** (cut Tier 4 then Tier 3 then Tier 2 if coverage ratio drops below a threshold — Tier 1 is never touched).
4. **DERMS dispatch layer** — executes the MPC core's decision: computes actual `battery_power`, `grid_power`, `p2p_energy` for the step, respecting battery SOC limits and charge/discharge power limits.
5. **Reliability & compliance layer** — tags each appliance group with a criticality tier (Tier 1: `display_freezer_power`, `display_refrigerator_power`, `cold_room_power`, `freezer_room_power`; Tier 2: `checkout_power`, `it_power`; Tier 3: `hvac_power`; Tier 4: `lighting_power`, `other_appliance_power`). After a full run, verifies Tier 1 was never interrupted, and computes a simple ancillary-service value estimate (e.g. avoided peak-demand cost from peak-shaving actions taken).
6. **Visualization & API layer** — not a full frontend. Just expose the per-timestep output as a clean, documented JSON/CSV stream (one file or a simple local API, your choice) with this shape:

```json
{
  "timestamp": "...",
  "coverage_ratio": 0.94,
  "coverage_status": "AT_RISK",
  "active_actions": ["hvac_soft_shed"],
  "tier_1_protected": true,
  "battery_soc": 62.3,
  "grid_power": 12.4,
  "p2p_energy": 0,
  "anomaly_flag": false,
  "anomaly_source": null
}
```

## Implementation steps

1. Explore the repo/working directory, locate `dataset.csv`, inspect its shape and columns, confirm it matches the description above (flag any discrepancy instead of silently adapting).
2. Set up a Python project: virtual environment, `requirements.txt` (pandas, numpy, scikit-learn, and anything else genuinely needed — keep dependencies minimal).
3. Implement the six layers as separate modules under a clear package structure (e.g. `src/ingestion/`, `src/forecasting/`, `src/mpc/`, `src/derms/`, `src/compliance/`, `src/api/`).
4. Implement a `scenario_runner.py` (or similar) that replays the full 4-month dataset through the pipeline and also supports injecting synthetic stress scenarios on top of it (forced grid outage, artificial price spike, corrupted sensor reading) for demo purposes.
5. Write unit tests for each layer (pytest), especially: the energy-balance identity, the Tier 1 protection invariant, and the MPC action-selection logic under known synthetic inputs.
6. Run the full pipeline once end-to-end over the dataset and sanity-check the output (coverage ratio distribution, how often each action fires, whether Tier 1 was ever breached).
7. Write the README (see requirements below).
8. Initialize git, commit, and push to GitHub (see below).

## README requirements

Write a comprehensive `README.md` at the repo root including:
- Project description and what problem it solves (one paragraph, plain language)
- Architecture section with the six layers, one paragraph each, matching the design in b2g_general_architecture.png (attach the picture too)
- Dataset section: description of `dataset.csv`, its schema, and where it lives in the repo
- **Papers/sources used**, listed explicitly (do not paraphrase into generic citations, use these exact titles):
  - *Building to Grid* — Guidehouse, 2019
  - *Emerging Microgrid Business Models* — Navigant, 2016
  - *Microgrids – Critical Facilities* — Navigant, 2019
  - *Buildings-to-Grid Technical Opportunities: From the Grid Perspective* — DOE/NREL/PNNL, 2014
  - *A Comprehensive Review of Building-to-Grid Interaction* — Energy Use, 2026
  - *Buildings-to-Grid Integration Framework* — IEEE Transactions on Smart Grid, 2017 (Taha et al.)
  - *Thermal storage capacity in the entire building stock of Denmark for energy flexibility strategies and building-to-grid services* — REHVA European HVAC Journal, 2024
  - *Data-Driven Analytics for Reliability in the Buildings-to-Grid Integrated System Framework* — IEEE Access, 2023 (Bachoumis et al.)
  - For each paper, one sentence on which specific design decision it justifies (e.g. "the peak shaving / load shifting / valley filling action set is taken from the Denmark thermal-storage paper").
- **Tools/tech stack used**, listed explicitly (Python version, pandas, scikit-learn, etc. — whatever you actually end up using)
- Setup & run instructions (clone, install, run the pipeline, run tests)
- Output contract documentation (the JSON schema above, field by field)
- A short "Team & scope" note stating this repo covers the backend simulation engine only; the dashboard and compliance reporting layers are built separately by other team members and consume this module's output contract.

## Dataset & GitHub handling

- Check the size of `dataset.csv` first (`ls -lh dataset.csv` or equivalent).
- If it's under ~50MB, commit it directly into the repo under a `data/` folder — this dataset is small and synthetic, there's no privacy/licensing reason to exclude it.
- If for any reason it's larger than expected, don't fight it silently — tell me the size and ask whether to use Git LFS or truncate a sample for the repo (keeping the full file elsewhere).
- Initialize a git repository if one doesn't exist yet, add a sensible `.gitignore` (venv, `__pycache__`, `.env`, etc. — **not** the dataset), commit everything with a clear message.
- If the GitHub CLI (`gh`) is authenticated in this environment, create the repository and push directly. If it isn't, stop and give me the exact commands to run myself (`gh repo create`, `git remote add origin ...`, `git push -u origin main`) rather than guessing at credentials.

## What NOT to do

- Don't implement a full frontend/dashboard — that's someone else's part.
- Don't implement the actual power-flow/DAE math from the Taha et al. MPC paper — we deliberately use a simplified receding-horizon heuristic inspired by it, not the full optimization.
- Don't silently drop the Tier 1 protection rule under any circumstance, even during a hard-shedding scenario — that invariant must hold in every test and every scenario run.
