# Implementation Plan: Merge Three Branches and Consolidate B2G Platform

## Current State Summary

**Repository state:**
- `main` branch is at commit `22d437b` ("fix: resolve all 80 linting errors and update CI/CD health check"), 1 commit ahead of `origin/main`
- Three remote branches exist:
  - `origin/feature/compliance-layer5`: 2 commits ahead (enhanced compliance R1-R6, pytest-asyncio addition)
  - `origin/ajout-datasets`: 1 commit ahead (adds `data1/` with 2 CSV files)
  - `origin/feature/dashboard`: 3 commits ahead (major addition: React dashboard + P2P trading module + monitoring + migrations)
- CI/CD health check already fixed in local main (uses `pg_isready -U b2g -d b2g`)
- `pytest-asyncio>=0.23` already in requirements.txt
- No `src/p2p/`, `dashboard/`, or P2P migrations exist yet on main

**Expected conflicts:**
1. `requirements.txt`: compliance branch reorders pytest-asyncio/httpx (trivial)
2. `src/compliance/`: linting fixes (main) vs enhanced compliance layer (compliance branch)
3. `data1/`: both ajout-datasets and dashboard add this directory (dashboard's version is complete)
4. `src/api/fastapi_app.py`: dashboard branch removes P2P/temperature integration code that was never on main (clean merge expected)

---

## Implementation Steps

### Phase 1: Push Local Main

- [ ] 1. Push the local linting-fix commit (22d437b) to origin/main.
      
      This synchronizes the linting fixes and CI health check update with the remote before merging other branches.
      
      Files: none (git operation)
      
      Command: `git push origin main`
      
      Verify: `git log origin/main --oneline -1` shows commit 22d437b

### Phase 2: Merge Branches in Order

- [ ] 2. Merge `origin/feature/compliance-layer5` into main.
      
      This brings in the enhanced compliance layer (R1-R6 rules, `ComplianceReport`, `ComplianceStatus`, regulatory references) and the pytest-asyncio addition (already present, so expect trivial conflict).
      
      Expected conflicts:
      - `requirements.txt`: line order difference (pytest-asyncio vs httpx) — keep main's order since pytest-asyncio is already pinned
      - `src/compliance/__init__.py`: linting fix (main removed imports) vs enhanced exports (compliance branch) — preserve compliance branch's full export list
      - `src/compliance/checker.py`: linting fixes vs R1-R6 audit logic — preserve compliance branch's enhanced implementation, which includes the linting fixes
      
      Resolution strategy: accept compliance branch's compliance module entirely (it's the enhanced version), keep main's requirements.txt order.
      
      Files: `requirements.txt`, `src/compliance/__init__.py`, `src/compliance/checker.py`, `tests/compliance/test_checker.py`
      
      Command: `git merge --no-ff origin/feature/compliance-layer5`
      
      Verify: `git log --oneline -1` shows merge commit; `ruff check src/compliance/ --select E,F,W --ignore E501` passes

- [ ] 3. Merge `origin/ajout-datasets` into main.
      
      This adds `data1/dataset_modifié.csv` and `data1/smart_supermarket_neighbor_buildings_4months_15min1.csv` for P2P trading neighbor data.
      
      Expected conflicts: none (new directory)
      
      Note: The dashboard branch also adds `data1/` with the same files. The next merge will overwrite this if needed.
      
      Files: `data1/dataset_modifié.csv`, `data1/smart_supermarket_neighbor_buildings_4months_15min1.csv`
      
      Command: `git merge --no-ff origin/ajout-datasets`
      
      Verify: `git log --oneline -1` shows merge commit; `ls data1/` lists 2 CSV files

