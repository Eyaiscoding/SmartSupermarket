# Smart Supermarket B2G - Microservices Migration Plan
## v2 Monolith → Target Distributed Architecture

---

## 📋 Executive Summary

**Objective:** Transition from monolithic FastAPI application to distributed microservices architecture using Apache Kafka for event streaming.

**Timeline:** 3 phases over multiple sessions  
**Risk Level:** Medium (gradual migration with rollback capability)  
**Current Status:** ✅ Phase 1 in progress

---

## 🎯 Migration Goals

### Business Drivers
1. **Scalability:** Independent scaling of compute-heavy services (forecasting, MPC)
2. **Team Structure:** Enable parallel development across service boundaries
3. **Deployment Flexibility:** Deploy services independently without full-stack restarts
4. **Technology Diversity:** Use optimal tech stack per service (e.g., PyTorch for forecasting)
5. **Resilience:** Service failures don't bring down entire platform

### Non-Goals
- **Not a rewrite:** Core logic in `src/` modules stays unchanged
- **Not performance-focused:** Latency may increase slightly (network overhead)
- **Not immediate:** Gradual migration over weeks, not hours

---

## 🏗️ Current Architecture (v2 Monolith)

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                          │
│  ┌──────────┐  ┌───────────┐  ┌─────┐  ┌───────┐  ┌─────┐ │
│  │Ingestion │→ │Forecasting│→ │ MPC │→ │ DERMS │→ │ API │ │
│  └──────────┘  └───────────┘  └─────┘  └───────┘  └─────┘ │
│       ↓              ↓           ↓         ↓          ↓     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         TimescaleDB + Redis (shared state)           │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         ↑                                          ↓
    Mosquitto MQTT                          Dashboard WebSocket
```

**Characteristics:**
- ✅ Simple deployment (one container)
- ✅ Easy debugging (single process)
- ✅ Low latency (in-process function calls)
- ❌ Tight coupling (modules share memory)
- ❌ Single point of failure
- ❌ Cannot scale components independently

---

## 🎯 Target Architecture (Microservices)

```
                    ┌─────────────────────────────────────┐
                    │      Apache Kafka Event Bus         │
                    │  Topics: telemetry, forecasts,      │
                    │  mpc-decisions, dispatch, compliance │
                    └─────────────────────────────────────┘
                              ↑         ↓
        ┌─────────────────────┴─────────┴──────────────────┐
        ↓                     ↓         ↓                   ↓
┌──────────────┐     ┌──────────────┐ ┌────────────┐  ┌─────────────┐
│ Ingestion    │────→│ Forecasting  │→│ MPC        │→ │ DERMS       │
│ Service      │     │ Service      │ │ Service    │  │ Service     │
│ (MQTT→Kafka) │     │ (AI/ML)      │ │ (Optim.)   │  │ (P2P/Grid)  │
└──────────────┘     └──────────────┘ └────────────┘  └─────────────┘
        ↓                                                      ↓
        └──────────────────────────────────────────────────────┘
                                 ↓
                    ┌────────────────────────┐
                    │  Compliance Service    │
                    │  (Rules R1-R6)         │
                    └────────────────────────┘
                                 ↓
                    ┌────────────────────────┐
                    │  API Gateway Service   │
                    │  (REST/WebSocket)      │
                    └────────────────────────┘
                                 ↓
                    ┌────────────────────────┐
                    │  TimescaleDB + Redis   │
                    │  (Persistence Layer)   │
                    └────────────────────────┘
                                 ↓
                         Dashboard (React)
