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
