# MQTT Dual-Mode Ingestion System Documentation

**Project**: B2G Smart Supermarket Platform  
**Version**: 1.0  
**Last Updated**: 2024  

---

## 1. Overview

The B2G Smart Supermarket platform supports **dual-mode data ingestion** to accommodate both development/testing scenarios and production real-time streaming:

- **CSV Mode** (default): Batch-loads historical telemetry from disk for replay, simulation, and testing
- **MQTT Mode**: Streams live telemetry via Mosquitto broker for real-time pipeline execution

The mode is controlled via the `B2G_INGESTION_MODE` environment variable. Both modes share the same data schema and pipeline processing logic downstream.

### Design Intent

- **CSV Mode**: Deterministic replay of known datasets; ideal for unit/integration testing, compliance validation, and scenario analysis
- **MQTT Mode**: Low-latency streaming ingestion for production deployments, live dashboards, and real-time MPC coordination

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DUAL-MODE INGESTION                         │
└─────────────────────────────────────────────────────────────────────┘

CSV Mode (B2G_INGESTION_MODE=csv):
┌──────────────────┐
│ dataset_*.csv    │
└────────┬─────────┘
         │
         v
┌────────────────────────────┐
│ src/ingestion/loader.py    │
│ - load_dataset()           │
│ - Schema validation        │
│ - P2P dataset routing      │
└────────┬───────────────────┘
         │
         v
┌────────────────────────────┐
│ pandas.DataFrame           │
│ → iter_timesteps()         │
└────────┬───────────────────┘
         │
         v
┌────────────────────────────┐
│ Pipeline Processing        │
│ (Forecasting, MPC, DERMS)  │
└────────────────────────────┘


MQTT Mode (B2G_INGESTION_MODE=mqtt):
┌──────────────────────────────┐
│ mqtt_publisher.py (Replay)   │
│ Reads CSV → JSON → MQTT      │
└──────────┬───────────────────┘
           │
           v MQTT Publish
┌──────────────────────────────┐
│ Mosquitto Broker             │
│ Port 1883 (TCP)              │
│ Port 9001 (WebSocket)        │
└──────────┬───────────────────┘
           │
           v MQTT Subscribe
┌──────────────────────────────┐
│ mqtt_subscriber.py           │
│ - Buffers messages (deque)   │
│ - drain_as_dataframe()       │
└──────────┬───────────────────┘
           │
           v
┌──────────────────────────────┐
│ Application Code             │
│ (Manual integration required)│
└──────────┬───────────────────┘
           │
           v
┌──────────────────────────────┐
│ Pipeline Processing          │
│ (Forecasting, MPC, DERMS)    │
└──────────────────────────────┘
```

---

## 3. Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `B2G_INGESTION_MODE` | `csv` | Ingestion mode selector: `csv` or `mqtt` |
| `MQTT_BROKER_HOST` | `localhost` | Mosquitto broker hostname (use `mosquitto` in Docker) |
| `MQTT_BROKER_PORT` | `1883` | MQTT broker port (standard TCP) |
| `MQTT_TOPIC` | `supermarket/telemetry` | MQTT topic for telemetry stream |
| `MQTT_CLIENT_ID` | `b2g-ingestion` | Default client ID for subscribers |
| `B2G_P2P_ENABLED` | `false` | Enable P2P neighbor dataset loading (CSV mode only) |
| `B2G_SUPERMARKET_CSV` | `data1/dataset_modified.csv` | Path to enriched supermarket CSV (when P2P enabled) |
| `B2G_NEIGHBORS_CSV` | `data1/smart_supermarket_neighbor_buildings_4months_15min1.csv` | Path to neighbor buildings dataset |
| `B2G_DATASET_PATH` | `""` | Legacy dataset path override |
| `B2G_SELL_PRICE` | — | P2P energy sell price (€/kWh) |
| `B2G_WHEELING_BASE_FEE` | — | P2P wheeling base fee |
| `B2G_WHEELING_PER_KM` | — | P2P wheeling cost per km |
| `B2G_STEP_HOURS` | — | Simulation step duration (hours) |
| `B2G_PRODUCTION_TYPE_PRICE_FACTOR` | — | P2P production type pricing factor |

**Notes**:
- All env vars are read via `src/config.py` → `settings` singleton
- Docker Compose sets `MQTT_BROKER_HOST=mosquitto` automatically
- P2P features are **CSV-mode only** (see section 9)

---

## 4. Publisher Usage Guide

### Overview
`src/ingestion/mqtt_publisher.py` replays CSV dataset rows as JSON messages onto an MQTT topic.

### CLI Syntax
```bash
python -m src.ingestion.mqtt_publisher [OPTIONS]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--host HOST` | `settings.MQTT_BROKER_HOST` or `localhost` | Broker hostname |
| `--port PORT` | `1883` | Broker port |
| `--topic TOPIC` | `supermarket/telemetry` | Target MQTT topic |
| `--interval SECONDS` | `0.1` | Delay between row publishes (e.g., `1.0` = 1 row/sec) |
| `--dataset PATH` | Auto-detect via `load_dataset()` | Path to CSV dataset |

### Examples

**Publish to local Mosquitto at 1 row/second**:
```bash
python -m src.ingestion.mqtt_publisher --interval 1.0
```

**Publish to Docker Mosquitto service**:
```bash
python -m src.ingestion.mqtt_publisher --host mosquitto --interval 0.5
```

**Publish custom dataset to custom topic**:
```bash
python -m src.ingestion.mqtt_publisher \
  --dataset data1/dataset_modified.csv \
  --topic building/energy \
  --interval 0.2
