# Kafka Event Streaming Infrastructure
## Phase 1: Foundation Setup

---

## 📋 Overview

This directory contains Kafka configuration, utilities, and scripts for the B2G microservices event streaming backbone.

**Status:** Phase 1 Complete ✅  
**Kafka Version:** 7.6.0 (Confluent Platform)  
**Topics:** 5 core event streams

---

## 🗂️ Directory Structure

```
kafka/
├── README.md                 # This file
├── create-topics.sh          # Topic creation script
├── test_kafka.py             # Integration test script
├── utils.py                  # Python Kafka utilities
└── schemas/                  # JSON schemas for messages
    └── telemetry.json        # Telemetry event schema
```

---

## 🚀 Quick Start

### 1. Start Kafka Stack

```powershell
cd "c:\Users\user\Desktop\Digital\Smart building\SmartSupermarket"
docker compose up -d zookeeper kafka
```

Wait ~30 seconds for Kafka to become healthy:

```powershell
docker compose ps kafka
# Should show "Up (healthy)"
```

### 2. Create Topics

```powershell
docker compose exec kafka bash -c "cd /opt/kafka/bin && ./kafka-topics.sh --create --bootstrap-server localhost:9092 --topic telemetry.raw --partitions 4 --replication-factor 1 --if-not-exists"
docker compose exec kafka bash -c "cd /opt/kafka/bin && ./kafka-topics.sh --create --bootstrap-server localhost:9092 --topic forecasting.predictions --partitions 2 --replication-factor 1 --if-not-exists"
docker compose exec kafka bash -c "cd /opt/kafka/bin && ./kafka-topics.sh --create --bootstrap-server localhost:9092 --topic mpc.decisions --partitions 1 --replication-factor 1 --if-not-exists"
docker compose exec kafka bash -c "cd /opt/kafka/bin && ./kafka-topics.sh --create --bootstrap-server localhost:9092 --topic derms.dispatch --partitions 1 --replication-factor 1 --if-not-exists"
docker compose exec kafka bash -c "cd /opt/kafka/bin && ./kafka-topics.sh --create --bootstrap-server localhost:9092 --topic compliance.reports --partitions 1 --replication-factor 1 --if-not-exists"
```

### 3. Verify Topics

```powershell
docker compose exec kafka kafka-topics --list --bootstrap-server localhost:9092
```

Expected output:
```
compliance.reports
derms.dispatch
forecasting.predictions
mpc.decisions
telemetry.raw
```

### 4. Run Integration Tests

```powershell
python kafka/test_kafka.py
```

Expected: All 3 tests pass ✅

---

## 📊 Topic Configuration

| Topic | Partitions | Retention | Purpose |
|-------|------------|-----------|---------|
| `telemetry.raw` | 4 | 7 days | Raw MQTT sensor data |
| `forecasting.predictions` | 2 | 24 hours | AI forecasts + flexibility |
| `mpc.decisions` | 1 | 24 hours | MPC controller actions |
| `derms.dispatch` | 1 | 30 days | Physical dispatch + P2P |
| `compliance.reports` | 1 | 1 year | R1-R6 compliance events |

---

## 🔌 Connection Details

### From Host (Local Development)

```python
from kafka.utils import create_producer, create_consumer

# Producer
producer = create_producer(bootstrap_servers='localhost:9093')
producer.send('telemetry.raw', {'timestamp': '...', 'pv_power': 15.4})

# Consumer
consumer = create_consumer('telemetry.raw', group_id='my-service')
for message in consumer:
    process(message.value)
```

### From Docker Container (Production)

```python
# Set environment variable
KAFKA_BOOTSTRAP_SERVERS=kafka:9092

# Use default (reads from env)
producer = create_producer()
consumer = create_consumer('telemetry.raw', group_id='my-service')
```

---

## 📝 Message Schemas

### Telemetry Event (`telemetry.raw`)

```json
{
  "timestamp": "2025-06-01T00:00:00",
  "occupancy": 45,
  "temperature": 22.3,
  "pv_power": 15.4,
  "total_consumption": 78.2,
  "battery_soc": 62.3,
  ... // 30+ fields from dataset.csv
}
```

### Forecasting Prediction (`forecasting.predictions`)

```json
{
  "timestamp": "2025-06-01T00:00:00",
  "forecast_consumption": 82.1,
  "forecast_pv": 18.3,
  "anomaly_score": 0.12,
  "anomaly_flag": false,
  "flexibility_budgets": {
    "hvac_soft_shed_kw": 12.5,
    "lighting_shed_kw": 8.2
  }
}
```

### MPC Decision (`mpc.decisions`)

```json
{
  "timestamp": "2025-06-01T00:00:00",
  "peak_shave": true,
  "peak_shave_kw": 8.5,
  "load_shift_hvac": true,
  "hard_shed_tiers": [4],
  "hard_shed_kw": 12.3,
  "active_action_names": ["peak_shaving", "hvac_soft_shed"]
}
```

### DERMS Dispatch (`derms.dispatch`)

```json
{
  "timestamp": "2025-06-01T00:00:00",
  "battery_soc": 62.3,
  "battery_power": -8.5,
  "grid_power": 23.4,
  "p2p_energy": 3.2,
  "p2p_trades": [{"building": "B03", "kw": 3.2, "price": 0.18}]
}
```

### Compliance Report (`compliance.reports`)

```json
{
  "timestamp": "2025-06-01T00:00:00",
  "status": "GREEN",
  "tier_1_protected": true,
  "violations": [],
  "temperatures": {"display_freezer_temp": -19.2}
}
```

---

## 🛠️ Useful Commands

### Monitor Topic Activity

```powershell
# Watch messages in real-time
docker compose exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic telemetry.raw \
  --from-beginning
```

### Check Consumer Groups

```powershell
docker compose exec kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --list
```

### View Consumer Lag

```powershell
docker compose exec kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --group forecasting-service \
  --describe
```

### Reset Consumer Offset

```powershell
docker compose exec kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --group my-service \
  --topic telemetry.raw \
  --reset-offsets --to-earliest \
  --execute
```

---

## 🐛 Troubleshooting

### Issue: "Connection refused" errors

**Solution:** Ensure Kafka is healthy

```powershell
docker compose ps kafka
# Should show "Up (healthy)"

# Check logs
docker compose logs kafka
```

### Issue: Topics not created

**Solution:** Run topic creation manually

```powershell
docker compose exec kafka kafka-topics \
  --create --bootstrap-server localhost:9092 \
  --topic telemetry.raw --partitions 4 --replication-factor 1
```

### Issue: Messages not being consumed

**Solution:** Check consumer group status

```powershell
docker compose exec kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --group my-service \
  --describe
```

Look for `LAG` column - should decrease as messages are consumed.

---

## 📚 Next Steps (Phase 2)

- [ ] Extract Forecasting Service
- [ ] Build Dockerfile for forecasting container
- [ ] Implement Kafka consumer in forecasting service
- [ ] Test end-to-end: MQTT → Kafka → Forecasting → Kafka → API

See `MICROSERVICES_MIGRATION_PLAN.md` for full roadmap.

---

*Last Updated:* 2026-10-12  
*Phase:* 1 of 7  
*Status:* Infrastructure Ready ✅