```

**Characteristics:**
- ✅ Independent scaling (scale MPC without scaling API)
- ✅ Fault isolation (forecasting crash doesn't stop API)
- ✅ Technology flexibility (Python, Go, Java per service)
- ✅ Team boundaries (clear service ownership)
- ❌ Higher latency (~50-200ms added per hop)
- ❌ Complex debugging (distributed tracing needed)
- ❌ Operational overhead (6+ containers, Kafka cluster)

---

## 📊 Service Decomposition Matrix

| Service | Consumes | Produces | Technology | Scaling Need | Statefulness |
|---------|----------|----------|------------|--------------|--------------|
| **Ingestion** | MQTT broker | `telemetry.raw` | Python 3.13 | Low (I/O bound) | Stateless |
| **Forecasting** | `telemetry.raw` | `forecasting.predictions` | Python + scikit-learn | High (CPU bound) | Stateless (model in memory) |
| **MPC** | `forecasting.predictions` | `mpc.decisions` | Python + NumPy | High (CPU bound) | Stateless |
| **DERMS** | `mpc.decisions`, neighbor data | `derms.dispatch` | Python | Medium | Stateless |
| **Compliance** | `derms.dispatch`, `telemetry.raw` | `compliance.reports` | Python | Low | Stateful (breach tracking) |
| **API Gateway** | All topics (subscribe) | WebSocket streams | FastAPI + asyncio | Medium (connection bound) | Stateful (WS connections) |

---

## 🗂️ Kafka Topic Design

### Topic: `telemetry.raw`
**Purpose:** Raw sensor data from MQTT broker  
**Partitions:** 4 (for parallel consumption)  
**Retention:** 7 days (168 hours)  
**Schema:**
```json
{
  "timestamp": "2025-06-01T00:00:00",
  "occupancy": 45,
  "temperature": 22.3,
  "pv_power": 15.4,
  "total_consumption": 78.2,
  ...  // All 30+ dataset columns
}
```

---

### Topic: `forecasting.predictions`
**Purpose:** AI forecasts and flexibility estimates  
**Partitions:** 2  
**Retention:** 24 hours  
**Schema:**
```json
{
  "timestamp": "2025-06-01T00:00:00",
  "forecast_consumption": 82.1,
  "forecast_pv": 18.3,
  "anomaly_score": 0.12,
  "anomaly_flag": false,
  "flexibility_budgets": {
    "hvac_soft_shed_kw": 12.5,
    "lighting_shed_kw": 8.2,
    ...
  }
}
```

---

### Topic: `mpc.decisions`
**Purpose:** MPC controller action plans  
**Partitions:** 1 (ordered decisions)  
**Retention:** 24 hours  
**Schema:**
```json
{
  "timestamp": "2025-06-01T00:00:00",
  "peak_shave": true,
  "peak_shave_kw": 8.5,
  "valley_fill": false,
  "load_shift_hvac": true,
  "hard_shed_tiers": [4],
  "hard_shed_kw": 12.3,
  "battery_action": "discharge",
  "active_action_names": ["peak_shaving", "hvac_soft_shed"]
}
```

---

### Topic: `derms.dispatch`
**Purpose:** Physical dispatch with grid/battery/P2P balances  
**Partitions:** 1 (ordered)  
**Retention:** 30 days (audit trail)  
**Schema:**
```json
{
  "timestamp": "2025-06-01T00:00:00",
  "battery_soc": 62.3,
  "battery_power": -8.5,
  "grid_power": 23.4,
  "p2p_energy": 3.2,
  "p2p_import": 3.2,
  "p2p_export": 0.0,
  "p2p_trades": [
    {"building": "B03", "kw": 3.2, "price": 0.18}
  ],
  "shed_kw": 12.3
}
```

---

### Topic: `compliance.reports`
**Purpose:** Regulatory compliance events (R1-R6 violations)  
**Partitions:** 1  
**Retention:** 1 year (regulatory requirement)  
**Schema:**
```json
{
  "timestamp": "2025-06-01T00:00:00",
  "status": "GREEN",  // GREEN, YELLOW, RED
  "tier_1_protected": true,
  "violations": [],  // List of active violations
  "cold_chain_status": "OK",
  "temperatures": {
    "display_freezer_temp": -19.2,
    ...
  }
}
```

---

## 🚀 Migration Phases

### Phase 1: Infrastructure Foundation ✅ (Current)
**Duration:** 1 session (~2 hours)  
**Deliverables:**
- ✅ Kafka + Zookeeper in docker-compose
- ✅ Topic creation scripts
- ✅ Basic Python Kafka producer/consumer utilities
- ✅ Health checks and monitoring

**Success Criteria:**
- [ ] `docker compose up` starts all services healthy
- [ ] Can publish/consume test messages to/from each topic
- [ ] Monolithic backend still works unchanged

**Rollback:** Remove Kafka services from docker-compose, system unaffected

---

### Phase 2: Extract First Service (Proof of Concept)
**Duration:** 1-2 sessions (~4 hours)  
**Target Service:** Forecasting (isolated, CPU-intensive, good PoC candidate)  
**Deliverables:**
- [ ] `services/forecasting/` directory structure
- [ ] Dockerfile for forecasting service
- [ ] Kafka consumer for `telemetry.raw`
- [ ] Kafka producer for `forecasting.predictions`
- [ ] Integration test: MQTT → Kafka → Forecasting → Kafka → API

**Success Criteria:**
- [ ] Forecasting runs as standalone container
- [ ] Produces predictions to Kafka successfully
- [ ] API Gateway can consume predictions
- [ ] End-to-end latency <500ms per timestep

**Rollback:** Disable forecasting service, API falls back to in-process forecasting

---

### Phase 3: Extract MPC Service
**Duration:** 1 session (~3 hours)  
**Target Service:** MPC Coordinator  
**Deliverables:**
- [ ] `services/mpc/` directory structure
- [ ] Kafka consumer for `forecasting.predictions`
- [ ] Kafka producer for `mpc.decisions`
- [ ] Stateless MPC logic extraction

**Success Criteria:**
- [ ] MPC decisions flow through Kafka
- [ ] API Gateway receives decisions
- [ ] Test suite passes (MPC module tests adapted)

---

### Phase 4: Extract DERMS Service
**Duration:** 1 session (~3 hours)  
**Target Service:** DERMS Dispatcher + P2P Trading  
**Deliverables:**
- [ ] `services/derms/` directory structure
- [ ] Kafka consumer for `mpc.decisions`
- [ ] Kafka producer for `derms.dispatch`
- [ ] P2P neighbor data integration

**Success Criteria:**
- [ ] Dispatch events published to Kafka
- [ ] P2P trades executed correctly
- [ ] Battery SOC tracking works across service boundary

---

### Phase 5: Extract Compliance Service
**Duration:** 1 session (~2 hours)  
**Target Service:** Compliance Checker (R1-R6 rules)  
**Deliverables:**
- [ ] `services/compliance/` directory structure
- [ ] Kafka consumer for `derms.dispatch` and `telemetry.raw`
- [ ] Kafka producer for `compliance.reports`
- [ ] Stateful violation tracking

**Success Criteria:**
- [ ] Compliance events published per timestep
- [ ] Violation logs persisted
- [ ] Dashboard shows compliance status

---

### Phase 6: Ingestion Service + API Gateway Refactor
**Duration:** 2 sessions (~6 hours)  
**Deliverables:**
- [ ] `services/ingestion/` - MQTT subscriber publishing to Kafka
- [ ] `services/api-gateway/` - Kafka consumer aggregating events
- [ ] WebSocket streaming from Kafka events
- [ ] TimescaleDB/Redis writes from API Gateway

**Success Criteria:**
- [ ] MQTT → Kafka → All Services → Kafka → API → Dashboard
- [ ] WebSocket streams live data
- [ ] Historical API endpoints work
- [ ] All 108 tests passing

---

### Phase 7: Production Hardening
**Duration:** 1-2 sessions (~4 hours)  
**Deliverables:**
- [ ] Distributed tracing (OpenTelemetry)
- [ ] Service health checks and auto-restart
- [ ] Kafka consumer group monitoring
- [ ] Error handling and dead letter queues
- [ ] Performance benchmarks and optimization

**Success Criteria:**
- [ ] End-to-end latency <1 second
- [ ] Services recover from transient failures
- [ ] Monitoring dashboards for all services

---

## 📁 New Directory Structure

```
SmartSupermarket/
├── docker-compose.yml              # Updated with Kafka + all services
├── docker-compose.monolith.yml     # Backup of v2 monolith
├── services/                        # NEW: Microservices directory
│   ├── ingestion/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py                 # MQTT → Kafka bridge
│   │   └── config.py
│   ├── forecasting/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py                 # Kafka consumer/producer
│   │   ├── forecaster.py           # Copied from src/forecasting/
│   │   └── config.py
│   ├── mpc/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── coordinator.py
│   │   └── config.py
│   ├── derms/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── dispatch.py
│   │   └── p2p_integration.py
│   ├── compliance/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── checker.py
│   │   └── config.py
│   └── api-gateway/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── main.py                 # Kafka → REST/WebSocket
│       └── aggregator.py
├── kafka/                           # NEW: Kafka utilities
│   ├── topics.sh                   # Topic creation script
│   ├── schemas/                    # Avro/JSON schemas
│   └── monitoring/                 # Kafka monitoring configs
├── src/                            # KEEP: Core logic (reused by services)
│   ├── ingestion/
│   ├── forecasting/
│   ├── mpc/
│   ├── derms/
│   ├── compliance/
│   └── api/
└── tests/
    ├── unit/                       # Module-level tests (unchanged)
    ├── integration/                # NEW: Cross-service tests
    │   ├── test_kafka_flow.py
    │   └── test_end_to_end.py
    └── load/                       # NEW: Performance tests