```

**Fast replay for stress testing**:
```bash
python -m src.ingestion.mqtt_publisher --interval 0.01
```

### Behavior

- **Client ID**: `b2g-publisher` (fixed)
- **QoS Level**: 0 (fire-and-forget)
- **Message Format**: JSON dict with keys:
  - `timestamp` (str, ISO format)
  - `occupancy` (int)
  - `demand_response` (int)
  - All other fields: float
- **Progress**: Prints every 500 rows (`Published 500 messages...`)
- **Graceful Shutdown**: Handles `Ctrl+C` (`KeyboardInterrupt`) cleanly
- **Scope**: Publishes **supermarket telemetry only** — does NOT stream neighbor building data

### Implementation Details
- Uses `paho-mqtt >= 2.0` with `CallbackAPIVersion.VERSION2`
- Reads full CSV via `load_dataset()`, iterates row-by-row
- Converts pandas `Timestamp` → ISO string, `np.float64` → native Python float

---

## 5. Subscriber API Reference

### Class: `MQTTSubscriber`

**Module**: `src.ingestion.mqtt_subscriber`

```python
from src.ingestion.mqtt_subscriber import MQTTSubscriber

subscriber = MQTTSubscriber(
    host="localhost",           # default: settings.MQTT_BROKER_HOST
    port=1883,                  # default: settings.MQTT_BROKER_PORT
    topic="supermarket/telemetry",  # default: settings.MQTT_TOPIC
    max_buffer=1000             # default: 1000 messages
)
```

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | `settings.MQTT_BROKER_HOST` | Broker hostname |
| `port` | `int` | `settings.MQTT_BROKER_PORT` | Broker port |
| `topic` | `str` | `settings.MQTT_TOPIC` | MQTT topic to subscribe to |
| `max_buffer` | `int` | `1000` | Max messages buffered (oldest dropped if exceeded) |

### Methods

#### `start() -> None`
Connects to broker, subscribes to topic (QoS 1), starts background listener thread.

```python
subscriber.start()
```

**Raises**: `ConnectionRefusedError` if broker unreachable.

#### `stop() -> None`
Stops background thread, disconnects from broker.

```python
subscriber.stop()
```

#### `drain() -> list[dict]`
Returns all buffered messages as list of dicts, clears buffer.

```python
messages = subscriber.drain()
for msg in messages:
    print(msg['timestamp'], msg['pv_generation_kw'])
```

#### `drain_as_dataframe() -> pd.DataFrame`
Returns buffered messages as pandas DataFrame, clears buffer.  
Automatically parses `timestamp` column as datetime.

```python
df = subscriber.drain_as_dataframe()
if not df.empty:
    print(df.head())
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `is_running` | `bool` | `True` if subscriber is active |
| `buffer_size` | `int` | Current number of buffered messages |

### Full Example

