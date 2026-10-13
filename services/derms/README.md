# DERMS Microservice

**Phase 3:** Distributed Energy Resource Management System microservice extraction

The DERMS service translates high-level MPC decisions into physically feasible equipment dispatch commands, enforcing battery SOC bounds, charge/discharge limits, and energy balance constraints.

## Architecture

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│     MPC     │       │    DERMS    │       │  Equipment  │
│  Service    │──────▶│  Service    │──────▶│  Controller │
│             │ mpc.  │             │ derms.│             │
│             │decisions             │dispatch             │
└─────────────┘       └─────────────┘       └─────────────┘
                             │
                             ▼
                      DERMSDispatcher
                   (src.derms.dispatch)
                   • Battery limits
                   • SOC bounds
                   • Energy balance
```

## Purpose

The DERMS service:

1. **Consumes MPC decisions** from the `mpc.decisions` Kafka topic containing high-level energy management actions (peak shaving, valley filling, load shedding)
2. **Translates decisions** into physical equipment commands using the `DERMSDispatcher` from `src.derms.dispatch`
3. **Enforces constraints**:
   - Battery charge/discharge rates (default: 50 kW max)
   - Battery SOC bounds (default: 10-95%)
   - Energy balance: PV + Battery + Grid = Consumption - Shed
4. **Publishes dispatch commands** to the `derms.dispatch` Kafka topic with equipment IDs, command types, and setpoints

## Files

- **`main.py`** — Service entry point, extends `MessageProcessor` from `kafka_utils.utils`
- **`Dockerfile`** — Container definition for Docker Compose deployment
- **`requirements.txt`** — Python dependencies (pandas, numpy, kafka-python, lz4)
- **`test_service.py`** — Integration test validating message flow
- **`README.md`** — This documentation

## Running the Service

### Docker Compose (Recommended)

```bash
# Build and start DERMS service
docker compose up --build -d derms

# View logs
docker compose logs derms -f

# Check service status
docker compose ps derms
```

### Local Development

```bash
# Ensure Kafka is running on localhost:9093
# Install dependencies
pip install -r requirements.txt

# Set environment variable
export KAFKA_BOOTSTRAP_SERVERS=localhost:9093

# Run service
python services/derms/main.py
```

## Input Schema

**Topic:** `mpc.decisions`  
**Producer:** MPC Service

```json
{
  "timestamp": "2025-06-01T12:30:00",
  "peak_shave": true,
  "peak_shave_kw": 25.0,
  "load_shift_hvac": false,
  "hvac_shed_kw": 0.0,
  "valley_fill": false,
  "valley_fill_kw": 0.0,
  "hard_shed_tiers": [],
  "hard_shed_kw": 0.0,
  "active_action_names": ["peak_shaving"],
  "total_battery_request_kw": 25.0,
  "service": "mpc"
}
```

## Output Schema

**Topic:** `derms.dispatch`  
**Consumer:** Equipment Controller / Compliance Service

```json
{
  "timestamp": "2025-06-01T12:30:00",
  "commands": [
    {
      "equipment_id": "battery_001",
      "command_type": "discharge",
      "setpoint_kw": 25.0,
      "duration_min": 15
    },
    {
      "equipment_id": "grid_connection",
      "command_type": "import",
      "setpoint_kw": 75.0,
      "duration_min": 15
    }
  ],
  "total_commands": 2,
  "battery_power": 25.0,
  "grid_power": 75.0,
  "p2p_energy": 0.0,
  "shed_kw": 0.0,
  "battery_soc_after": 48.75,
  "service": "derms"
}
```

## Equipment IDs and Command Types

### Battery (`battery_001`)
- **charge** — Charge battery at `setpoint_kw`
- **discharge** — Discharge battery at `setpoint_kw`

### Grid Connection (`grid_connection`)
- **import** — Import power from grid at `setpoint_kw`
- **export** — Export power to grid at `setpoint_kw`

### HVAC System (`hvac_main`)
- **reduce_power** — Reduce HVAC power by `setpoint_kw`

### Lighting (`lighting_zone_1`)
- **dim** — Dim lighting to `setpoint_percent` (e.g., 70%)

## Configuration

### Environment Variables

- `KAFKA_BOOTSTRAP_SERVERS` — Kafka broker addresses (default: `localhost:9093`)
- `PYTHONUNBUFFERED` — Set to `"1"` for real-time logging

## Known Limitations

### Hardcoded Telemetry State (CRITICAL)

**Issue:** The service uses fixed default values for battery SOC, PV power, and consumption instead of real-time telemetry.

**Resolution:** Phase 4 state service integration — Introduce `telemetry.state` Kafka topic with real-time values.

## Testing

```bash
# Run integration test (requires Kafka running)
python services/derms/test_service.py
```

---

**Pattern:** Extends `MessageProcessor` from `kafka_utils.utils`  
**Core Logic:** Reuses `DERMSDispatcher` from `src/derms/dispatch`  
**Phase:** 3 of 7 (Microservices extraction)
