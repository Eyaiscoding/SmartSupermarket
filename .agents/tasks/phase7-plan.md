# Phase 7 Production Hardening Implementation Plan

This plan hardens the B2G microservices platform for production deployment by adding resilience patterns (retry, circuit breaker, DLQ), operational visibility (health endpoints, structured logging), input validation (schema checks), and deployment infrastructure (healthchecks, documentation).

**Phase 7 Scope:** No Prometheus/Grafana/OpenTelemetry (Phase 6 was skipped per user instructions).

---

## Implementation Order

- [ ] 1. **Production-grade kafka_utils foundation**
      
      Add retry decorator with exponential backoff (configurable max_retries=3, base_delay=1.0s, max_delay=60s), CircuitBreaker class for Kafka connection failures (CLOSED/OPEN/HALF_OPEN states, failure_threshold=5, success_threshold=2, timeout=60s), DLQ support in MessageProcessor that routes failed messages to `{topic}.dlq` suffix, correlation ID generation and injection into all log records, and JSONFormatter for structured logging with fields (timestamp, level, logger_name, message, service_name, correlation_id).
      
      **Files:**
      - `kafka_utils/utils.py` — add retry_with_backoff decorator, CircuitBreaker class, DLQ logic to MessageProcessor.run(), get_correlation_id() function, JSONFormatter class, configure_json_logging(service_name) helper
      - `kafka_utils/test_kafka.py` — add tests for retry, circuit breaker, DLQ routing, correlation ID injection, JSON log formatting
      
      **Patterns from codebase:** MessageProcessor base class already exists with run() loop and process_message() hook. Extend run() to wrap process_message() calls with try/except for DLQ routing. Use Python standard library (time.sleep for backoff, uuid.uuid4 for correlation IDs, logging.Formatter for JSON output).
      
      **Verify:** `python -m pytest kafka_utils/test_kafka.py -v` — all new tests pass for retry, circuit breaker, DLQ, correlation ID, JSON logging.

- [ ] 2. **Health endpoints for all microservices**
      
      Create HealthServer class in kafka_utils/utils.py that runs http.server.HTTPServer in background thread. Expose /health (always 200 OK) and /ready (checks Kafka with check_kafka_health(), returns 200 if reachable, 503 if not). Add to all 4 services: forecasting (port 8081), mpc (port 8082), derms (port 8083), compliance (port 8084). Start HealthServer in main() before entering run() loop.
      
      **Files:**
      - `kafka_utils/utils.py` — add HealthServer class with start(), stop(), /health and /ready endpoints
      - `services/forecasting/main.py` — instantiate HealthServer(port=8081) in main(), stop in shutdown
      - `services/mpc/main.py` — instantiate HealthServer(port=8082)
      - `services/derms/main.py` — instantiate HealthServer(port=8083)
      - `services/compliance/main.py` — instantiate HealthServer(port=8084)
      
      **Verify:** `docker compose up --build -d && sleep 10 && curl http://localhost:8081/health && curl http://localhost:8082/health && curl http://localhost:8083/health && curl http://localhost:8084/health` — all return 200 OK. `curl http://localhost:8081/ready` returns 200 when Kafka healthy.

- [ ] 3. **Schema validation for all microservices**
      
      Add schema validation in each service's process_message() method. Check required fields exist and have correct types. Raise ValueError on invalid schema to trigger DLQ routing from step 1. Services validate: forecasting (telemetry: timestamp, total_consumption, pv_power, temperature), mpc (prediction: timestamp, forecast_consumption, forecast_pv, flexibility_budgets), derms (decision: timestamp, peak_shave, peak_shave_kw, load_shift_hvac, hvac_shed_kw, valley_fill, valley_fill_kw, hard_shed_tiers, hard_shed_kw, active_action_names), compliance (dispatch: timestamp, commands, battery_power, grid_power, battery_soc_after; telemetry: timestamp, building_id).
      
      **Files:**
      - `services/forecasting/main.py` — add _validate_telemetry_schema(data) helper, call at start of process_message()
      - `services/mpc/main.py` — add _validate_prediction_schema(data) helper
      - `services/derms/main.py` — add _validate_decision_schema(data) helper
      - `services/compliance/main.py` — add _validate_dispatch_schema(data) and _validate_telemetry_schema(data) helpers
      - `tests/test_forecasting.py` — add test_schema_validation_rejects_invalid_message()
      - `tests/test_mpc.py` — add test_schema_validation_rejects_invalid_message()
      - `tests/test_derms.py` — add test_schema_validation_rejects_invalid_message()
      - `tests/test_compliance.py` — add test_schema_validation_rejects_invalid_message()
      
      **Patterns:** Use dict.get() with required keys, check isinstance() for types, raise ValueError with descriptive message.
      
      **Verify:** `python -m pytest tests/test_forecasting.py::test_schema_validation_rejects_invalid_message -v` and same for mpc, derms, compliance — all tests pass.