```python
from src.ingestion.mqtt_subscriber import MQTTSubscriber
import time

sub = MQTTSubscriber(host="mosquitto", max_buffer=500)
sub.start()

try:
    while True:
        time.sleep(5)  # Poll every 5 seconds
        df = sub.drain_as_dataframe()
        if not df.empty:
            print(f"Received {len(df)} rows")
            # Process df through pipeline...
finally:
    sub.stop()
```

### Error Handling

- **Parse Errors**: Invalid JSON messages are logged as warnings (never crash)
- **Buffer Overflow**: Oldest messages silently dropped when `max_buffer` exceeded (see Known Issues)
- **Connection Loss**: No automatic reconnection logic implemented

---

## 6. Dual-Mode Data Flow

### CSV Mode (`B2G_INGESTION_MODE=csv`)

**Step-by-step**:

1. Application calls `load_dataset(path)` from `src/ingestion/loader.py`
2. Loader checks `B2G_P2P_ENABLED` / `B2G_SUPERMARKET_CSV`:
   - If P2P enabled → loads `data1/dataset_modified.csv` (enriched schema with `p2p_energy` column)
   - Else → loads default dataset
3. Schema validation: 30 required columns + 4 optional cold-chain columns
4. Data cleaning: forward/back-fill NaNs, chronological sort
5. Returns `pd.DataFrame` ready for `iter_timesteps()`
6. P2P neighbor data loaded separately via `src/p2p/loader.py` → `NeighborBook`
7. Pipeline consumes timestep-by-timestep via iterator

**Advantages**:
- Deterministic, repeatable
- Full P2P dataset support
- No broker dependency

**Use Cases**:
- Unit/integration testing
- Compliance scenario validation
- Batch analysis

---

### MQTT Mode (`B2G_INGESTION_MODE=mqtt`)

**Step-by-step**:

1. **Publisher Side** (optional, for dataset replay):
   ```bash
   python -m src.ingestion.mqtt_publisher --interval 1.0
   ```
   - Reads CSV via `load_dataset()`
   - Publishes each row as JSON to `supermarket/telemetry` topic

2. **Broker**: Mosquitto routes messages to subscribers

3. **Subscriber Side** (application code):
   ```python
   from src.ingestion.mqtt_subscriber import MQTTSubscriber
   
   sub = MQTTSubscriber()
   sub.start()
   
   # Periodic drain (e.g., every API request or background task)
   df = sub.drain_as_dataframe()
   # Feed df into pipeline...
   ```

4. **Pipeline Integration** (manual):
   - Application must explicitly instantiate `MQTTSubscriber`
   - Must periodically call `drain_as_dataframe()` to retrieve buffered data
   - **No automatic wiring exists** (see Known Issues)

**Advantages**:
- Low-latency streaming
- Decoupled producer/consumer
- WebSocket support (port 9001) for browser clients

**Limitations**:
- No P2P neighbor dataset streaming (see section 9)
- Requires manual subscriber integration
- Buffer overflow risk if consumer slow

**Use Cases**:
- Live dashboard updates
- Real-time MPC coordination
- Production streaming deployments

---

## 7. Mosquitto Configuration

**Config File**: `docker/mosquitto/mosquitto.conf`

```conf
listener 1883
allow_anonymous true

listener 9001
protocol websockets
```

### Ports

| Port | Protocol | Description |
|------|----------|-------------|
| `1883` | MQTT (TCP) | Standard MQTT protocol |
| `9001` | MQTT over WebSockets | Browser-compatible MQTT (for web dashboards) |

### Security

- **Authentication**: Anonymous connections allowed (`allow_anonymous true`)
- **TLS/SSL**: Not configured (plaintext only)
- **Authorization**: No topic-level ACLs

**⚠️ Production Warning**: This configuration is **development-only**. Production deployments should:
- Require authentication (username/password or certificates)
- Enable TLS encryption
- Implement topic ACLs for multi-tenant isolation

### Testing Broker

**Verify broker is running**:
```bash
docker compose ps mosquitto
```

**Test publish from host**:
```bash
mosquitto_pub -h localhost -p 1883 -t test/topic -m "Hello MQTT"
```

**Test subscribe from host**:
```bash
mosquitto_sub -h localhost -p 1883 -t test/topic
```

---

## 8. Docker Compose Integration

### Current Configuration

**File**: `docker-compose.yml`

