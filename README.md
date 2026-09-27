# Smart Supermarket B2G Simulation Engine

A Building-to-Grid (B2G) backend simulation engine for a smart supermarket connected to a local microgrid and, through it, to the macrogrid. The system models how a supermarket consumes grid electricity, produces solar PV, stores energy in a battery, and can trade energy peer-to-peer (P2P) with other participants -- all while continuously guaranteeing reliable electrical coverage of the building and respecting a strict priority/criticality hierarchy on its loads (refrigeration must never lose power, even if lighting is shed first).

---

## Architecture

![B2G General Architecture](b2g_general_architecture.png)

The simulation engine is organized into six clearly separated layers, each implemented as its own Python module under `src/`:

### 1. Data Ingestion Layer (`src/ingestion/`)

Loads the synthetic dataset (`data/dataset.csv`), validates the schema and column types against the expected 30-column specification, handles missing values via forward-fill/back-fill, and exposes a clean per-timestamp dataclass (`TimestepState`) that all downstream layers consume. This layer ensures that any schema drift or data corruption is caught early, before the pipeline begins processing.

### 2. AI Forecasting & Flexibility Layer (`src/forecasting/`)

This layer contains three sub-modules:
- **Forecaster** (`forecaster.py`): Trains a gradient-boosting regressor (scikit-learn) to predict next-step total consumption and PV generation using calendar features (hour, day-of-week), weather context, and lagged values. Predictions are validated against the dataset's own `forecast_consumption` and `forecast_pv` columns.
- **Anomaly Detector** (`anomaly.py`): Uses an Isolation Forest model to produce a normalised anomaly score for each timestep, compared against the dataset's `anomaly_score`. Includes a heuristic source-attribution method that identifies the most deviant feature.
- **Flexibility Estimator** (`flexibility.py`): For each appliance group, computes how much load can be shifted or reduced and for how long. Refrigeration (Tier 1) gets zero flexibility; HVAC (Tier 3) gets a soft budget derived from thermal inertia and current temperature margin; Lighting and Other (Tier 4) can be shed entirely.

### 3. MPC Coordination Core (`src/mpc/`)

A simplified receding-horizon controller inspired by the Taha et al. IEEE framework. At each timestep, the controller looks up to 4 steps ahead (1 hour at 15-min resolution) and selects the combination of actions that minimizes a composite cost: grid import cost (weighted by `energy_price`), a shedding penalty (weighted by criticality tier, with Tier 1 at effectively infinite cost), and a comfort penalty for HVAC soft-shedding. The action set includes: peak shaving (battery discharge during high prices), load shifting (HVAC reduction during demand-response events), valley filling (battery pre-charge ahead of PV dips), and hard shedding (Tier 4, then 3, then 2 -- never Tier 1).

### 4. DERMS Dispatch Layer (`src/derms/`)

Executes the MPC's decision by computing the actual physical `battery_power`, `grid_power`, and `p2p_energy` for each timestep. This layer enforces hard constraints: battery SOC must stay within [10%, 95%], charge/discharge rates are capped at 50 kW, and the energy balance identity is maintained. It translates abstract MPC actions into feasible dispatch commands.

### 5. Reliability & Compliance Layer (`src/compliance/`)

Tags each appliance group with a criticality tier (Tier 1: refrigeration, Tier 2: checkout/IT, Tier 3: HVAC, Tier 4: lighting/other). After a full simulation run, it verifies that Tier 1 was never interrupted (the critical invariant), counts how often each action type fired, and computes a simple ancillary-service value estimate based on avoided peak-demand costs from peak-shaving actions.

### 6. Visualization & API Layer (`src/api/`)

Exposes the per-timestep simulation output as a clean, documented JSON and CSV stream matching the output contract (see below). This layer does not implement a frontend -- it produces the data that a separate dashboard (built by another team) will consume.

---

## Dataset

**File:** `data/dataset.csv` (also at repo root as `dataset.csv`)