- [ ] 4. **Structured JSON logging for all microservices**
      
      Replace basic logging.basicConfig() with configure_json_logging(service_name) from step 1 in all 4 services. Call at start of main() before any log statements. Verify logs are valid JSON with required fields (timestamp, level, message, service_name, correlation_id).
      
      **Files:**
      - `services/forecasting/main.py` — call configure_json_logging('forecasting') in main()
      - `services/mpc/main.py` — call configure_json_logging('mpc')
      - `services/derms/main.py` — call configure_json_logging('derms')
      - `services/compliance/main.py` — call configure_json_logging('compliance')
      
      **Verify:** `docker compose up --build -d && sleep 10 && docker compose logs forecasting --tail 20 | python -m json.tool` — output is valid JSON array with service_name='forecasting' and correlation_id fields.

- [ ] 5. **Log sanitization for secrets**
      
      Add log sanitization to all 4 services to redact passwords, tokens, and secrets. Scan log messages for patterns (password, token, key=, secret, bearer, authorization) and replace values with `***REDACTED***`. Implement as logging.Filter subclass that modifies LogRecord.msg before emission.
      
      **Files:**
      - `kafka_utils/utils.py` — add SanitizingFilter class (logging.Filter subclass) with regex patterns for secrets, add to configure_json_logging()
      - Test by temporarily logging a message with "password=secret123" and verifying it becomes "password=***REDACTED***"
      
      **Verify:** Manual test: add `logger.info("Connecting with password=abc123")` to forecasting/main.py, start service, check logs contain "password=***REDACTED***" not "password=abc123".

- [ ] 6. **Startup config validation**
      
      Add startup validation for required env vars in all 4 services. Fail fast with clear error message if missing. Log warnings for optional vars using defaults.
      
      **Files:**
      - `services/forecasting/main.py` — validate KAFKA_BOOTSTRAP_SERVERS (required), TRAINING_DATA_PATH (required), fail with sys.exit(1) and error message if missing
      - `services/mpc/main.py` — validate KAFKA_BOOTSTRAP_SERVERS (required), warn if MPC_HORIZON_HOURS/MPC_TIME_STEP_MINUTES use defaults
      - `services/derms/main.py` — validate KAFKA_BOOTSTRAP_SERVERS (required)
      - `services/compliance/main.py` — validate KAFKA_BOOTSTRAP_SERVERS (required)
      
      **Verify:** `KAFKA_BOOTSTRAP_SERVERS= docker compose up forecasting` — service exits immediately with error "Missing required env var: KAFKA_BOOTSTRAP_SERVERS".

- [ ] 7. **Update .env.example with all env vars**
      
      Document all required and optional environment variables with descriptions and defaults.
      
      **Files:**
      - `.env.example` — add sections: Kafka (KAFKA_BOOTSTRAP_SERVERS), MPC (MPC_HORIZON_HOURS, MPC_TIME_STEP_MINUTES), Forecasting (TRAINING_DATA_PATH), add comments explaining each variable
      
      **Verify:** `cat .env.example | grep KAFKA_BOOTSTRAP_SERVERS` — exists with comment.