```yaml
services:
  mosquitto:
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./docker/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf

  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      B2G_INGESTION_MODE: csv          # ← CSV mode by default
      MQTT_BROKER_HOST: mosquitto      # ← Correct service name
      MQTT_BROKER_PORT: 1883
    depends_on:
      - mosquitto
      - timescaledb
      - redis
```

### Switching to MQTT Mode

**Option 1: Override in Compose File**

Edit `docker-compose.yml`:
```yaml
services:
  backend:
    environment:
      B2G_INGESTION_MODE: mqtt  # ← Change to mqtt
```

**Option 2: Environment Variable Override**

```bash
B2G_INGESTION_MODE=mqtt docker compose up
```

**Option 3: `.env` File**

Create `.env` in project root:
```env
B2G_INGESTION_MODE=mqtt
```

Then:
```bash
docker compose up
```

### Running Publisher in Docker

**Add publisher service** (optional):
```yaml
services:
  publisher:
    build: .
    command: python -m src.ingestion.mqtt_publisher --host mosquitto --interval 1.0
    environment:
      MQTT_BROKER_HOST: mosquitto
    depends_on:
      - mosquitto
```

Start with:
```bash
docker compose up mosquitto publisher
```

### Verifying MQTT Mode

**Check logs**:
```bash
docker compose logs backend | grep -i mqtt
```

**Expected output** (if subscriber integrated):
```
INFO:src.ingestion.mqtt_subscriber:Connected to mosquitto:1883
INFO:src.ingestion.mqtt_subscriber:Subscribed to supermarket/telemetry
```

---

## 9. P2P / Neighbor Data Limitations in MQTT Mode

### Current Limitation

**P2P neighbor building datasets are NOT streamed over MQTT.**

### Details

- **CSV Mode**: Neighbor data loaded from `data1/smart_supermarket_neighbor_buildings_4months_15min1.csv` via `src/p2p/loader.py`
- **MQTT Mode**: `mqtt_publisher.py` only publishes **supermarket telemetry** from the main dataset
- **Impact**: Dynamic P2P trading features (neighbor surplus/deficit matching) are **unavailable in MQTT mode**

### Workaround Options

#### Option A: Hybrid Mode (Current Best Practice)
```python
# Load neighbor data from CSV (one-time)
from src.p2p.loader import load_neighbors
neighbor_book = load_neighbors()

# Stream supermarket telemetry via MQTT
from src.ingestion.mqtt_subscriber import MQTTSubscriber
sub = MQTTSubscriber()
sub.start()

while True:
    df = sub.drain_as_dataframe()
    for row in df.itertuples():
        neighbors = neighbor_book.at(row.timestamp)
        # Run P2P matching logic...
```

#### Option B: Multi-Topic Publishing (Future Enhancement)
Publish neighbor data to separate topics:
- `supermarket/telemetry` — main building
- `neighbors/building_1` — neighbor 1
- `neighbors/building_2` — neighbor 2
- etc.

Subscriber subscribes to all topics and reconstructs `NeighborBook` in-memory.

#### Option C: Full CSV Mode for P2P Scenarios
Use `B2G_INGESTION_MODE=csv` when P2P features are required.

### Recommendation

For **real-time P2P trading in production**, implement **Option B** (multi-topic publishing) as a future enhancement.

---

## 10. Testing Guide

### Local Testing (Without Docker)

#### Prerequisites
```bash
pip install paho-mqtt
```

Install Mosquitto broker:
- **Ubuntu/Debian**: `sudo apt install mosquitto`
- **macOS**: `brew install mosquitto`
- **Windows**: Download from https://mosquitto.org/download/

Start broker:
```bash
mosquitto -c docker/mosquitto/mosquitto.conf
```

#### Test 1: Publisher → Broker → Subscriber

**Terminal 1 (Subscriber)**:
```bash
python -c "
from src.ingestion.mqtt_subscriber import MQTTSubscriber
import time

sub = MQTTSubscriber(host='localhost')
sub.start()
print('Subscriber started, waiting for messages...')

try:
    while True:
        time.sleep(2)
        df = sub.drain_as_dataframe()
        if not df.empty:
            print(f'Received {len(df)} rows')
            print(df.head())
except KeyboardInterrupt:
    sub.stop()
"
```

**Terminal 2 (Publisher)**:
```bash
python -m src.ingestion.mqtt_publisher --interval 1.0
```

**Expected**: Terminal 1 prints batches of received telemetry every 2 seconds.

