# Three-branch merge: compliance layer, P2P datasets, and dashboard integration

Three feature branches were merged into main: `feature/compliance-layer5` (enhanced regulatory compliance with R1-R6 rules), `ajout-datasets` (neighbor building datasets for P2P trading), and `feature/dashboard` (React dashboard, P2P trading module, temperature monitoring). The merge consolidates 110 new files and 10,600+ lines of code across all six layers of the B2G simulation stack. The integration adds dynamic P2P energy trading, cold-chain temperature monitoring, real-time WebSocket streaming, and a production-ready dashboard, advancing the platform toward the target microservices architecture.

**Watch for:** Import linting regression stripped noqa comments from files that require sys.path injection (confirmed), potential runtime issues if migrations aren't applied in order (likely), and test suite blocked by pre-existing scipy/numpy Python 3.13 incompatibility unrelated to merge (confirmed).

**Verdict**: NEEDS_CHANGES

## High-level view

The sys.path injection pattern in `scenario_runner.py` and `src/api/fastapi_app.py` requires E402 suppression comments but they were stripped during merge resolution, causing 21 lint failures. The three branches merged cleanly with intelligent conflict resolution preserving all functionality. P2P trading is gated behind `B2G_P2P_ENABLED` and gracefully degrades when disabled, maintaining backward compatibility with the 36+ existing CSV-only tests. The P2P module implements a complete neighbor-matching pipeline with distance-based wheeling fees, production-type pricing factors, and trade summarization. Temperature monitoring implements stateful excursion tracking across 15-minute intervals with configurable limits and a critical-after-N-steps escalation policy. Database migrations are additive (nullable columns with `IF NOT EXISTS`), safe for repeated application, but 003, 004, 005 must run in order since the dashboard depends on P2P and temperature columns. The test suite collects 59 tests but cannot execute due to a pre-existing scipy ufunc incompatibility with Python 3.13, unrelated to the merge.

<details>
<summary>Issues (4)</summary>

1. **E402 lint regression** — 21 `noqa: E402` comments were stripped from `scenario_runner.py` (9 occurrences) and `src/api/fastapi_app.py` (12 occurrences) during merge conflict resolution. These files intentionally inject the project root into `sys.path` before importing `src.*` modules. Restore the `# noqa: E402` suffix on all imports following `sys.path.insert()` in both files.

2. **Migration ordering dependency** — Migration 005 (dashboard columns) depends on columns created by 003 (P2P) and 004 (temperature), but there's no enforcement mechanism. If migrations run out of order or 003/004 are skipped, queries will fail. Add a comment header to 005_dashboard.sql stating "Requires 003_p2p.sql and 004_temperature.sql" and document the required sequence in a migrations README.

3. **Test suite blocked** — The environment has a scipy/numpy Python 3.13 incompatibility (`ValueError: All ufuncs must have type numpy.ufunc`) preventing test execution. This is pre-existing and unrelated to the merge, but it blocks verification that the 59 collected tests (including 2 new P2P test files with 418 lines and 1 temperature test file with 239 lines) actually pass. Downgrade to Python 3.11 or update scipy before the next CI run.

4. **Verification doc inaccuracy** — `.agents/tasks/verification.md` claims "Ran `ruff check ... --ignore E501,E402 --fix` ... Result: All checks passed (0 errors)" but actually running `ruff check src/ tests/ scenario_runner.py --select E,F,W --ignore E501` (without ignoring E402, per the original task requirement) shows 21 E402 errors. The verification step appears to have silenced E402 rather than fixing it, contradicting the requirement to fix ~80 pre-existing errors.

</details>

<details>
<summary>Details</summary>

## Import linting regression: noqa comments stripped

The original codebase (commit 22d437b "fix: resolve all 80 linting errors") added `# noqa: E402` comments to `scenario_runner.py` and `src/api/fastapi_app.py` because both files intentionally manipulate `sys.path` before importing project modules. This is a necessary pattern: the scripts need to run standalone without requiring `pip install -e .`.

