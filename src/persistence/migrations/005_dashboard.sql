-- Dashboard columns migration
-- REQUIRES: 003_p2p.sql and 004_temperature.sql
--
-- This migration adds dashboard-specific columns to output_records.
-- It depends on columns created by:
--   - 003_p2p.sql (P2P energy trading columns)
--   - 004_temperature.sql (temperature monitoring columns)
--
-- Migrations MUST be run in order: 001, 002, 003, 004, 005

ALTER TABLE output_records ADD COLUMN IF NOT EXISTS neighbors JSONB;
ALTER TABLE output_records ADD COLUMN IF NOT EXISTS demand_kw DOUBLE PRECISION;
ALTER TABLE output_records ADD COLUMN IF NOT EXISTS pv_power DOUBLE PRECISION;
ALTER TABLE output_records ADD COLUMN IF NOT EXISTS temperature_limits JSONB;
