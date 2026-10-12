# Docker Stack Configuration Report
_Generated: 2024-12-19_

## Executive Summary

The Docker Compose stack consists of **4 services** (mosquitto, timescaledb, redis, backend). The configuration is functional but **missing critical health checks** and **proper dependency conditions** that would ensure reliable startup order and service availability. The stack uses a simple approach without custom networks, relying on Docker's default bridge network for service discovery.

**Critical Issues Found: 3**
**Warnings: 2**

---

## Service Inventory

### 1. mosquitto (MQTT Broker)
- **Image**: `eclipse-mosquitto:2`
- **Container Name**: `b2g-mosquitto`
- **Ports**: 
  - `1883:1883` (MQTT protocol)
  - `9001:9001` (WebSocket protocol)
- **Health Check**: ❌ **MISSING**
- **Depends On**: None
- **Volumes**: 
  - `./docker/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf` (bind mount)
- **Restart Policy**: `unless-stopped`
- **Status**: ⚠️ No health check means dependent services cannot verify availability

### 2. timescaledb (PostgreSQL + TimescaleDB)
- **Image**: `timescale/timescaledb:latest-pg16`
- **Container Name**: `b2g-timescaledb`
- **Ports**: `5432:5432`
- **Health Check**: ❌ **MISSING**
- **Required Health Check**: `pg_isready -U b2g -d b2g`
- **Depends On**: None
- **Environment Variables**:
  - `POSTGRES_DB=b2g`
  - `POSTGRES_USER=b2g`
  - `POSTGRES_PASSWORD=b2g_password`
- **Volumes**: 
  - `timescale_data:/var/lib/postgresql/data` (named volume)
- **Restart Policy**: `unless-stopped`
- **Status**: ❌ **CRITICAL** - Missing health check, but backend depends on it

### 3. redis (Cache/State Store)
- **Image**: `redis:7-alpine`
- **Container Name**: `b2g-redis`
- **Ports**: `6379:6379`
- **Health Check**: ❌ **MISSING**
- **Required Health Check**: `redis-cli ping`
- **Depends On**: None
- **Volumes**: None (data not persisted)
- **Restart Policy**: `unless-stopped`
- **Status**: ❌ **CRITICAL** - Missing health check, but backend depends on it

### 4. backend (FastAPI Application)
- **Image**: Built from local `Dockerfile`
- **Container Name**: `b2g-backend`
- **Ports**: `8000:8000`
- **Health Check**: ❌ **MISSING**
- **Recommended Health Check**: `curl -f http://localhost:8000/health || exit 1`
- **Depends On**: 
  - `mosquitto` (no condition specified)
  - `timescaledb` (no condition specified)
  - `redis` (no condition specified)
- **Environment Variables**:
  - `B2G_INGESTION_MODE=csv`
  - `MQTT_BROKER_HOST=mosquitto`
  - `TIMESCALE_HOST=timescaledb`
  - `TIMESCALE_PORT=5432`
  - `TIMESCALE_DB=b2g`
  - `TIMESCALE_USER=b2g`
  - `TIMESCALE_PASSWORD=b2g_password` (hardcoded credential)
  - `REDIS_HOST=redis`
  - `REDIS_PORT=6379`
- **Volumes**: None
- **Restart Policy**: `unless-stopped`
- **Status**: ⚠️ Depends on services without health checks; may start before dependencies are ready

---

## Health Check Analysis

### Current State vs. Requirements

| Service | Current Health Check | Required Health Check | Status |
|---------|---------------------|----------------------|--------|
| **mosquitto** | None | TCP check on port 1883 | ❌ Missing |
| **timescaledb** | None | `pg_isready -U b2g -d b2g` | ❌ Missing |
| **redis** | None | `redis-cli ping` | ❌ Missing |
| **backend** | None | `curl -f http://localhost:8000/health` | ❌ Missing |

### Impact

Without health checks:
1. **Backend may start before dependencies are ready**, leading to connection errors and crash loops
2. **Docker Compose cannot report accurate service status** (`docker compose ps` will show "running" even if services are failing)
3. **No automatic service recovery** when services enter unhealthy states
4. **Dependency orchestration is unreliable** - depends_on only waits for container start, not service readiness

### CI/CD Comparison

The GitHub Actions CI workflow (`.github/workflows/ci.yml`) **correctly implements health checks**:
- TimescaleDB: `pg_isready -U b2g -d b2g` ✅
- Redis: `redis-cli ping` ✅

