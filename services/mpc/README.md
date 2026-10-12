# MPC Microservice

**Phase 3: Microservices Architecture**

The MPC (Model Predictive Control) microservice consumes forecasting predictions from Kafka and runs a receding-horizon controller to determine optimal energy management actions.

## Architecture

```
Kafka (forecasting.predictions) → MPC Service → Kafka (mpc.decisions)
```

The MPC service is **stateless**: each prediction event is processed independently. The controller looks ahead over a short horizon (default: 4 timesteps = 1 hour) and optimizes a multi-objective cost function to decide:

- **Peak shaving**: Discharge battery when grid prices are high
- **Load shifting**: Soft-shed HVAC during demand-response events
- **Valley filling**: Pre-charge battery before anticipated PV drops
- **Hard shedding**: Cut non-critical loads (Tier 4 → Tier 3 → Tier 2, never Tier 1) when coverage ratio is critically low

## Files

```
services/mpc/
├── Dockerfile           # Container image definition
├── requirements.txt     # Python dependencies
├── main.py             # MPC service entry point
├── test_service.py     # Integration test
└── README.md           # This file
```

## Running

### With Docker Compose (Production)

```bash
# Build and start MPC service (along with dependencies)
docker compose up --build -d mpc

# View logs
docker compose logs -f mpc

# Stop service
docker compose stop mpc
```

### Local Development

```bash
# Install dependencies
pip install -r services/mpc/requirements.txt

# Set environment variables
export KAFKA_BOOTSTRAP_SERVERS=localhost:9093
export MPC_HORIZON_HOURS=24
export MPC_TIME_STEP_MINUTES=15

# Run service
python services/mpc/main.py
```

## Message Schemas

### Input: `forecasting.predictions`

Consumed from the Forecasting microservice:

```json
{
  "timestamp": "2025-06-01 12:00:00",
  "forecast_consumption": 150.5,
  "forecast_pv": 45.2,
  "anomaly_score": 0.1,
  "anomaly_flag": false,
  "anomaly_source": null,
  "flexibility_budgets": {
    "hvac_soft_shed_kw": 12.5,
    "lighting_shed_kw": 8.3,
    "checkout_shed_kw": 2.1,
    "other_shed_kw": 5.4
  },
  "telemetry": {
    "hvac_power": 25.0,
    "lighting_power": 16.6,
    "checkout_power": 42.0,
    "other_appliance_power": 10.8
  }
}
```

**Note**: The `telemetry` field is optional. If missing, the MPC service uses typical supermarket power defaults (HVAC: 50kW, Lighting: 30kW, Checkout: 20kW, Other: 25kW) to construct FlexBudget objects.

### Output: `mpc.decisions`

Published to Kafka for the DERMS microservice:

```json
{
  "timestamp": "2025-06-01 12:00:00",
  "peak_shave": false,
  "peak_shave_kw": 0.0,
  "load_shift_hvac": false,
  "hvac_shed_kw": 0.0,
  "valley_fill": false,
  "valley_fill_kw": 0.0,
  "hard_shed_tiers": [],
  "hard_shed_kw": 0.0,
  "active_action_names": [],
  "total_battery_request_kw": 0.0,
  "service": "mpc"
}
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9093` | Kafka broker addresses |
| `MPC_HORIZON_HOURS` | `24` | Planning horizon in hours (capped at 4 timesteps in v1) |
| `MPC_TIME_STEP_MINUTES` | `15` | Discretization timestep |

**Note**: The MPC controller currently caps the horizon at 4 timesteps regardless of `MPC_HORIZON_HOURS` configuration, as the current implementation is optimized for short-term (1-hour) decisions. Future versions may support longer horizons.

## Known Limitations & Technical Debt

### Single-timestep Forecasts (Phase 6 Enhancement)

The forecasting service currently publishes single-timestep predictions (`forecast_consumption`, `forecast_pv`). The MPC service replicates these values across the horizon, which produces **valid but suboptimal** decisions:

- **Impact**: The optimizer sees a flat future and cannot anticipate upcoming PV dips or consumption peaks
- **Example**: Valley-filling logic (pre-charging battery before forecasted PV drops) will never trigger
- **Workaround**: The controller still makes safe decisions based on current conditions
- **Fix**: Forecasting service should publish horizon-length forecast vectors in future phases

This limitation is documented as technical debt for **Phase 6 (Observability & Optimization)**.

## MPC Controller Details

The controller (`src.mpc.coordinator.MPCCoordinator`) implements a simplified receding-horizon optimization:

**Objective**: Minimize composite cost:
```
cost = grid_import_cost + shedding_penalty + comfort_penalty
```

**Constraints**:
- Battery SOC limits (10% - 90%)
- Tier 1 refrigeration loads must never be shed (infinite penalty)
- Tier 2-4 loads can be shed with tiered penalties
- HVAC soft-shedding respects thermal comfort bounds (18-26°C)

**Tuning Parameters** (in `src/mpc/coordinator.py`):
- `PRICE_PEAK_THRESHOLD`: €0.25/kWh (trigger peak shaving above this)
- `COVERAGE_CRITICAL`: 0.90 (trigger hard shedding below this coverage ratio)
- `HORIZON`: 4 timesteps (look-ahead window)

## Testing

### Unit Test (Service Logic Only)

```bash
# Test MPCService.process_message() without Kafka
python services/mpc/test_service.py
```

### Integration Test (End-to-End)

```bash
# Requires Kafka running
docker compose up -d kafka

# Run test
python services/mpc/test_service.py

# Expected output: "🎉 MPC Service Test PASSED"
```

## Troubleshooting

### Service won't start

**Symptom**: `kafka.errors.NoBrokersAvailable`

**Solution**: Ensure Kafka is running and healthy:
```bash
docker compose ps kafka
docker compose logs kafka
```

### No messages consumed

**Symptom**: Logs show "Starting message processing loop" but no "Processing prediction for..." messages

**Solution**: Check that forecasting service is running and publishing predictions:
```bash
docker compose logs forecasting
kafka-console-consumer --bootstrap-server localhost:9093 --topic forecasting.predictions --from-beginning --max-messages 1
```

### Actions always empty

**Symptom**: `active_action_names: []` in all decisions

**Solution**: This is expected under normal conditions. Actions only trigger when:
- Energy price > €0.25/kWh (peak shaving)
- Demand-response event active (load shifting)
- Coverage ratio < 0.90 (hard shedding)
- Forecasted PV drops significantly (valley filling)

Check input prediction values and MPC parameters in `src/mpc/coordinator.py`.

## Dependencies

- **Python**: 3.13+
- **Kafka**: Apache Kafka 7.6.0+ (via Docker)
- **Core logic**: `src/mpc/coordinator.py` (MPCCoordinator)
- **Flexibility model**: `src/forecasting/flexibility.py` (FlexBudget)

## Related Services

- **Upstream**: Forecasting Service (`services/forecasting/`)
- **Downstream**: DERMS Service (`services/derms/`, Phase 3)
- **Shared utilities**: `kafka_utils/utils.py` (MessageProcessor base class)
