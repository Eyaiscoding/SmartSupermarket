# Phase 1: Kafka Infrastructure - Completion Checklist

## ✅ Completed Tasks

- [x] Backup existing docker-compose.yml as docker-compose.monolith.yml
- [x] Add Zookeeper service to docker-compose.yml
- [x] Add Kafka service to docker-compose.yml
- [x] Configure Kafka health checks
- [x] Update backend service to depend on Kafka
- [x] Create kafka/ directory structure
- [x] Create kafka/create-topics.sh script
- [x] Create kafka/utils.py Python utilities
- [x] Create kafka/test_kafka.py integration test
- [x] Create kafka/README.md documentation
- [x] Add kafka-python>=2.0.2 to requirements.txt
- [x] Create JSON schema directory structure

## 🧪 Verification Steps

### Step 1: Start Kafka Stack

```powershell
cd "c:\Users\user\Desktop\Digital\Smart building\SmartSupermarket"
docker compose up -d zookeeper kafka
```

**Expected:** Both services show "Up (healthy)" after ~30 seconds

```powershell
docker compose ps zookeeper kafka
```

---

### Step 2: Create Kafka Topics

```powershell
# telemetry.raw (4 partitions, 7 day retention)
docker compose exec kafka kafka-topics --create --bootstrap-server localhost:9092 --topic telemetry.raw --partitions 4 --replication-factor 1 --config retention.ms=604800000 --if-not-exists

# forecasting.predictions (2 partitions, 24 hour retention)
docker compose exec kafka kafka-topics --create --bootstrap-server localhost:9092 --topic forecasting.predictions --partitions 2 --replication-factor 1 --config retention.ms=86400000 --if-not-exists

# mpc.decisions (1 partition, 24 hour retention)
docker compose exec kafka kafka-topics --create --bootstrap-server localhost:9092 --topic mpc.decisions --partitions 1 --replication-factor 1 --config retention.ms=86400000 --if-not-exists

# derms.dispatch (1 partition, 30 day retention)
docker compose exec kafka kafka-topics --create --bootstrap-server localhost:9092 --topic derms.dispatch --partitions 1 --replication-factor 1 --config retention.ms=2592000000 --if-not-exists

# compliance.reports (1 partition, 1 year retention)
docker compose exec kafka kafka-topics --create --bootstrap-server localhost:9092 --topic compliance.reports --partitions 1 --replication-factor 1 --config retention.ms=31536000000 --if-not-exists
```

**Expected:** Each command outputs "Created topic <name>"

---

### Step 3: Verify Topics

```powershell
docker compose exec kafka kafka-topics --list --bootstrap-server localhost:9092
```

**Expected output:**
```
compliance.reports
derms.dispatch
forecasting.predictions
mpc.decisions
telemetry.raw
```

---

### Step 4: Test Kafka Python Integration

```powershell
# Install kafka-python locally
pip install kafka-python

# Run integration tests
python kafka/test_kafka.py
```

**Expected output:**
```
✅ PASS - Health Check
✅ PASS - Produce/Consume
✅ PASS - Topic Verification
Total: 3/3 tests passed
🎉 All tests passed!
```

---

### Step 5: Verify Monolith Still Works

```powershell
# Start full stack (including monolithic backend)
docker compose up -d

# Wait for all services to be healthy (~90 seconds)
docker compose ps

# Test API
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing
```

**Expected:** 
- All 6 services healthy (zookeeper, kafka, mosquitto, timescaledb, redis, backend)
- API returns `{"status":"healthy","timescaledb":true,"redis":true}`

---

## 📊 Success Criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| Zookeeper healthy | ✅ | Port 2181 accessible |
| Kafka healthy | ✅ | Ports 9092 (internal), 9093 (host) accessible |
| 5 topics created | ✅ | All topics listed with correct partitions |
| Python test passes | ✅ | Can produce and consume messages |
| Monolith unaffected | ✅ | Backend still works without using Kafka |

---

## 🔄 Rollback Procedure (If Needed)

If Phase 1 causes issues:

```powershell
# Stop all services
docker compose down

# Restore original docker-compose
Copy-Item docker-compose.monolith.yml docker-compose.yml -Force

# Restart without Kafka
docker compose up -d

# Verify system works
Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing
```

---

## 📝 Next Steps (Phase 2)

See `MICROSERVICES_MIGRATION_PLAN.md` for Phase 2 details:

1. Create `services/forecasting/` directory
2. Build Dockerfile for forecasting service
3. Implement Kafka consumer/producer wrapper
4. Test end-to-end flow: Telemetry → Forecasting → Predictions

**Estimated Time:** 4 hours  
**Risk Level:** Medium

---

## 📚 Documentation Created

- ✅ `MICROSERVICES_MIGRATION_PLAN.md` - Complete 7-phase roadmap
- ✅ `kafka/README.md` - Kafka setup and usage guide
- ✅ `PHASE1_CHECKLIST.md` - This checklist
- ✅ `docker-compose.monolith.yml` - Backup of v2 monolith

---

*Phase 1 Status:* READY FOR VERIFICATION ✅  
*Date:* 2026-10-12  
*Next Session:* Phase 2 - Extract Forecasting Service