```

---

## 🔧 Phase 1 Implementation Details

### 1.1 Docker Compose Updates

**New Services:**
```yaml
zookeeper:
  image: confluentinc/cp-zookeeper:7.6.0
  ports: ["2181:2181"]
  environment:
    ZOOKEEPER_CLIENT_PORT: 2181

kafka:
  image: confluentinc/cp-kafka:7.6.0
  depends_on: [zookeeper]
  ports: ["9092:9092", "9093:9093"]
  environment:
    KAFKA_BROKER_ID: 1
    KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
    KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092,PLAINTEXT_HOST://localhost:9093
    KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
    KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
```

### 1.2 Topic Creation Script

```bash
#!/bin/bash
# kafka/create-topics.sh
kafka-topics --create --bootstrap-server kafka:9092 --topic telemetry.raw --partitions 4 --replication-factor 1
kafka-topics --create --bootstrap-server kafka:9092 --topic forecasting.predictions --partitions 2 --replication-factor 1
kafka-topics --create --bootstrap-server kafka:9092 --topic mpc.decisions --partitions 1 --replication-factor 1
kafka-topics --create --bootstrap-server kafka:9092 --topic derms.dispatch --partitions 1 --replication-factor 1
kafka-topics --create --bootstrap-server kafka:9092 --topic compliance.reports --partitions 1 --replication-factor 1
```

### 1.3 Python Kafka Utilities

```python
# kafka/utils.py
from kafka import KafkaProducer, KafkaConsumer
import json

