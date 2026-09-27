# Coding agent prompt — Smart Supermarket B2G backend, v1 → v2 (production upgrade)

## Context — what already exists (v1, done)

The repo already contains a working, tested B2G simulation backend:
- Six-layer pipeline: ingestion → AI forecasting/flexibility → MPC coordination core → DERMS dispatch → reliability/compliance → JSON/CSV output.
- `dataset.csv` (11,712 rows, 30 columns, 15-min resolution, 4 months) committed under `data/`.
- 36 passing pytest tests across all six layers.
- `scenario_runner.py` replays the full dataset plus three injected stress scenarios (grid outage, price spike, sensor corruption) — Tier 1 (critical refrigeration loads) was never breached in any of them.
- A reference architecture diagram, `b2g_microservices_architecture.png`, already committed to the repo. It depicts the **target production architecture**: MQTT edge ingestion → Kafka event streaming backbone → four independent microservices (forecasting, MPC, DERMS, compliance) → TimescaleDB + Redis → FastAPI API gateway → dashboard client.
- A git repository, already initialized, committed, and pushed to GitHub.

**Do not break any of this.** All 36 existing tests must still pass after this upgrade, and `scenario_runner.py` must still work end-to-end on the plain CSV path (see the dual-mode note below).

## Goal — version 2

We are **not** building the full Kafka/microservices split yet — that stays documented as the future target architecture (the PNG already committed covers this; keep it referenced in the README, do not delete it).

Version 2 is the pragmatic, honest middle ground: turn the existing six-layer pipeline into a single **modular FastAPI service** with real infrastructure around it — MQTT for realistic telemetry ingestion, TimescaleDB for durable time-series persistence, Redis for low-latency current-state reads, everything containerized, with CI running the test suite on every push. This gets full production-engineering credit (real API, real DB, real cache, real CI/CD, real message broker) without betting the demo on a distributed system none of us have operated before.

## Implementation steps

1. **Refactor into clean internal service boundaries** (if not already this clean): keep the six existing modules (`ingestion`, `forecasting`, `mpc`, `derms`, `compliance`, `api`) as clearly separated Python packages inside one app — these are exactly the seams a future Kafka split would cut along, so keep them honest and decoupled (no module reaching into another's internals).

2. **Wrap the pipeline in FastAPI**:
   - REST endpoints: historical query by time range, latest state, scenario replay trigger.
   - A WebSocket endpoint streaming per-timestep output live as the pipeline runs.
   - Pydantic models enforcing the existing output contract (`coverage_ratio`, `coverage_status`, `active_actions`, `tier_1_protected`, `battery_soc`, `grid_power`, `p2p_energy`, `anomaly_flag`, `anomaly_source`) — use these as both the internal dataclass and the API response model, don't duplicate the schema.

3. **Add MQTT as a dual-mode ingestion path**:
   - Add a small publisher script that replays `dataset.csv` row by row onto an MQTT topic (e.g. `supermarket/telemetry`), at a configurable interval, against a local Mosquitto broker.
   - Extend the ingestion layer to support two modes via config: `csv` (reads the file directly — this is what the existing 36 tests and `scenario_runner.py` should keep using, so they stay fast and deterministic) and `mqtt` (subscribes to the topic — this is the "live/demo" mode). Don't make MQTT mandatory for tests to pass.

4. **Add TimescaleDB** (PostgreSQL + the Timescale extension):
   - One hypertable for per-timestep output records.
   - The compliance layer (or a small dedicated persistence module) writes every processed timestep here, in addition to the existing JSON/CSV output.
   - Add at least one test proving a full scenario run can be queried back out of the DB and the Tier 1 invariant still holds when read from storage, not just in memory.

5. **Add Redis**:
   - Cache only the *current* state (latest coverage status, latest battery SOC, latest active actions) — this is what the API's "latest state" REST endpoint and the WebSocket should read from for low latency, while historical queries go to TimescaleDB.

6. **Dockerize everything**:
   - `docker-compose.yml` with services: `mosquitto`, `timescaledb`, `redis`, and the FastAPI `backend` app.
   - One `docker compose up` should bring up the full stack, run migrations/schema setup, and serve the API.
   - Keep a `Dockerfile` for the backend that's usable standalone too.

7. **Add GitHub Actions CI**:
   - Workflow that runs on every push/PR: install deps, run all pytest tests (the original 36 plus whatever you add for DB/MQTT), run a linter (ruff), and build the Docker image to confirm it isn't broken.

8. **Update the README** with a new structure:
   - Keep the existing v1 content (architecture, dataset, papers, tools, setup).
   - Add a **"Version 2 — Production Upgrade"** section: what changed, why (real API instead of flat files, real persistence instead of CSV dumps, real message broker instead of direct file reads), and the dual-mode ingestion design decision (CSV for tests/determinism, MQTT for live demo).
   - Add a **"Target Architecture (Future Work)"** section that embeds/references `b2g_microservices_architecture.png` and explains, in a few sentences, why the full Kafka/multi-service split is documented as the intended production target but deliberately not implemented for this project's scope (operational risk vs. remaining time, no team member has run Kafka before) — be explicit and honest about this being a scoping decision, not a technical limitation.
   - Update the "Tools/tech stack used" list to add: FastAPI, Pydantic, MQTT/Mosquitto, TimescaleDB, Redis, Docker/docker-compose, GitHub Actions.

9. **Git — incremental, meaningful commits, then push**:
   - Commit in small logical chunks as you go, not one giant commit at the end, e.g.:
     - `feat: wrap pipeline in FastAPI with REST + WebSocket`
     - `feat: add dual-mode ingestion (csv/mqtt) with Mosquitto publisher`
     - `feat: add TimescaleDB persistence layer`
     - `feat: add Redis current-state cache`
     - `feat: dockerize backend, mosquitto, timescaledb, redis`
     - `ci: add GitHub Actions test/lint/build workflow`
     - `docs: document v2 upgrade and future microservices target architecture`
   - The remote should already be configured from v1 (check with `git remote -v`). If it is, just `git push` after each meaningful commit (or at the end, your call). If for some reason no remote is configured, stop and give me the exact commands rather than guessing at credentials.

## What NOT to do

- Don't implement Kafka or split into separate microservice processes/repos — that stays a documented future target only, represented by the existing PNG and the new README section.
- Don't remove or weaken the dual-mode ingestion — tests must keep working off the plain CSV without needing Mosquitto/Docker running.
- Don't let the Tier 1 protection invariant regress — it must still hold in every existing test, every stress scenario, and the new DB round-trip test.
- Don't over-engineer the Redis layer into a second source of truth — TimescaleDB is the durable record, Redis is a disposable cache of the latest state only.
