# Dataset Schema Reference

**File:** `data/dataset.csv`

- **Type:** Synthetic, generated for this simulation
- **Resolution:** 15-minute intervals
- **Period:** 1 June -- 30 September 2025 (4 months)
- **Size:** 11,712 rows, 30 columns (~2 MB)

## Column Schema

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

## Sign Conventions

- `battery_power`: positive = discharge, negative = charge
- `grid_power`: positive = import, negative = export

## Energy Balance Identity

At every timestamp, this should approximately hold:

```
pv_power + grid_import + battery_discharge + p2p_import
    ~ total_consumption + battery_charge + grid_export + p2p_export
```

## Phase 3 optional datasets and columns

The original 30 columns remain required. These four optional numeric columns are
accepted in degrees Celsius: `display_freezer_temp`, `freezer_room_temp`,
`display_refrigerator_temp`, `cold_room_temp`. Missing/invalid temperature readings
remain unavailable; ingestion never fills them with a previous reading.
Column names are stripped, lowercased and accent-normalized. Unicode filenames
are supported, including the `dataset_modifié.csv` alternate spelling.

Inspection found that the supplied filenames have the opposite roles to the
request: `data1/dataset_modified.csv` contains the supermarket's 34 columns;
`data1/smart_supermarket_neighbor_buildings_4months_15min1.csv` contains the six
neighbours. See [the complete audit](PHASE3_DATA_AUDIT.md) for ranges and caveats.

With P2P disabled, the default remains `data/dataset.csv`. With P2P enabled, the
supermarket default is `data1/dataset_modified.csv`. An explicit ingestion path
takes precedence over `B2G_SUPERMARKET_CSV`, which takes precedence over defaults.
`B2G_NEIGHBORS_CSV` overrides the neighbouring-buildings file independently.

Neighbour columns: `timestamp`, `building_id`, `building_type`, `distance_km`
(also `distance_Km`), `consumption_kw`, `production` (also
`energy_production_kw`), `production_type`, `energy_offer_kw`. Distances are km;
power quantities are kW. Each building must cover the same continuous 15-minute
timeline, including all supermarket timestamps used by a run. Missing values,
negative/nonfinite measures and duplicate timestamp/building keys are rejected.
Offers are capped at `max(production - consumption_kw, 0)` with a warning.

## P2P settlement

Set `B2G_P2P_ENABLED=true` to settle trades **after** DERMS dispatch. Settlement
does not change MPC inputs, dispatch actions, SOC, coverage or Tier 1 protection.
It replaces the residual grid exchange with economically preferable neighbour
exchange. Historical synthetic `p2p_energy` is replaced, not added: DERMS already
computes its residual grid requirement without that historical exchange.

`p2p_import` and `p2p_export` are nonnegative kW;
`p2p_energy = p2p_import - p2p_export`. Therefore:

```text
grid_after + p2p_import - p2p_export = grid_before_settlement
```

The energy identity above applies to **served** consumption after DERMS shedding.
Raw synthetic CSV rows do not consistently satisfy that identity (see the audit).
No physical transmission losses are modeled; wheeling is a monetary charge.

Tariffs and fees are placeholders, configured in `src/p2p/config.py`:

| Environment variable | Default | Meaning |
|---|---|---|
| `B2G_P2P_ENABLED` | `false` | Enable settlement |
| `B2G_SUPERMARKET_CSV` | See above | Supermarket source |
| `B2G_NEIGHBORS_CSV` | See above | Neighbour source |
| `B2G_SELL_PRICE` | `0.08` | Grid export EUR/kWh |
| `B2G_WHEELING_BASE_FEE` | `0.005` | EUR/kWh |
| `B2G_WHEELING_PER_KM` | `0.02` | EUR/kWh/km |
| `B2G_STEP_HOURS` | `0.25` | Settlement duration; retain for supplied data |
| `B2G_PRODUCTION_TYPE_PRICE_FACTOR` | `{}` | JSON type-to-factor map; unspecified types use 1 |

The buy tariff is each row's `energy_price`; `p2p_price` is the midpoint of buy
and sell tariffs. A trade's `price_per_kwh` excludes its `wheeling_fee` (also a
rate in EUR/kWh). Purchases pay price plus fee; sales receive price minus fee.
`quantity_kwh = quantity_kw * STEP_HOURS`. `saving_vs_grid` and `p2p_savings`
are actual EUR per step, not rates. `cost` includes grid and P2P purchases;
`revenue` includes grid and P2P sales after fees. No trade executes at an equal
or worse price than the grid. Negative grid buy tariffs are supported.