def create_producer(bootstrap_servers='localhost:9093'):
    return KafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        acks='all',
        retries=3
    )

def create_consumer(topic, group_id, bootstrap_servers='localhost:9093'):
    return KafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        value_deserializer=lambda v: json.loads(v.decode('utf-8')),
        auto_offset_reset='earliest'
    )
```

---

## 🧪 Testing Strategy

### Unit Tests (Unchanged)
- Existing `tests/test_*.py` continue to test module logic
- No changes needed (modules still have same interfaces)

### Integration Tests (New)
```python
# tests/integration/test_kafka_flow.py
def test_telemetry_to_forecasting():
    """Verify telemetry event flows to forecasting service."""
    producer = create_producer()
    consumer = create_consumer('forecasting.predictions', 'test-group')
    
    # Publish test telemetry
    producer.send('telemetry.raw', test_event)
    
    # Verify forecasting service produced prediction
    messages = []
    for msg in consumer:
        messages.append(msg.value)
        if len(messages) >= 1:
            break
    
    assert messages[0]['forecast_consumption'] > 0
```

### End-to-End Test
```python
# tests/integration/test_end_to_end.py
def test_mqtt_to_dashboard_flow():
    """Full pipeline: MQTT → Kafka → Services → API → Dashboard."""
    # 1. Publish MQTT message
    mqtt_client.publish('supermarket/telemetry', test_payload)
    
    # 2. Wait for processing (poll dashboard API)
    time.sleep(2)
    response = requests.get('http://localhost:8000/api/v1/latest')
    
    # 3. Verify data flowed through entire pipeline
    assert response.status_code == 200
    assert response.json()['timestamp'] == test_payload['timestamp']
