# Implementation Plan: Extract MPC Service as Independent Microservice

## Context

This plan extracts the MPC (Model Predictive Control) Service as an independent microservice following the exact pattern established by the already-extracted Forecasting Service. The MPC service will consume forecasting predictions from Kafka, run the receding-horizon controller logic, and publish MPC decisions back to Kafka for the DERMS service to consume.

**Pattern to follow:** `services/forecasting/` (Dockerfile, requirements.txt, main.py structure, README.md, test_service.py)

**Core logic:** Reuse existing `MPCCoordinator` from `src/mpc/coordinator.py` (no CVXPY dependency exists—verified via grep)

**Architecture:** Stateless service extending `MessageProcessor` from `kafka_utils/utils.py`

---

## Plan

- [ ] 1. Create MPC service directory structure and requirements file.
      Create `services/mpc/` directory and `services/mpc/requirements.txt` listing: pandas>=2.0, numpy>=1.24, kafka-python>=2.0.2, lz4>=4.3.2 (no cvxpy—coordinator.py uses only numpy).
      Files: services/mpc/requirements.txt
      Verify: File exists and lists the 4 dependencies.

- [ ] 2. Create MPC service Dockerfile following the forecasting service pattern.
      Copy and adapt `services/forecasting/Dockerfile` to create `services/mpc/Dockerfile`. Use `FROM python:3.13-slim`, install `gcc libpq-dev` system dependencies, copy requirements.txt and install, copy entire project for access to `src/` modules, set `ENV PYTHONPATH=/app`, and set `CMD ["python", "services/mpc/main.py"]`.
      Files: services/mpc/Dockerfile
      Verify: File exists and follows the same structure as services/forecasting/Dockerfile.

- [ ] 3. Implement MPCService class in services/mpc/main.py.
      Create `services/mpc/main.py` extending `MessageProcessor` from `kafka_utils.utils`. Initialize with `input_topics=['forecasting.predictions']`, `output_topic='mpc.decisions'`, `group_id='mpc-service'`. In `__init__`, instantiate `MPCCoordinator` from `src.mpc.coordinator` with default parameters. Implement `process_message(message)` to: (1) extract prediction data (timestamp, forecast_consumption, forecast_pv, anomaly_flag, flexibility_budgets), (2) call `coordinator.decide()` with current timestep values + forecasts (use empty lists for forecast_prices if not available, and replicate current forecast values for look-ahead horizon), (3) convert `MPCAction` result into JSON-serializable dict with fields: timestamp, peak_shave, peak_shave_kw, load_shift_hvac, hvac_shed_kw, valley_fill, valley_fill_kw, hard_shed_tiers (list), hard_shed_kw, active_action_names (list), total_battery_request_kw, (4) return the dict for publishing. Include signal handlers (SIGTERM, SIGINT) for graceful shutdown. Add `main()` function reading config from env vars (`KAFKA_BOOTSTRAP_SERVERS` default `localhost:9093`).
      Files: services/mpc/main.py
      Verify: Run `python -m py_compile services/mpc/main.py` to check syntax is valid.

- [ ] 4. Create MPC service README.md documentation.
      Create `services/mpc/README.md` following the same structure as `services/forecasting/README.md`. Document: overview (Phase 3, MPC service extraction), architecture diagram (forecasting.predictions → MPC Service → mpc.decisions), files list, running instructions (Docker Compose and local dev), input schema (forecasting.predictions topic), output schema (mpc.decisions topic), configuration env vars (KAFKA_BOOTSTRAP_SERVERS), MPC controller details (horizon=4, actions: peak shaving, load shifting, valley filling, hard shedding), troubleshooting section.
      Files: services/mpc/README.md
      Verify: File exists and follows the forecasting README structure with MPC-specific content.

- [ ] 5. Create MPC service integration test.
      Create `services/mpc/test_service.py` following `services/forecasting/test_service.py` pattern. Test flow: (1) publish test prediction event to `forecasting.predictions` topic with all required fields (timestamp, forecast_consumption, forecast_pv, anomaly_score, anomaly_flag, anomaly_source, flexibility_budgets dict), (2) wait 3 seconds for processing, (3) consume from `mpc.decisions` topic, (4) validate output has required fields (timestamp, peak_shave, load_shift_hvac, valley_fill, hard_shed_tiers, active_action_names, total_battery_request_kw), (5) validate timestamp matches, (6) validate data types (booleans for action flags, floats for kW values, list for tiers/actions). Use `kafka_utils.utils.create_producer` and `create_consumer` helpers with bootstrap_servers='localhost:9093'.
      Files: services/mpc/test_service.py
      Verify: Run `python -m py_compile services/mpc/test_service.py` to check syntax is valid.