#### Test 2: Verify Message Schema

```bash
mosquitto_sub -h localhost -t supermarket/telemetry -C 1 | python -m json.tool
```

**Expected output**:
```json
{
  "timestamp": "2024-01-01T00:00:00",
  "occupancy": 150,
  "demand_response": 0,
  "pv_generation_kw": 12.34,
  "battery_soc_kwh": 45.67,
  ...
}
```

---

### Docker Testing

#### Test 1: Broker Connectivity

```bash
docker compose up -d mosquitto
docker compose exec mosquitto mosquitto_sub -t test/topic &
docker compose exec mosquitto mosquitto_pub -t test/topic -m "ping"
```

**Expected**: `ping` appears in subscriber output.

#### Test 2: Publisher Container

```bash
docker compose up -d mosquitto
docker run --rm --network smartsupermarket_default \
  -e MQTT_BROKER_HOST=mosquitto \
  $(docker compose images -q backend) \
  python -m src.ingestion.mqtt_publisher --interval 1.0
```

#### Test 3: Full Stack with MQTT Mode

```bash
# Override ingestion mode
B2G_INGESTION_MODE=mqtt docker compose up

# In another terminal, check backend logs
docker compose logs -f backend

# In another terminal, publish data
docker run --rm --network smartsupermarket_default \
  -e MQTT_BROKER_HOST=mosquitto \
  $(docker compose images -q backend) \
  python -m src.ingestion.mqtt_publisher --interval 0.5
```

---

### Unit Test Template

**File**: `tests/test_mqtt.py` (currently missing)

```python
import pytest
import time
from src.ingestion.mqtt_subscriber import MQTTSubscriber
from src.ingestion.mqtt_publisher import MQTTPublisher  # hypothetical

@pytest.mark.mqtt
def test_subscriber_lifecycle():
    sub = MQTTSubscriber(host="localhost")
    assert not sub.is_running
    
    sub.start()
    assert sub.is_running
    
    sub.stop()
    assert not sub.is_running

@pytest.mark.mqtt
def test_message_buffering():
    sub = MQTTSubscriber(host="localhost", max_buffer=10)
    sub.start()
    
    # Publish 5 test messages (requires separate publisher)
    time.sleep(1)
    
    messages = sub.drain()
    assert len(messages) == 5
    assert sub.buffer_size == 0
    
    sub.stop()

@pytest.mark.mqtt
def test_drain_as_dataframe():
    sub = MQTTSubscriber(host="localhost")
    sub.start()
    
    time.sleep(2)
    df = sub.drain_as_dataframe()
    
    assert 'timestamp' in df.columns
    assert df['timestamp'].dtype == 'datetime64[ns]'
    
    sub.stop()
```

**Run with**:
```bash
pytest tests/test_mqtt.py -m mqtt
```

---

## 11. Troubleshooting

### Issue: Publisher Cannot Connect

**Symptom**:
```
ConnectionRefusedError: [Errno 111] Connection refused
```

**Solutions**:
1. Verify broker is running: `docker compose ps mosquitto` or `ps aux | grep mosquitto`
2. Check port availability: `netstat -tuln | grep 1883`
3. Verify hostname: use `mosquitto` in Docker, `localhost` on host
4. Check firewall rules (Windows Defender, iptables, etc.)

---

### Issue: Subscriber Receives No Messages

**Symptom**: `sub.drain()` always returns empty list.

**Solutions**:
1. Verify topic name matches: `settings.MQTT_TOPIC` vs publisher `--topic`
2. Check subscriber is started: `sub.is_running` should be `True`
3. Verify broker logs: `docker compose logs mosquitto | grep subscribed`
4. Test with `mosquitto_sub`:
   ```bash
   mosquitto_sub -h localhost -t supermarket/telemetry
   ```

---

### Issue: Messages Are Dropped

**Symptom**: Publisher sends 10,000 messages but subscriber only receives 1,000.

**Cause**: Buffer overflow (default `max_buffer=1000`).

**Solutions**:
1. Increase buffer size:
   ```python
   sub = MQTTSubscriber(max_buffer=10000)
   ```
2. Drain more frequently:
   ```python
   while True:
       time.sleep(0.5)  # Drain every 500ms instead of 5 seconds
       df = sub.drain_as_dataframe()
   ```