```

---

## 📊 Success Metrics

### Performance
- **Latency:** <1 second from MQTT publish to dashboard update
- **Throughput:** Handle 100+ events/second
- **Availability:** 99.9% uptime per service

### Quality
- **Test Coverage:** Maintain 100% test pass rate
- **Zero Data Loss:** All telemetry events persisted
- **Compliance:** R1-R6 rules still enforced

### Operations
- **Deployment Time:** <5 minutes for full stack
- **Recovery Time:** Services auto-restart within 30 seconds
- **Debugging:** Distributed traces available for all requests

---

## 🛡️ Risk Mitigation

### Risk 1: Kafka Cluster Failure
**Mitigation:** 
- Monolithic backend runs in parallel as fallback
- `docker-compose.monolith.yml` preserved for quick rollback
- Health checks detect Kafka issues early

### Risk 2: Increased Latency
**Mitigation:**
- Benchmark each phase, optimize before proceeding
- Consider batching for high-throughput scenarios
- Add caching at API Gateway

### Risk 3: Message Loss
**Mitigation:**
- Kafka `acks=all` for guaranteed delivery
- Dead letter queues for failed processing
- Idempotent consumers (handle duplicates)

### Risk 4: Debugging Complexity
**Mitigation:**
- OpenTelemetry tracing from day 1
- Correlation IDs in all messages
- Centralized logging (ELK stack or similar)

---

## 📅 Timeline Estimate

| Phase | Duration | Dependencies | Risk |
|-------|----------|--------------|------|
| Phase 1 (Infrastructure) | 2 hours | None | Low |
| Phase 2 (Forecasting) | 4 hours | Phase 1 | Medium |
| Phase 3 (MPC) | 3 hours | Phase 2 | Low |
| Phase 4 (DERMS) | 3 hours | Phase 3 | Medium |
| Phase 5 (Compliance) | 2 hours | Phase 4 | Low |
| Phase 6 (Ingestion + API) | 6 hours | Phase 5 | High |
| Phase 7 (Hardening) | 4 hours | Phase 6 | Medium |
| **Total** | **24 hours** | Sequential | **Medium** |

**Recommended Schedule:** 1-2 phases per week, with validation between each

---

## ✅ Phase 1 Checklist (Today's Session)

- [ ] Update docker-compose.yml with Zookeeper + Kafka
- [ ] Create topic creation script
- [ ] Add Kafka health checks
- [ ] Create Python Kafka utilities (`kafka/utils.py`)
- [ ] Test basic produce/consume flow
- [ ] Document Kafka access patterns
- [ ] Verify monolith still works
- [ ] Commit and push Phase 1 changes

---

## 📚 References

- [Apache Kafka Documentation](https://kafka.apache.org/documentation/)
- [Confluent Platform Quickstart](https://docs.confluent.io/platform/current/quickstart/ce-docker-quickstart.html)
- [Python Kafka Client](https://kafka-python.readthedocs.io/)
- [Microservices Patterns (Chris Richardson)](https://microservices.io/patterns/)

---

**Next Steps:** After Phase 1 completion, review this plan with the team and schedule Phase 2 implementation.

*Last Updated:* 2026-10-12  
*Status:* Phase 1 in progress  
*Owner:* Smart Supermarket B2G Team