- **Type:** Synthetic, generated for this simulation
- **Resolution:** 15-minute intervals
- **Period:** 1 June -- 30 September 2025 (4 months)
- **Size:** 11,712 rows, 30 columns (~2 MB)

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | datetime | ISO timestamp at 15-min intervals |
| `occupancy` | int | Number of people in the building |
| `temperature` | float | Indoor temperature (C) |
| `humidity` | float | Relative humidity (%) |
| `solar_irradiance` | float | Solar irradiance (W/m2) |
| `pv_voltage` | float | PV array voltage (V) |
| `pv_current` | float | PV array current (A) |
| `pv_power` | float | PV generation (kW) |
| `total_consumption` | float | Total building consumption (kW) |
| `display_freezer_power` | float | Display freezer consumption (kW) |
| `display_refrigerator_power` | float | Display refrigerator consumption (kW) |
| `cold_room_power` | float | Cold room consumption (kW) |
| `freezer_room_power` | float | Freezer room consumption (kW) |
| `hvac_power` | float | HVAC consumption (kW) |
| `lighting_power` | float | Lighting consumption (kW) |
| `checkout_power` | float | Checkout system consumption (kW) |
| `it_power` | float | IT infrastructure consumption (kW) |
| `other_appliance_power` | float | Other appliances consumption (kW) |
| `battery_voltage` | float | Battery voltage (V) |
| `battery_current` | float | Battery current (A) |
| `battery_capacity` | float | Battery capacity (kWh) |
| `battery_soc` | float | Battery state of charge (%) |
| `battery_power` | float | Battery power (kW); positive = discharge, negative = charge |
| `grid_power` | float | Grid power (kW); positive = import, negative = export |
| `energy_price` | float | Energy price (EUR/kWh) |
| `demand_response` | int | Demand response event active (0 or 1) |
| `p2p_energy` | float | Peer-to-peer energy exchange (kW) |
| `forecast_consumption` | float | Dataset's own consumption forecast (kW) |
| `forecast_pv` | float | Dataset's own PV forecast (kW) |
| `anomaly_score` | float | Dataset's own anomaly score |

### Sign Conventions

- `battery_power`: positive = discharge, negative = charge
- `grid_power`: positive = import, negative = export

### Energy Balance Identity

At every timestamp, this should approximately hold:

```
pv_power + grid_import + battery_discharge + p2p_import
    ~ total_consumption + battery_charge + grid_export + p2p_export
```

---

## Papers & Sources Used

| # | Paper / Source | Year | Design Decision Justified |
|---|---------------|------|---------------------------|
| 1 | *Building to Grid* -- Guidehouse | 2019 | Overall B2G concept and the building-as-grid-asset framing that motivates the entire pipeline architecture |
| 2 | *Emerging Microgrid Business Models* -- Navigant | 2016 | P2P energy trading model and the microgrid interconnection topology used in the DERMS dispatch layer |
| 3 | *Microgrids -- Critical Facilities* -- Navigant | 2019 | The criticality-tier hierarchy (Tier 1 = never shed) and the reliability-first design constraint |
| 4 | *Buildings-to-Grid Technical Opportunities: From the Grid Perspective* -- DOE/NREL/PNNL | 2014 | The specific grid services modelled (peak shaving, valley filling, demand response) and their value quantification approach |
| 5 | *A Comprehensive Review of Building-to-Grid Interaction* -- Energy Use | 2026 | The six-layer pipeline decomposition and the coverage-ratio metric as the primary reliability indicator |
| 6 | *Buildings-to-Grid Integration Framework* -- IEEE Transactions on Smart Grid (Taha et al.) | 2017 | The simplified receding-horizon MPC formulation and the multi-objective cost function structure (import cost + shedding penalty + comfort penalty) |
| 7 | *Thermal storage capacity in the entire building stock of Denmark for energy flexibility strategies and building-to-grid services* -- REHVA European HVAC Journal | 2024 | The peak shaving / load shifting / valley filling action set, and the HVAC thermal-inertia flexibility budget derived from comfort-band margin |
| 8 | *Data-Driven Analytics for Reliability in the Buildings-to-Grid Integrated System Framework* -- IEEE Access (Bachoumis et al.) | 2023 | The anomaly-detection approach (Isolation Forest) and the data-driven compliance verification methodology |