- [ ] 4. Merge `origin/feature/dashboard` into main.
      
      This is the major merge: adds React/TypeScript dashboard (37 files in `dashboard/`), P2P trading module (`src/p2p/` with 7 files), temperature monitoring (`src/monitoring/temperature.py`), ingestion schema updates (`src/ingestion/schema.py`), three DB migrations (`003_p2p.sql`, `004_temperature.sql`, `005_dashboard.sql`), new tests (`tests/p2p/test_p2p.py`, `tests/monitoring/test_temperature.py`), API updates (`src/api/fastapi_app.py`, `src/api/models.py`), and WebSocket scenario support.
      
      Expected conflicts:
      - `data1/`: both branches add this directory — dashboard's version is the authoritative one; if git reports conflict, accept dashboard's version
      - `src/api/fastapi_app.py`: dashboard branch modifies imports and removes P2P/temperature integration code from `_run_pipeline_sync` that was never on main — should merge cleanly, but if conflict, preserve dashboard's version (it's the complete implementation)
      
      Resolution strategy: accept dashboard's `data1/` if conflict occurs; preserve all dashboard additions to API.
      
      Files: 
      - New: `dashboard/` (37 files), `src/p2p/` (7 files), `src/monitoring/temperature.py`, `src/persistence/migrations/003_p2p.sql`, `src/persistence/migrations/004_temperature.sql`, `src/persistence/migrations/005_dashboard.sql`, `tests/p2p/test_p2p.py`, `tests/monitoring/test_temperature.py`
      - Modified: `src/api/fastapi_app.py`, `src/api/models.py`, `src/ingestion/schema.py`, `data1/` (overwrite from ajout-datasets)
      
      Command: `git merge --no-ff origin/feature/dashboard`
      
      Verify: 
      - `git log --oneline -1` shows merge commit
      - `Test-Path dashboard/` returns True
      - `Test-Path src/p2p/` returns True
      - `Test-Path src/persistence/migrations/003_p2p.sql` returns True
      - `Test-Path src/persistence/migrations/004_temperature.sql` returns True
      - `Test-Path src/persistence/migrations/005_dashboard.sql` returns True
      - `ls src/p2p/` lists 7 files: `__init__.py`, `config.py`, `loader.py`, `matching.py`, `models.py`, `pipeline.py`, `pricing.py`

### Phase 3: Post-Merge Consolidation

- [ ] 5. Run Ruff auto-fix on all merged code and commit any fixes.
      
      After all three merges, run the linting check/fix to catch any new issues introduced by the merges or conflicts.
      
      Files: potentially any Python file in `src/`, `tests/`, `scenario_runner.py`
      
      Command: `ruff check src/ tests/ scenario_runner.py --select E,F,W --ignore E501 --fix`
      
      If fixes applied: `git add -A && git commit -m "fix: post-merge linting fixes"`
      
      Verify: `ruff check src/ tests/ scenario_runner.py --select E,F,W --ignore E501` exits 0

- [ ] 6. Run full test suite and document any failures.
      
      Run pytest to identify any broken tests after the merges. Do NOT fix failures in this step — just document them.
      
      Files: none (test execution)
      
      Command: `python -m pytest tests/ -v --tb=short`
      
      Expected: some tests may fail due to schema changes, new dependencies, or integration issues. Document the count and categories of failures.
      
      Verify: command completes (regardless of exit code); note failure count and which test modules failed

- [ ] 7. Verify all critical artifacts are present.
      
      Confirm that all expected files from the three branches are now on main.
      
      Files: none (verification only)
      
      Checks:
      - `Test-Path src/p2p/__init__.py` → True
      - `Test-Path src/p2p/config.py` → True
      - `Test-Path src/p2p/loader.py` → True
      - `Test-Path src/p2p/matching.py` → True
      - `Test-Path src/p2p/models.py` → True
      - `Test-Path src/p2p/pipeline.py` → True
      - `Test-Path src/p2p/pricing.py` → True
      - `Test-Path src/persistence/migrations/003_p2p.sql` → True
      - `Test-Path src/persistence/migrations/004_temperature.sql` → True
      - `Test-Path src/persistence/migrations/005_dashboard.sql` → True
      - `Test-Path dashboard/package.json` → True
      - `Test-Path data1/smart_supermarket_neighbor_buildings_4months_15min1.csv` → True
      
      Verify: all checks pass

- [ ] 8. Update README.md if P2P trading and dashboard sections are missing.
      
      The current README (as of main) ends at "Target Architecture (Future Work)". Check if the merged code includes updates to document P2P trading and the dashboard. If not, add brief sections describing:
      - P2P Energy Trading: dynamic peer-to-peer energy matching using neighbor building datasets
      - Dashboard: React/TypeScript frontend with real-time WebSocket updates, energy flow visualization, financial metrics
      
      Files: `README.md`
      
      Command: `code README.md` (manual inspection)
      
      If sections missing: add them under "## P2P Energy Trading" and "## Dashboard" after the "Version 2" section, then commit with `git commit -m "docs: add P2P trading and dashboard sections to README"`
      
      Verify: `grep -n "P2P" README.md` and `grep -n "Dashboard" README.md` return matches