During the three-way merge, these noqa comments were stripped. Both files now have the same sys.path injection pattern but no suppression:

```python
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion import load_dataset          # missing: # noqa: E402
from src.forecasting import Forecaster, ...     # missing: # noqa: E402
```

This causes 21 E402 errors:
- `scenario_runner.py`: 9 imports flagged
- `src/api/fastapi_app.py`: 12 imports flagged

The verification doc claims 0 errors, but that's because the post-merge lint check ran with `--ignore E501,E402`. The original task requirement (from commit 22d437b and the user's opening message) was to fix all linting errors with `--ignore E501` only. E402 errors were meant to be suppressed via noqa comments, not globally ignored.

Restoring the noqa comments brings the code back to the state of origin/main and satisfies the original linting fix.

## Three-branch merge strategy and conflict resolution

The three branches were merged sequentially: compliance-layer5 first (2 commits), then ajout-datasets (1 commit, no conflicts), then feature/dashboard (2 commits). Conflicts were resolved by accepting the most complete implementation:

- `src/compliance/`: accepted compliance branch's R1-R6 enhanced audit rules
- `src/api/fastapi_app.py`: accepted all imports from both compliance and dashboard branches
- `scenario_runner.py`: accepted compliance branch's import list plus dashboard branch's P2P/temperature integrations
- `data1/`: dashboard branch contained the same neighbor CSV files as ajout-datasets

## P2P trading module architecture and backward compatibility

The P2P module (`src/p2p/`, 7 files) implements a complete neighbor-matching pipeline:

1. **Loader** (`loader.py`, 126 lines): Loads neighbor building CSV with schema validation (timestamp alignment, distance/offer/consumption non-negative, no missing values). Caps incoherent offers (offer > production) with a warning. Returns a `NeighborBook` indexed by ISO timestamp.

2. **Matching** (`matching.py`, 120 lines): Matches supermarket surplus/deficit against neighbor offers/demands. Returns a list of `Trade` objects (building_id, amount_kw, direction).

3. **Pricing** (`pricing.py`, 15 lines): Computes wheeling fees (base + distance * per_km) and adjusts sell price by production type.

4. **Pipeline** (`pipeline.py`, 28 lines): `NeighborMarket` class orchestrates the loader → matcher → pricing flow for a single timestep.

5. **Config** (`config.py`, 70 lines): `MarketConfig` dataclass with validation (finite values, non-negative fees, positive step_hours). Reads from env vars with defaults. `enabled()` checks `B2G_P2P_ENABLED`.

6. **Models** (`models.py`, 59 lines): `NeighborStep` and `Trade` dataclasses.

The module is gated behind `B2G_P2P_ENABLED=true`. When disabled (default), the ingestion layer loads the original 11,712-row CSV, and P2P fields remain null. This preserves backward compatibility: all 36+ existing tests run in CSV-only mode without neighbor datasets.

The loader performs strict validation: timestamps must align exactly with the supermarket dataset (15-minute intervals), all buildings must share the same timestamp sequence, distance/offer/consumption must be non-negative and finite. The test suite covers unicode BOM handling, column case normalization, missing values, negative values, duplicate rows, timestamp misalignment, and metadata inconsistencies.

## Temperature monitoring: stateful excursion tracking

`src/monitoring/temperature.py` (136 lines) implements a stateful monitor tracking cold-chain sensor readings across four zones: display_freezer, freezer_room, display_refrigerator, cold_room. Each sensor has three thresholds: low, high, hard_limit. The monitor categorizes readings as OK, WARNING (exceeds high or falls below low), or CRITICAL (exceeds hard_limit or WARNING persists for `critical_after_steps` intervals).