- [ ] 8. **Docker Compose healthchecks**
      
      Add healthcheck stanzas to all 4 microservice containers using /health endpoints. Configure interval=30s, timeout=10s, retries=3, start_period=60s. Expose health check ports.
      
      **Files:**
      - `docker-compose.yml` — add healthcheck to forecasting service (curl http://localhost:8081/health), expose 8081:8081
      - `docker-compose.yml` — add healthcheck to mpc service (curl http://localhost:8082/health), expose 8082:8082
      - `docker-compose.yml` — add healthcheck to derms service (curl http://localhost:8083/health), expose 8083:8083
      - `docker-compose.yml` — add healthcheck to compliance service (curl http://localhost:8084/health), expose 8084:8084
      
      **Verify:** `docker compose up --build -d && sleep 90 && docker compose ps` — all services show status "healthy", no containers marked unhealthy.

- [ ] 9. **PRODUCTION_DEPLOYMENT.md documentation**
      
      Create comprehensive production deployment guide with checklist, env var reference, failure recovery, and scaling guidance.
      
      **Files:**
      - `PRODUCTION_DEPLOYMENT.md` — create with sections:
        1. Deployment Checklist — pre-flight (verify .env, run tests, build images, create Kafka topics, check disk), deployment (docker compose up -d, verify healthchecks, smoke test, tail logs), post-deployment (end-to-end scenario, check compliance reports)
        2. Environment Variable Reference — table of all vars from .env.example with descriptions, defaults, required/optional
        3. Failure Modes and Recovery — scenarios (Kafka down, TimescaleDB connection lost, service OOM, DLQ overflow), detection (logs, healthcheck failures, container restarts), recovery (restart service, clear DLQ, scale up)
        4. Scaling Notes — how to scale each service (Kafka partitions, consumer instances, container replicas), when to scale (CPU/memory thresholds, message lag), bottlenecks (Kafka throughput, TimescaleDB writes, Redis memory)
      - `README.md` — add link to PRODUCTION_DEPLOYMENT.md in Production Deployment section
      
      **Verify:** `cat PRODUCTION_DEPLOYMENT.md | grep -E 'Deployment Checklist|Environment Variable Reference|Failure Modes|Scaling Notes'` — all sections exist. `cat README.md | grep PRODUCTION_DEPLOYMENT.md` — link exists.

---

## Verification Strategy

Each step has inline verification. Final integration test:

```bash
# Start all services
docker compose up --build -d

# Wait for startup
sleep 90

# Check all services healthy
docker compose ps | grep -v "healthy" | wc -l  # Should output: 1 (header line only)

# Verify health endpoints
curl -f http://localhost:8081/health  # forecasting
curl -f http://localhost:8082/health  # mpc
curl -f http://localhost:8083/health  # derms
curl -f http://localhost:8084/health  # compliance

# Verify structured JSON logs
docker compose logs forecasting --tail 20 | python -m json.tool

# Run test suite
python -m pytest tests/ -v

# Verify deployment docs exist
ls -lh PRODUCTION_DEPLOYMENT.md

# Cleanup
docker compose down
```

---

## Dependencies Between Steps

- Steps 2-6 depend on step 1 (kafka_utils foundation)
- Steps 4-6 can run in parallel (structured logging, sanitization, config validation are independent)
- Step 8 depends on step 2 (health endpoints must exist)
- Step 9 depends on step 7 (references .env.example env vars)

---

## Technical Notes

- **No external dependencies added:** All features use Python standard library (threading, http.server, json, logging, time, uuid)
- **MessageProcessor base class:** All services inherit from it, so DLQ/retry/circuit breaker logic added to MessageProcessor.run() benefits all 4 services automatically
- **Health check ports:** 8081-8084 chosen to avoid conflicts with existing services (8000=FastAPI backend, 9092/9093=Kafka, 5432=TimescaleDB, 6379=Redis, 1883=Mosquitto)
- **DLQ topic naming:** Failed messages from `telemetry.raw` go to `telemetry.raw.dlq`, from `forecasting.predictions` go to `forecasting.predictions.dlq`, etc.
- **Correlation ID propagation:** Generated once per incoming message in MessageProcessor, stored in thread-local storage, injected into all log records via logging.Filter
- **Circuit breaker scope:** Applied to Kafka producer/consumer creation in create_producer() and create_consumer() functions, not to individual message processing (message failures use DLQ instead)