---

## Tools & Tech Stack

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.13.5 | Core runtime |
| pandas | >= 2.0 | Data loading, manipulation, and CSV output |
| NumPy | >= 1.24 | Numerical operations |
| scikit-learn | >= 1.3 | Gradient boosting forecaster, Isolation Forest anomaly detector |
| pytest | >= 7.4 | Unit and integration testing |

---

## Setup & Run Instructions

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/SmartSupermarket.git
cd SmartSupermarket
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the full pipeline

```bash
# Normal run (no stress scenarios)
python scenario_runner.py

# Run with all stress scenarios
python scenario_runner.py --scenario all

# Run a specific stress scenario
python scenario_runner.py --scenario price_spike
python scenario_runner.py --scenario forced_grid_outage
python scenario_runner.py --scenario sensor_corruption
```

Output files are written to the `output/` directory as JSON and CSV.

### 5. Run the test suite

```bash
python -m pytest tests/ -v
```

---

## Output Contract

Each timestep produces one JSON record with the following fields:

```json
{
  "timestamp": "2025-06-01 00:00:00",
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

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO datetime of this 15-minute interval |
| `coverage_ratio` | float | Ratio of available supply to total consumption (0.0 -- 1.0) |
| `coverage_status` | string | `"NORMAL"` (>= 0.95), `"AT_RISK"` (0.90 -- 0.95), or `"CRITICAL"` (< 0.90) |
| `active_actions` | list[string] | Currently active MPC actions: `"peak_shaving"`, `"hvac_soft_shed"`, `"valley_filling"`, `"hard_shedding"` |
| `tier_1_protected` | bool | Whether Tier 1 loads (refrigeration) were fully supplied this step |
| `battery_soc` | float | Battery state of charge after this step (%) |
| `grid_power` | float | Grid power for this step (kW; positive = import) |
| `p2p_energy` | float | P2P energy exchange for this step (kW) |
| `anomaly_flag` | bool | Whether the anomaly detector flagged this timestep |
| `anomaly_source` | string or null | If anomaly_flag is true, the feature most likely responsible |

The full output is written to both `output/output_<scenario>.json` (array of records) and `output/output_<scenario>.csv` (flat CSV).

---

## Team & Scope

This repository covers the **backend simulation engine only**. The dashboard and compliance reporting layers are built separately by other team members and consume this module's output contract (the JSON/CSV files described above). The API layer in this repo produces the data; it does not render any frontend UI.

---

## Project Structure

```
SmartSupermarket/
|-- data/
|   |-- dataset.csv              # Synthetic dataset (also at repo root)
|-- src/
|   |-- __init__.py
|   |-- ingestion/               # Layer 1: Data ingestion
|   |   |-- __init__.py
|   |   |-- loader.py
|   |-- forecasting/             # Layer 2: AI forecasting & flexibility
|   |   |-- __init__.py
|   |   |-- forecaster.py
|   |   |-- anomaly.py
|   |   |-- flexibility.py
|   |-- mpc/                     # Layer 3: MPC coordination core
|   |   |-- __init__.py
|   |   |-- coordinator.py
|   |-- derms/                   # Layer 4: DERMS dispatch
|   |   |-- __init__.py
|   |   |-- dispatch.py
|   |-- compliance/              # Layer 5: Reliability & compliance
|   |   |-- __init__.py
|   |   |-- checker.py
|   |-- api/                     # Layer 6: Visualization & API output
|       |-- __init__.py
|       |-- output.py
|-- tests/
|   |-- test_ingestion.py
|   |-- test_forecasting.py
|   |-- test_mpc.py
|   |-- test_derms.py
|   |-- test_compliance.py
|   |-- test_api.py
|-- scenario_runner.py           # Main pipeline entry point
|-- requirements.txt
|-- .gitignore
|-- b2g_general_architecture.png
|-- README.md
```