REST latest/history, WebSocket, JSON, CSV, Redis and SQL preserve optional market
fields. CSV stores `p2p_trades` as a JSON array in one quoted cell.
`GET /api/v1/neighbors` returns static metadata; `production_types` lists observed
values because generation type varies over time. `production_type` reports the
observed technology excluding `Aucune` when a generating technology is present.
`GET /api/v1/p2p/summary?start=...&end=...&scenario=normal` returns per-counterparty
`bought_kwh`, `sold_kwh`, and `money_saved` over the inclusive stored interval.
Naive timestamps use the common simulation clock; offset timestamps normalize
to UTC. These endpoints return 503 if their required source/store is unavailable.

## Persistence migration

`src/persistence/migrations/003_p2p.sql` adds nullable market columns with
`ADD COLUMN IF NOT EXISTS`. PostgreSQL store initialization applies it
automatically; it may also be applied manually before starting the service.
Existing rows remain valid. Trades use JSONB: at most six trades belong to a
timestep and are written/read atomically with its dispatch result, without an
additional trade table or join. SQLite tests use SQLAlchemy's JSON equivalent.
Redis stores the complete JSON record with the same optional fields.

## Temperature monitoring (Part B)

`src/monitoring/temperature.py` observes available sensor columns in CLI and API
runs independently of P2P. With P2P disabled, set
`B2G_SUPERMARKET_CSV=data1/dataset_modified.csv` to use the new data.
Legacy data without sensors retains its original output fields.

All thresholds are **simulation placeholders**, not validated food-safety limits.
Validate against applicable rules, equipment and the audit's observed ranges
before operational use.

| Sensor | Inclusive normal band (°C) | Immediate critical upper limit (°C) |
|---|---|---|
| `display_freezer_temp` | [-30, -18] | -12 |
| `freezer_room_temp` | [-30, -18] | -12 |
| `display_refrigerator_temp` | [0, 5] | 8 |
| `cold_room_temp` | [0, 5] | 8 |

Override with `B2G_TEMP_<SENSOR>_LOW`, `_HIGH`, `_HARD_LIMIT`; uppercase the
sensor name and remove its `_temp` suffix. For example:
`B2G_TEMP_DISPLAY_FREEZER_HIGH=-18`, `B2G_TEMP_COLD_ROOM_HARD_LIMIT=8`.
`B2G_TEMP_CRITICAL_AFTER_STEPS` defaults to 2. Invalid/nonfinite limits,
unordered bands and nonpositive counts fail early.

- Inside the inclusive band: OK; outside either end: WARNING.
- Two consecutive out-of-band 15-minute observations: CRITICAL. Two sampled
  intervals represent 30 minutes; `since` denotes the first observation,
  not an inferred physical onset time.
- Strictly above the hard upper limit: immediate CRITICAL. Equality alone is
  WARNING. No immediate lower hard limit is assumed; excessive cold escalates
  through persistence.
- Returning inside the band resets the sensor's counter. Missing/nonfinite
  readings or a time gap interrupt persistence. Duplicate/out-of-order timestamps
  are rejected. Each run has independent state.
- `temperatures` includes finite observed readings only; absent sensors are
  omitted. With no readings, all three optional fields are omitted. Overall
  `temperature_status` is the worst **observed** status, not a guarantee about
  unavailable sensors. The dashboard labels missing sensors explicitly.
- `temperature_alerts` includes active WARNING/CRITICAL readings only:
  `{sensor, value, status, limit_low, limit_high, since}`. `since` stays unchanged
  throughout an excursion, including escalation.

Monitoring never changes dispatch, coverage or Tier 1 compliance. The dashboard
shows temperature status beside electrical protection, with per-sensor details.

`GET /api/v1/alerts/temperature?start=...&end=...&scenario=normal` returns a
chronological flat list of active alert observations, each with its timestep
`timestamp` and the alert fields. Bounds are inclusive; persistent alerts appear
once per affected step. `since` is retained even if it precedes the query range.
Empty history returns `[]`, invalid ranges 422, unavailable storage 503.
Offset timestamps normalize to UTC; naive timestamps use the simulation clock.

Latest/history/WebSocket and Redis carry the optional fields. CSV uses JSON cells
for temperatures and alerts. `src/persistence/migrations/004_temperature.sql`
adds nullable JSONB columns and a status column; PostgreSQL initialization applies
it idempotently after the P2P migration. SQLite tests use the JSON equivalent.