- [ ] 9. Verify CI/CD TimescaleDB health check configuration.
      
      The local main (commit 22d437b) already updated `.github/workflows/ci.yml` to use `--health-cmd "pg_isready -U b2g -d b2g"`. Confirm this is still present after all merges.
      
      Files: `.github/workflows/ci.yml`
      
      Command: `Select-String -Path .github/workflows/ci.yml -Pattern 'pg_isready -U b2g -d b2g'`
      
      Verify: match found on line containing `--health-cmd`

### Phase 4: Final Summary

- [ ] 10. Create a merge summary report.
      
      Document the final state: commits merged, conflicts resolved, test results, and next steps.
      
      Files: `.agents/tasks/merge-summary.txt`
      
      Content:
      ```
      Merge Summary
      =============
      
      Branches merged (in order):
      1. origin/feature/compliance-layer5 (2 commits)
         - Enhanced compliance layer with R1-R6 audit rules
         - Regulatory references and ComplianceReport model
      
      2. origin/ajout-datasets (1 commit)
         - Added data1/ directory with neighbor building CSVs
      
      3. origin/feature/dashboard (3 commits)
         - React/TypeScript dashboard (37 files)
         - P2P trading module (src/p2p/, 7 files)
         - Temperature monitoring (src/monitoring/temperature.py)
         - DB migrations 003_p2p, 004_temperature, 005_dashboard
         - API updates for WebSocket scenario streaming
      
      Conflicts resolved:
      - requirements.txt: kept main's line order (pytest-asyncio already pinned)
      - src/compliance/: accepted compliance branch's enhanced R1-R6 implementation
      - data1/: accepted dashboard's version (complete dataset)
      
      Final state:
      - Total commits on main: [count from git log]
      - Linting status: [pass/fail from step 5]
      - Test results: [summary from step 6]
      - All migrations present: 003_p2p.sql, 004_temperature.sql, 005_dashboard.sql
      - src/p2p/ module complete: 7 files
      - dashboard/ directory complete: 37 files
      
      Next steps:
      - Fix any test failures identified in step 6
      - Run full integration test with Docker Compose
      - Deploy migrations to dev/staging TimescaleDB
      - Test dashboard connection to backend WebSocket
      - Update any remaining documentation
      ```
      
      Command: create and commit summary
      
      Verify: `.agents/tasks/merge-summary.txt` exists

---

## Critical Notes

1. **DO NOT push to remote** after the initial push in step 1. All three branch merges stay local on main until approved.

2. **Conflict resolution priority**: When conflicts occur, prefer the most complete implementation:
   - Compliance module: compliance branch (R1-R6 is the enhancement)
   - data1/: dashboard branch (it's the complete version)
   - API: dashboard branch (it has the full P2P/temperature integration)

3. **Preserve all functionality**: Every feature from all three branches must be retained. No code should be deleted to "resolve" a conflict.

4. **Six-layer architecture**: The compliance and P2P additions preserve the six-layer pipeline structure:
   - Layer 1: Ingestion (updated schema)
   - Layer 2: Forecasting (unchanged)
   - Layer 3: MPC (unchanged)
   - Layer 4: DERMS (unchanged)
   - Layer 5: Compliance (enhanced R1-R6)
   - Layer 6: API/Visualization (dashboard + P2P endpoints added)

5. **Backward compatibility**: CSV-only mode must still work after merges (required by 36+ existing unit tests).

6. **Migration ordering**: The three SQL migrations must be applied in order: 003 → 004 → 005.

---

## Build & Test Commands (from repository exploration)

- **Lint**: `ruff check src/ tests/ scenario_runner.py --select E,F,W --ignore E501`
- **Lint fix**: `ruff check src/ tests/ scenario_runner.py --select E,F,W --ignore E501 --fix`
- **Test**: `python -m pytest tests/ -v --tb=short`
- **Run scenario**: `python scenario_runner.py`
- **Docker stack**: `docker compose up` (requires .env configuration)

---

## Verification Commands Reference

```powershell
# Git status
git status
git log --oneline -10
git branch -a

# Check artifacts
Test-Path src/p2p/
Test-Path dashboard/
Test-Path src/persistence/migrations/003_p2p.sql
ls src/p2p/
ls dashboard/

# Linting
ruff check src/ tests/ scenario_runner.py --select E,F,W --ignore E501

# Tests
python -m pytest tests/ -v

# Search
Select-String -Path .github/workflows/ci.yml -Pattern 'pg_isready'
grep -n "P2P" README.md
```
