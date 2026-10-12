-- Informational observations; nullable for legacy records. Safe to repeat.
ALTER TABLE output_records ADD COLUMN IF NOT EXISTS temperatures JSONB;
ALTER TABLE output_records ADD COLUMN IF NOT EXISTS temperature_alerts JSONB;
ALTER TABLE output_records ADD COLUMN IF NOT EXISTS temperature_status VARCHAR(8);