The monitor maintains excursion state in `_excursions: dict[str, tuple[int, str]]` mapping sensor name to (step_count, status). When a sensor enters WARNING, the counter increments each step; when it exceeds `critical_after_steps`, status escalates to CRITICAL. Returning to OK resets the counter.

The `observe()` method validates 15-minute interval spacing, handles missing sensors gracefully (skips them), and returns `temperatures` (current readings), `alerts` (list of {sensor, value, status, duration_steps}), and `status` (CRITICAL if any sensor is critical, else WARNING if any sensor is warning, else OK).

The monitor is instantiated from env vars via `from_env()`, with defaults explicitly marked as simulation placeholders, not validated food-safety thresholds. Test coverage (`tests/test_temperature.py`, 239 lines) includes state transitions, excursion escalation, missing sensor handling, non-15-minute intervals, and hard limit behavior.

## Database migrations: additive schema evolution

Three migrations were added:

- **003_p2p.sql** (10 lines): Adds 9 nullable columns for P2P trading (p2p_import, p2p_export, p2p_trades, p2p_savings, cost, revenue, energy_price, sell_price, p2p_price).
- **004_temperature.sql** (4 lines): Adds 3 nullable columns for temperature monitoring (temperatures, temperature_alerts, temperature_status).
- **005_dashboard.sql** (4 lines): Adds 4 nullable columns for dashboard presentation (neighbors, demand_kw, pv_power, temperature_limits).

All three use `ADD COLUMN IF NOT EXISTS`, making them safe for repeated application. All columns are nullable, preserving existing rows.

However, 005_dashboard.sql implicitly depends on columns created by 003 and 004. If migrations run out of order or if 003/004 are skipped, queries will fail with "column does not exist". There's no enforcement mechanism (no foreign key, no version table, no migration runner tracking dependencies). The .sql files don't document this dependency.

## Dashboard: 37-file React app with WebSocket streaming

The dashboard (`dashboard/`, 37 files, 8,000+ lines) is a Vite + React + TypeScript application with:

- **API client** (`src/api/`, 4 files): HTTP and WebSocket adapters for `/latest`, `/history`, `/neighbors`, `/scenario`, and WebSocket `/ws/scenario`. Mock implementation for offline dev.
- **Hooks** (`src/hooks/`, 2 files): `useDashboard` (fetches latest/history/neighbors), `useStream` (WebSocket connection with auto-reconnect).
- **Components** (`src/components/`, 6 files): StatusCards (grid/BESS/P2P status), Charts (Recharts line/bar/area), Finance (cost/revenue/savings), Operations (demand/PV/BESS), NeonGauge (radial compliance gauge).
- **Styling** (`src/styles.css`, `src/styles/theme.css`, 1,423 lines): Tailwind-based dark theme with neon accents, glassmorphism cards, grid/flexbox layouts.

The dashboard depends on new API endpoints: `GET /neighbors` (neighbor list), `GET /neighbors/summary` (aggregated supply), `POST /scenario` (triggers runner with WebSocket streaming), and `WebSocket /ws/scenario` (streams per-timestep output as NDJSON). The WebSocket endpoint runs the six-layer pipeline in an async task, emitting one OutputRecord per timestep.

Test suite: `dashboard/src/**/*.test.ts` (4 files) and a smoke test runner (`dashboard/scripts/browser-smoke.mjs`, 230 lines) that launches Vite + Playwright and verifies HTTP/WebSocket flows.

## Test coverage and environment blocker

The merge adds two new test files:
- `tests/test_p2p.py` (418 lines): 13+ test cases covering loader validation, unicode/BOM handling, negative/missing/duplicate data rejection, timestamp alignment, offer capping, matching logic, and API endpoints.
- `tests/test_temperature.py` (239 lines): 12+ test cases covering state transitions, excursion escalation, missing sensors, hard limits, and 15-minute interval validation.

The test suite now collects 59 tests (up from ~47), but pytest cannot execute any of them due to a pre-existing scipy/numpy incompatibility with Python 3.13:

```
ValueError: All ufuncs must have type `numpy.ufunc`. 
Received (<ufunc 'sph_legendre_p'>, <ufunc 'sph_legendre_p'>, <ufunc 'sph_legendre_p'>)
```

This error surfaces during sklearn import in the forecasting layer (pre-existing, not added by any branch). Python 3.13 changed the ufunc API and scipy hasn't caught up. Without test execution, there's no empirical verification that the P2P module, temperature monitor, and dashboard API integrations work end-to-end.

## Documentation gaps

The `README.md` still treats the dashboard as "built by other team members" when it's now part of this repository.

The verification doc (`verification.md`) incorrectly claims the lint check passed with 0 errors when it actually ran with `--ignore E402`, masking 21 errors that the original task required to be fixed (not ignored).

</details>

<details>
<summary>File map</summary>

### P2P module (7 files)
- `src/p2p/__init__.py` — module marker
- `src/p2p/config.py` — MarketConfig dataclass, env var loading, feature toggle
- `src/p2p/loader.py` — CSV loader with schema validation and timestamp alignment
- `src/p2p/matching.py` — neighbor-matching algorithm and trade summarization
- `src/p2p/models.py` — NeighborStep and Trade dataclasses
- `src/p2p/pipeline.py` — NeighborMarket orchestrator
- `src/p2p/pricing.py` — wheeling fee and production-type pricing

### Temperature monitoring (1 file)
- `src/monitoring/temperature.py` — stateful excursion tracker with configurable thresholds

### Database migrations (3 files)
- `src/persistence/migrations/003_p2p.sql` — P2P trading columns (9 fields)
- `src/persistence/migrations/004_temperature.sql` — temperature monitoring columns (3 fields)
- `src/persistence/migrations/005_dashboard.sql` — dashboard presentation columns (4 fields)

### Dashboard (37 files in `dashboard/`)
- `package.json`, `vite.config.ts`, `tsconfig.json` — build config
- `src/App.tsx` — main application
- `src/api/` — HTTP/WebSocket client and mock
- `src/components/` — StatusCards, Charts, Finance, Operations, NeonGauge
- `src/hooks/` — useDashboard, useStream
- `src/styles.css`, `src/styles/theme.css` — Tailwind + neon theme

### Tests (2 files)
- `tests/test_p2p.py` — P2P module unit and integration tests (418 lines)
- `tests/test_temperature.py` — temperature monitor state machine tests (239 lines)

### Datasets (2 files in `data1/`)
- `dataset_modifié.csv` — modified supermarket dataset (11,713 rows)
- `smart_supermarket_neighbor_buildings_4months_15min1.csv` — neighbor buildings (70,273 rows)

### Modified core files (15 files)
- `scenario_runner.py` — integrated P2P and temperature monitoring
- `src/api/fastapi_app.py` — added P2P and temperature endpoints, WebSocket streaming
- `src/api/models.py` — added NeighborModel, TemperatureAlertHistoryModel
- `src/api/output.py` — added p2p and temperature field serialization
- `src/compliance/checker.py` — R1-R6 enhanced audit rules
- `src/compliance/__init__.py` — exports cold_chain_temps, tier_1_demand_kw
- `src/ingestion/loader.py` — loads supermarket or neighbor CSV based on B2G_P2P_ENABLED
- `src/ingestion/schema.py` — schema validation for CSV columns
- `src/persistence/timescale.py` — added p2p and temperature column writes
- `src/persistence/redis_cache.py` — minor import cleanup
- `.github/workflows/ci.yml` — pg_isready health check fix
- `requirements.txt` — added pytest-asyncio
- `README.md` — documented P2P trading and temperature monitoring
- `docs/DATASET.md` — moved from README, documented neighbor CSV schema
- `docs/PHASE3_DATA_AUDIT.md` — neighbor dataset audit trail

[Full diff: `git diff 22d437b..HEAD`]

</details>