3. Slow down publisher: `--interval 0.5` instead of `--interval 0.1`

---

### Issue: Pipeline Not Using MQTT Data

**Symptom**: Set `B2G_INGESTION_MODE=mqtt` but pipeline still reads CSV.

**Cause**: `loader.py` does NOT automatically switch to MQTT mode.

**Solution**: Manually integrate subscriber in application code (see Known Issues #1).

---

### Issue: P2P Features Not Working in MQTT Mode

**Symptom**: Neighbor building data missing, P2P trades not executed.

**Cause**: Neighbor data not published over MQTT (see section 9).

**Solution**: Use CSV mode or implement hybrid approach (section 9, Option A).

---

### Issue: Invalid JSON Parse Errors

**Symptom**:
```
WARNING:src.ingestion.mqtt_subscriber:Failed to parse message: ...
```

**Cause**: Corrupted message or incompatible publisher.

**Solutions**:
1. Verify publisher is official `mqtt_publisher.py`
2. Check broker logs for anomalies
3. Test message manually:
   ```bash
   mosquitto_pub -h localhost -t supermarket/telemetry -m '{"timestamp":"2024-01-01T00:00:00","occupancy":100}'
   ```

---

### Issue: WebSocket Connection Failed (Port 9001)

**Symptom**: Browser-based MQTT client cannot connect.

**Cause**: WebSocket listener not configured or port not exposed.

**Solutions**:
1. Verify `mosquitto.conf` has WebSocket listener:
   ```conf
   listener 9001
   protocol websockets
   ```
2. Check Docker port mapping: `docker compose ps mosquitto` should show `0.0.0.0:9001->9001/tcp`
3. Test with browser tool: https://www.hivemq.com/demos/websocket-client/

---

## 12. Known Issues & Gaps

### 🔴 Critical: No Automatic MQTT Pipeline Integration

**Severity**: CRITICAL  
**Component**: `src/ingestion/loader.py`, application entrypoints

**Description**:  
The `B2G_INGESTION_MODE` environment variable is defined in `src/config.py` but is NOT consumed by `loader.py` or any pipeline entrypoint. Setting `B2G_INGESTION_MODE=mqtt` has no automatic effect. The `MQTTSubscriber` class exists but must be manually instantiated and wired by application code.

**Impact**:  
- Developers must write custom integration code
- Risk of inconsistent implementations
- MQTT mode is effectively unusable without manual plumbing

**Recommended Fix**:
1. Add MQTT mode detection in `loader.py`:
   ```python
   def load_dataset_auto(path=None):
       if settings.INGESTION_MODE == "mqtt":
           return MQTTDataSource()  # New class wrapping MQTTSubscriber
       else:
           return load_dataset(path)
   ```
2. Or add FastAPI startup event in `src/api/main.py`:
   ```python
   @app.on_event("startup")
   async def startup_mqtt():
       if settings.INGESTION_MODE == "mqtt":
           subscriber = MQTTSubscriber()
           subscriber.start()
           app.state.mqtt_subscriber = subscriber
   ```

---

### 🟡 High: No Neighbor Data Streaming (P2P Limitation)

**Severity**: HIGH  
**Component**: `src/ingestion/mqtt_publisher.py`, P2P subsystem

**Description**:  
Publisher only streams supermarket telemetry. Neighbor building datasets (`smart_supermarket_neighbor_buildings_*.csv`) are not published over MQTT, making dynamic P2P trading impossible in MQTT mode.

**Impact**:  
- P2P features unavailable in real-time streaming scenarios
- Forces use of CSV mode for P2P testing/production

**Recommended Fix**:
1. Implement multi-topic publishing:
   - `supermarket/telemetry` — main building
   - `neighbors/building_1` — neighbor 1 telemetry
   - `neighbors/building_2` — neighbor 2 telemetry
2. Update `mqtt_publisher.py` to load and publish neighbor datasets
3. Update `MQTTSubscriber` to support multi-topic subscriptions
4. Add `NeighborBook.from_mqtt(subscriber)` constructor

---

### 🟡 High: Buffer Overflow Silently Drops Messages

**Severity**: HIGH  
**Component**: `src/ingestion/mqtt_subscriber.py`

**Description**:  
Subscriber uses `collections.deque(maxlen=1000)`. When buffer is full, oldest messages are silently discarded without error, warning, or metric.

**Impact**:  
- Data loss during slow consumer / fast producer scenarios
- No visibility into message loss
- Pipeline may process incomplete data without knowing

**Recommended Fix**:
1. Add overflow counter:
   ```python
   self._overflow_count = 0
   
   def _on_message(self, client, userdata, msg):
       if len(self._buffer) >= self._max_buffer:
           self._overflow_count += 1
           logger.warning(f"Buffer overflow: {self._overflow_count} messages dropped")
       self._buffer.append(data)
   ```
2. Expose metric: `subscriber.overflow_count`
3. Or raise exception on overflow (fail-fast)

---

### 🟢 Medium: No MQTT Integration Tests

**Severity**: MEDIUM  
**Component**: `tests/`

**Description**:  
No `tests/test_mqtt.py` or equivalent test suite exists. MQTT functionality is untested in CI/CD pipeline.

**Impact**:  
- Regressions may go undetected
- No automated validation of MQTT mode

**Recommended Fix**:
1. Add `tests/test_mqtt.py` with subscriber lifecycle, buffering, and parse error tests
2. Use `pytest-mqtt` or embedded broker for CI tests
3. Add Docker-based integration test in GitHub Actions

---

### 🟢 Low: Docker Compose Defaults to CSV Mode

**Severity**: LOW  
**Component**: `docker-compose.yml`

**Description**:  
Backend service has `B2G_INGESTION_MODE: csv` hardcoded. Users must override manually to enable MQTT mode.

**Impact**:  
- Extra configuration step
- Confusion for new users expecting MQTT mode to "just work"

**Recommended Fix**:
1. Document override process clearly (✅ done in section 8)
2. Or provide separate `docker-compose.mqtt.yml` override file:
   ```yaml
   services:
     backend:
       environment:
         B2G_INGESTION_MODE: mqtt
   ```
   Usage: `docker compose -f docker-compose.yml -f docker-compose.mqtt.yml up`

---

## Summary Table

| Issue | Severity | Component | Status |
|-------|----------|-----------|--------|
| No automatic MQTT pipeline integration | 🔴 CRITICAL | loader.py, entrypoints | Open |
| No neighbor data streaming (P2P) | 🟡 HIGH | mqtt_publisher.py | Open |
| Buffer overflow silently drops messages | 🟡 HIGH | mqtt_subscriber.py | Open |
| No MQTT integration tests | 🟢 MEDIUM | tests/ | Open |
| Docker Compose defaults to CSV mode | 🟢 LOW | docker-compose.yml | Documented |

---

## Appendix: Full Message Schema

**Topic**: `supermarket/telemetry`  
**Format**: JSON

```json
{
  "timestamp": "2024-01-01T00:00:00",
  "occupancy": 150,
  "demand_response": 0,
  "pv_generation_kw": 12.34,
  "wind_generation_kw": 5.67,
  "hvac_consumption_kw": 23.45,
  "lighting_consumption_kw": 8.90,
  "refrigeration_consumption_kw": 45.67,
  "it_consumption_kw": 3.21,
  "checkout_consumption_kw": 2.10,
  "battery_soc_kwh": 78.90,
  "battery_capacity_kwh": 100.0,
  "battery_charge_rate_kw": 10.0,
  "battery_discharge_rate_kw": 10.0,
  "grid_import_limit_kw": 150.0,
  "grid_export_limit_kw": 100.0,
  "electricity_price_eur_per_kwh": 0.25,
  "temperature_c": 22.5,
  "humidity_percent": 55.0,
  "solar_irradiance_w_per_m2": 800.0,
  "wind_speed_m_per_s": 7.5,
  "tier_1_load_kw": 50.0,
  "tier_2_load_kw": 30.0,
  "tier_3_load_kw": 20.0,
  "tier_4_load_kw": 10.0,
  "critical_load_kw": 50.0,
  "non_critical_load_kw": 60.0,
  "total_consumption_kw": 110.0,
  "net_load_kw": 91.99,
  "p2p_energy_kw": 0.0,
  "fridge_temp_c": 3.5,
  "freezer_temp_c": -20.0,
  "chilled_display_temp_c": 4.0,
  "frozen_display_temp_c": -18.5
}
```

**Note**: Last 4 fields (cold-chain temperatures) are optional and only present when cold-chain monitoring is enabled.

---

**End of Documentation**
