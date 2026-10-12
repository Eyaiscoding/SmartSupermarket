# Database Migrations

## Overview

This directory contains SQL migration files for the B2G Smart Supermarket database schema. Migrations are applied sequentially to evolve the database structure.

## Migration Files

1. **001_initial.sql** - Initial schema (output_records table)
2. **002_compliance.sql** - Compliance tracking columns
3. **003_p2p.sql** - P2P energy trading columns
4. **004_temperature.sql** - Temperature monitoring columns
5. **005_dashboard.sql** - Dashboard-specific columns (depends on 003 and 004)

## Execution Order

**IMPORTANT**: Migrations MUST be executed in numerical order (001 → 002 → 003 → 004 → 005).

### Dependencies

- **005_dashboard.sql** depends on columns added by **003_p2p.sql** and **004_temperature.sql**
- Running migrations out of order or skipping 003/004 will cause failures when the application attempts to write dashboard data

## Usage

Migrations are typically applied automatically by the TimescaleDB initialization process. For manual execution:

```bash
psql -U b2g -d b2g -f src/persistence/migrations/001_initial.sql
psql -U b2g -d b2g -f src/persistence/migrations/002_compliance.sql
psql -U b2g -d b2g -f src/persistence/migrations/003_p2p.sql
psql -U b2g -d b2g -f src/persistence/migrations/004_temperature.sql
psql -U b2g -d b2g -f src/persistence/migrations/005_dashboard.sql
```

## Verification

To verify all migrations have been applied:

```sql
\d+ output_records
```

The table should include all columns from migrations 001-005.