This discrepancy means **local Docker Compose deployments are less reliable than CI test runs**.

---

## Dependency & Startup Order

### Declared Dependencies

```
mosquitto (no dependencies)
  ↑
timescaledb (no dependencies)
  ↑
redis (no dependencies)
  ↑
backend → depends_on: [mosquitto, timescaledb, redis]
```

### Actual Startup Behavior

**Without health check conditions**, Docker Compose starts services in this order:
1. `mosquitto`, `timescaledb`, `redis` (parallel start)
2. `backend` (starts after containers #1-3 are created, NOT after they're ready)

**Problem**: Backend can start 1-2 seconds after the containers start, but:
- TimescaleDB needs ~5-10 seconds to initialize the database
- Mosquitto needs ~1-2 seconds to load configuration and start listeners
- Redis is typically ready in <1 second

**Result**: Backend likely crashes on first startup attempt, then restarts (due to `restart: unless-stopped`) and succeeds on retry.

### Recommended Startup Order

```yaml
# Add to each dependency in backend service:
depends_on:
  mosquitto:
    condition: service_healthy
  timescaledb:
    condition: service_healthy
  redis:
    condition: service_healthy
```

This ensures backend waits until all dependencies pass their health checks.

---

## Volume Mounts

### Named Volumes

| Volume Name | Mounted In | Path | Purpose |
|-------------|-----------|------|---------|
| `timescale_data` | timescaledb | `/var/lib/postgresql/data` | PostgreSQL data persistence |

**Status**: ✅ Correctly defined and mounted

### Bind Mounts

| Host Path | Container Path | Service | Purpose |
|-----------|---------------|---------|---------|
| `./docker/mosquitto/mosquitto.conf` | `/mosquitto/config/mosquitto.conf` | mosquitto | MQTT broker configuration |

**Status**: ✅ Configuration file exists and is correctly mounted

### Missing Volumes

1. **Redis data persistence**: Redis is configured without a volume, meaning all cached data is lost on container restart.
   - **Impact**: Low (Redis is used as a cache with graceful degradation)
   - **Recommendation**: Add volume if persistent caching is needed: `redis_data:/data`

2. **Mosquitto data/logs**: No persistence for MQTT messages or logs
   - **Impact**: Low for current use case (pub/sub messaging is ephemeral)
   - **Recommendation**: Add if message persistence is required:
     ```yaml
     volumes:
       - mosquitto_data:/mosquitto/data
       - mosquitto_logs:/mosquitto/log
     ```

---

## Network Configuration

### Current Configuration

- **Network Mode**: Default bridge network (no custom network defined)
- **Service Discovery**: Docker's built-in DNS resolver
- **Service Names**: Used as hostnames (e.g., `mosquitto`, `timescaledb`, `redis`)

### Analysis

**Advantages**:
- Simple, no configuration needed
- Automatic service discovery by container/service name
- Suitable for single-host deployments

**Disadvantages**:
- All services share the default bridge network (less isolation)
- Cannot segment services by role (e.g., separate data and messaging tiers)
- No IP address management (IPAM) control

**Status**: ✅ Acceptable for current architecture

**Recommendation for Production**: Define a custom network:
```yaml
networks:
  b2g_network:
    driver: bridge

# Add to each service:
services:
  mosquitto:
    networks:
      - b2g_network
```

---

## Environment Variables

### Backend Service Environment Variables

| Variable | Value | Source | Status |
|----------|-------|--------|--------|
| `B2G_INGESTION_MODE` | `csv` | docker-compose.yml | ✅ |
| `MQTT_BROKER_HOST` | `mosquitto` | docker-compose.yml | ✅ |
| `TIMESCALE_HOST` | `timescaledb` | docker-compose.yml | ✅ |
| `TIMESCALE_PORT` | `5432` | docker-compose.yml | ✅ |
| `TIMESCALE_DB` | `b2g` | docker-compose.yml | ✅ |
| `TIMESCALE_USER` | `b2g` | docker-compose.yml | ✅ |
| `TIMESCALE_PASSWORD` | `b2g_password` | docker-compose.yml | ⚠️ Hardcoded |
| `REDIS_HOST` | `redis` | docker-compose.yml | ✅ |
| `REDIS_PORT` | `6379` | docker-compose.yml | ✅ |

### TimescaleDB Service Environment Variables

| Variable | Value | Source | Status |
|----------|-------|--------|--------|
| `POSTGRES_DB` | `b2g` | docker-compose.yml | ✅ |
| `POSTGRES_USER` | `b2g` | docker-compose.yml | ✅ |
| `POSTGRES_PASSWORD` | `b2g_password` | docker-compose.yml | ⚠️ Hardcoded |

### Security Concerns

1. **Hardcoded Credentials**: Database password is hardcoded in `docker-compose.yml`
   - **Risk**: Medium (acceptable for development, unacceptable for production)
   - **Recommendation**: Use `.env` file with environment variable substitution:
     ```yaml
     TIMESCALE_PASSWORD: ${TIMESCALE_PASSWORD:-b2g_password}
     ```

2. **No .env File**: No `.env` or `.env.example` file found
   - **Impact**: Users must manually edit `docker-compose.yml` to change configuration
   - **Recommendation**: Create `.env.example` with documented variables

---

## Configuration Issues Found

### Critical Issues (Must Fix)

1. **Missing Health Checks on All Services**
   - **Impact**: Backend may start before dependencies are ready, causing connection failures
   - **Fix**: Add health checks to all four services (see recommendations below)
   - **Priority**: HIGH

2. **Missing `condition: service_healthy` in Backend Dependencies**
   - **Impact**: Backend starts as soon as containers are created, not when services are ready
   - **Fix**: Add `condition: service_healthy` to all three dependencies in backend service
   - **Priority**: HIGH

3. **No .env File or .env.example**
   - **Impact**: Poor developer experience, hardcoded credentials, difficult to customize
   - **Fix**: Create `.env.example` with documented variables
   - **Priority**: MEDIUM

### Warnings (Should Fix)

4. **Hardcoded Database Credentials**
   - **Impact**: Security risk if `docker-compose.yml` is shared or committed to public repos
   - **Fix**: Use environment variable substitution from `.env` file
   - **Priority**: MEDIUM

5. **Redis Data Not Persisted**
   - **Impact**: Cache data lost on container restart (graceful degradation exists in code)
   - **Fix**: Add volume mount for `/data` if persistence is desired
   - **Priority**: LOW

### Informational

6. **No Custom Network Defined**
   - **Impact**: Minimal for current use case; limits future segmentation options
   - **Fix**: Define `b2g_network` for better isolation
   - **Priority**: LOW

7. **Mosquitto Data/Logs Not Persisted**
   - **Impact**: Minimal for current pub/sub use case
   - **Fix**: Add volumes if message persistence/logging is needed
   - **Priority**: LOW

---

## Recommended Health Check Configurations

### Add to docker-compose.yml:

```yaml
services:
  mosquitto:
    # ... existing config ...
    healthcheck:
      test: ["CMD", "timeout", "5", "sh", "-c", "echo > /dev/tcp/127.0.0.1/1883"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  timescaledb:
    # ... existing config ...
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U b2g -d b2g"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  redis:
    # ... existing config ...
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 5s

  backend:
    # ... existing config ...
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    depends_on:
      mosquitto:
        condition: service_healthy
      timescaledb:
        condition: service_healthy
      redis:
        condition: service_healthy
```

**Note**: The backend Dockerfile may need `curl` installed:
```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*
```

---

## Quick Start Guide

### Prerequisites

1. **Docker**: Version 20.10 or later
2. **Docker Compose**: Version 2.0 or later (included with Docker Desktop)
3. **Operating System**: Linux, macOS, or Windows with WSL2
4. **Disk Space**: ~2GB for images and data volumes

Verify installation:
```bash
docker --version
docker compose version
```

### Environment Setup

1. **Create .env file** (currently missing, will need to be created):
   ```bash
   # Copy example (once created)
   cp .env.example .env
   
   # Edit as needed
   nano .env
   ```

2. **Verify directory structure**:
   ```
   SmartSupermarket/
   ├── docker-compose.yml
   ├── Dockerfile
   ├── docker/
   │   └── mosquitto/
   │       └── mosquitto.conf
   ├── src/
   ├── requirements.txt
   └── .env (you create this)
   ```

### Start the Stack

1. **Build and start all services**:
   ```bash
   cd "c:\Users\user\Desktop\Digital\Smart building\SmartSupermarket"
   docker compose up -d
   ```

   This will:
   - Pull required images (mosquitto, timescaledb, redis)
   - Build the backend image from Dockerfile
   - Create networks and volumes
   - Start all containers in detached mode

2. **View startup logs**:
   ```bash
   # All services
   docker compose logs -f
   
   # Specific service
   docker compose logs -f backend
   ```

3. **Stop viewing logs**: Press `Ctrl+C`

### Verify Services

#### Check Container Status
```bash
docker compose ps
```

Expected output (all should show "running"):
```
NAME                IMAGE                              STATUS
b2g-backend         smartsupermarket-backend          Up X seconds
b2g-mosquitto       eclipse-mosquitto:2               Up X seconds
b2g-redis           redis:7-alpine                    Up X seconds
b2g-timescaledb     timescale/timescaledb:latest-pg16 Up X seconds
```

#### Check Individual Services

1. **TimescaleDB**:
   ```bash
   docker exec b2g-timescaledb pg_isready -U b2g -d b2g
   ```
   Expected: `b2g:5432 - accepting connections`

2. **Redis**:
   ```bash
   docker exec b2g-redis redis-cli ping
   ```
   Expected: `PONG`

3. **Mosquitto**:
   ```bash
   docker exec b2g-mosquitto timeout 2 sh -c "echo > /dev/tcp/127.0.0.1/1883" && echo "MQTT Ready"
   ```
   Expected: `MQTT Ready`

4. **Backend API**:
   ```bash
   curl http://localhost:8000/health
   ```
   Expected: `{"status":"healthy",...}`

   Or visit in browser: http://localhost:8000/health

### Access Points

| Service | URL | Purpose |
|---------|-----|---------|
| **Backend API** | http://localhost:8000 | FastAPI REST/WebSocket endpoints |
| **API Documentation** | http://localhost:8000/docs | Interactive Swagger UI |
| **Alternative API Docs** | http://localhost:8000/redoc | ReDoc documentation |
| **MQTT Broker** | `mqtt://localhost:1883` | MQTT protocol (use client) |
| **MQTT WebSocket** | `ws://localhost:9001` | MQTT over WebSocket |
| **PostgreSQL** | `postgresql://b2g:b2g_password@localhost:5432/b2g` | Direct DB access (dev only) |
| **Redis** | `redis://localhost:6379` | Direct cache access (dev only) |

### Stop the Stack

```bash
# Stop all services (keeps volumes)
docker compose down

# Stop and remove volumes (CAUTION: deletes all data)
docker compose down -v
```

### Update After Code Changes

```bash
# Rebuild backend only
docker compose build backend

# Restart backend with new image
docker compose up -d backend

# Or rebuild and restart everything
docker compose up -d --build
```

---

## Troubleshooting

### TimescaleDB Not Starting

**Symptoms**:
- Backend logs show: `connection refused` or `could not connect to server`
- `docker compose ps` shows timescaledb as `exited` or `restarting`

**Diagnosis**:
```bash
docker compose logs timescaledb
```

**Common Causes & Fixes**:

1. **Port 5432 already in use** (local PostgreSQL running)
   ```bash
   # Windows
   netstat -ano | findstr :5432
   
   # Stop local PostgreSQL or change docker-compose.yml port:
   ports:
     - "5433:5432"  # Use 5433 on host
   ```

2. **Volume corruption**
   ```bash
   # Stop stack and remove volumes
   docker compose down -v
   
   # Restart
   docker compose up -d
   ```

3. **Insufficient disk space**
   ```bash
   docker system df
   docker system prune  # Clean up unused images/volumes
   ```

### Mosquitto Connection Refused

**Symptoms**:
- Backend logs: `Connection refused` when connecting to MQTT
- MQTT clients cannot connect to `localhost:1883`

**Diagnosis**:
```bash
docker compose logs mosquitto
docker exec b2g-mosquitto cat /mosquitto/config/mosquitto.conf
```

**Common Causes & Fixes**:

1. **Configuration file missing or malformed**
   - Verify `docker/mosquitto/mosquitto.conf` exists
   - Check file has correct content:
     ```
     listener 1883
     allow_anonymous true
     listener 9001
     protocol websockets
     ```

2. **Port conflict**
   ```bash
   # Windows - check if port 1883 is in use
   netstat -ano | findstr :1883
   ```

3. **Permission issues** (Linux/macOS)
   ```bash
   chmod 644 docker/mosquitto/mosquitto.conf
   ```

### Backend Fails Health Check

**Symptoms**:
- `docker compose ps` shows backend as `unhealthy` (if health check added)
- Cannot access http://localhost:8000

**Diagnosis**:
```bash
docker compose logs backend
docker exec b2g-backend curl -f http://localhost:8000/health
```

**Common Causes & Fixes**:

1. **Backend crashed on startup**
   - Check logs for Python exceptions
   - Often caused by missing dependencies or database connection issues
   - Fix: Ensure timescaledb and redis are healthy first

2. **Port 8000 already in use**
   ```bash
   # Windows
   netstat -ano | findstr :8000
   ```

3. **Missing Python dependencies**
   ```bash
   # Rebuild backend
   docker compose build backend
   docker compose up -d backend
   ```

4. **Database not ready** (if health checks not added)
   - Wait 10-20 seconds after `docker compose up`
   - Check `docker compose logs timescaledb` for "database system is ready"

### Redis Connection Issues

**Symptoms**:
- Backend logs: `redis.exceptions.ConnectionError`
- Application still works (graceful degradation)

**Diagnosis**:
```bash
docker compose logs redis
docker exec b2g-redis redis-cli ping
```

**Common Causes & Fixes**:

1. **Redis not started**
   ```bash
   docker compose restart redis
   ```

2. **Network issues**
   ```bash
   # Verify backend can reach redis
   docker exec b2g-backend ping -c 3 redis
   ```

3. **Port conflict**
   ```bash
   netstat -ano | findstr :6379
   ```

### General Container Issues

**View resource usage**:
```bash
docker stats
```

**Restart a specific service**:
```bash
docker compose restart <service-name>
# Example: docker compose restart backend
```

**Rebuild from scratch**:
```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

**Check Docker daemon**:
```bash
docker info
docker version
```

---

## Files Analyzed

### Files Found and Read

1. ✅ `docker-compose.yml` - Main orchestration file (34 lines)
2. ✅ `Dockerfile` - Backend application image (23 lines)
3. ✅ `docker/mosquitto/mosquitto.conf` - MQTT broker configuration (4 lines)
4. ✅ `.github/workflows/ci.yml` - CI pipeline with correct health checks (50 lines)
5. ✅ `src/api/fastapi_app.py` - Verified `/health` endpoint exists (partial read)

### Files Expected but Missing

1. ❌ `.env` - Environment variables file (not found)
2. ❌ `.env.example` - Example environment template (not found)

### Additional Docker Files Searched

- No additional Dockerfiles found (searched for `Dockerfile.dev`, `Dockerfile.prod`, etc.)
- No additional docker-compose files found (searched for `docker-compose.prod.yml`, etc.)
- Only one file in `docker/` directory: `mosquitto/mosquitto.conf`

---

## Comparison: CI Workflow vs. Docker Compose

The GitHub Actions CI workflow (`.github/workflows/ci.yml`) demonstrates **better practices** than the current `docker-compose.yml`:

| Aspect | CI Workflow | Docker Compose | Gap |
|--------|-------------|----------------|-----|
| TimescaleDB health check | ✅ `pg_isready -U b2g -d b2g` | ❌ Missing | Critical |
| Redis health check | ✅ `redis-cli ping` | ❌ Missing | Critical |
| Service wait strategy | ✅ Waits for healthy services | ❌ Only waits for container start | Critical |
| Health intervals | ✅ 10s intervals, 5 retries | ❌ N/A | High |

**Recommendation**: Align `docker-compose.yml` with the proven CI configuration.

---

## Summary

The Docker Compose stack is **functionally complete but operationally fragile**. All required services are defined with correct networking and environment variables, but the lack of health checks and proper dependency conditions means:

- **First startup may fail** requiring manual restart
- **Service state is opaque** - no way to verify readiness
- **Less reliable than CI environment** despite being the same application

**Immediate Actions Required**:
1. Add health checks to all four services
2. Add `condition: service_healthy` to backend dependencies
3. Create `.env.example` for better developer onboarding
4. Consider moving credentials to `.env` file

**Current Workaround**:
Wait 10-15 seconds after `docker compose up -d` before accessing services, and check logs if backend crashes on first attempt (it should auto-restart successfully).

---

## Version Information

- **Docker Compose File Version**: 3.9
- **Base Images**:
  - Mosquitto: `eclipse-mosquitto:2`
  - TimescaleDB: `timescale/timescaledb:latest-pg16`
  - Redis: `redis:7-alpine`
  - Backend: Python 3.13-slim (custom build)