- [ ] 6. Update docker-compose.yml to add the MPC service.
      Add new service definition `mpc:` to `docker-compose.yml` following the `forecasting:` service pattern. Use `build: { context: ., dockerfile: services/mpc/Dockerfile }`, `container_name: b2g-mpc`, set environment `KAFKA_BOOTSTRAP_SERVERS: kafka:9092` and `PYTHONUNBUFFERED: "1"`, add `depends_on: kafka: { condition: service_healthy }`, set `restart: unless-stopped`. Place it immediately after the forecasting service definition.
      Files: docker-compose.yml
      Verify: Run `docker compose config` to validate YAML syntax and structure.

- [ ] 7. Build and start the MPC service container to verify end-to-end integration.
      Build the MPC service Docker image and start the service: `docker compose up --build -d mpc`. Check logs to confirm: Kafka connection established, subscribed to forecasting.predictions topic, message processing loop started. Verify service is running: `docker compose ps mpc` shows healthy status.
      Files: (none—verification step)
      Verify: `docker compose logs mpc` shows "Starting message processing loop" and "Subscribed to: forecasting.predictions" without errors.

- [ ] 8. Run the MPC service integration test to validate message flow.
      With the full Docker stack running (kafka, forecasting, mpc), execute the integration test: `python services/mpc/test_service.py`. Confirm test publishes a prediction to forecasting.predictions, MPC service consumes it, processes it via MPCCoordinator, and publishes decision to mpc.decisions topic. Test should print "🎉 MPC Service Test PASSED" and exit with code 0.
      Files: (none—verification step)
      Verify: `python services/mpc/test_service.py` exits with code 0 and prints PASSED confirmation.

---

## Dependencies

- **Step 1-2** can run in parallel (requirements.txt and Dockerfile are independent).
- **Step 3** depends on Step 1 (needs requirements.txt to know dependencies).
- **Step 4-5** can run in parallel with each other, both depend on Step 3 (need main.py to document/test).
- **Step 6** depends on Step 2 (references Dockerfile path).
- **Step 7** depends on Steps 2, 3, 6 (needs Dockerfile, main.py, docker-compose.yml).
- **Step 8** depends on Steps 5, 7 (needs test file and running service).

---

## Notes

- **No cvxpy dependency**: Confirmed via `grep -r 'import cvxpy\|from cvxpy' **/*.py` returning no matches. The existing `MPCCoordinator` in `src/mpc/coordinator.py` uses only numpy for forecasting calculations.
- **Backward compatibility**: This extraction does NOT modify the v2 monolithic backend or any existing services. The MPC service operates independently alongside the monolith.
- **Stateless design**: MPCCoordinator has no internal state that persists across messages—each `decide()` call is independent, making the service fully stateless and horizontally scalable.
- **MessageProcessor pattern**: Reuses the proven `kafka_utils.utils.MessageProcessor` base class that handles Kafka consumer loop, error handling, graceful shutdown, and producer flushing.
- **Test command**: Per README.md, the project uses `pytest tests/` for unit tests. The integration test `test_service.py` is a standalone script (not a pytest fixture) following the forecasting service pattern.
- **Build command**: Docker Compose is the primary build/run mechanism for services: `docker compose up --build`.
- **Verification approach**: Each step specifies concrete commands (py_compile, docker compose config, docker compose logs) rather than grep checks, ensuring actual functional validation.

---

## Success Criteria

After completing all steps:

1. ✅ MPC service runs in Docker container without errors
2. ✅ Service subscribes to `forecasting.predictions` Kafka topic
3. ✅ Service publishes to `mpc.decisions` Kafka topic
4. ✅ Integration test passes end-to-end (publish prediction → receive decision)
5. ✅ All Docker health checks pass: `docker compose ps` shows all services healthy
6. ✅ No modifications to existing backend or forecasting service code

---

*Implementation Pattern:* Follow `services/forecasting/` exactly  
*Core Logic:* Reuse `src/mpc/coordinator.MPCCoordinator`  
*Base Class:* Extend `kafka_utils.utils.MessageProcessor`  
*Phase:* 3 of 7 (Microservices extraction)
