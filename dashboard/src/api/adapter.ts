import { GRID_IMPORT_SIGN } from '../config/market';
import { ACTIONS, type TimestepRecord } from './types';
export class DataError extends Error {}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new DataError('Enregistrement invalide.');
  return value as Record<string, unknown>;
}
function numeric(row: Record<string, unknown>, key: string): number {
  const value = row[key];
  if (typeof value !== 'number' || !Number.isFinite(value))
    throw new DataError(`Valeur numérique invalide : ${key}.`);
  return value;
}
function boolean(row: Record<string, unknown>, key: string): boolean {
  if (typeof row[key] !== 'boolean') throw new DataError(`Indicateur invalide : ${key}.`);
  return row[key];
}
// Naive backend timestamps represent simulation wall time, encoded as UTC to avoid browser/DST drift.
export function parseTimestamp(value: unknown): number {
  if (
    typeof value !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$/.test(value)
  )
    throw new DataError('Horodatage invalide.');
  const iso = value.replace(' ', 'T');
  const wall = new Date(`${iso.slice(0, 19)}Z`);
  if (!Number.isFinite(wall.getTime()) || wall.toISOString().slice(0, 19) !== iso.slice(0, 19))
    throw new DataError('Date de simulation invalide.');
  const result = Date.parse(/[Z]|[+-]\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`);
  if (!Number.isFinite(result)) throw new DataError('Horodatage invalide.');
  return result;
}
export function adaptRecord(value: unknown): TimestepRecord {
  const row = object(value);
  const coverageRatio = numeric(row, 'coverage_ratio');
  const batterySoc = numeric(row, 'battery_soc');
  if (coverageRatio < 0 || coverageRatio > 1 || batterySoc < 0 || batterySoc > 100)
    throw new DataError('Mesure hors limites physiques.');
  if (!Array.isArray(row.active_actions) || row.active_actions.some((a) => !ACTIONS.includes(a)))
    throw new DataError('Action de contrôle inconnue.');
  if (row.anomaly_source !== null && typeof row.anomaly_source !== 'string')
    throw new DataError('Source d’anomalie invalide.');
  return {
    timestamp: parseTimestamp(row.timestamp),
    coverageRatio,
    coverageStatus:
      coverageRatio >= 0.95 ? 'NORMAL' : coverageRatio >= 0.9 ? 'AT_RISK' : 'CRITICAL',
    activeActions: [...new Set(row.active_actions)] as TimestepRecord['activeActions'],
    tier1Protected: boolean(row, 'tier_1_protected'),
    batterySoc,
    gridPower: numeric(row, 'grid_power') * GRID_IMPORT_SIGN,
    p2pPower: numeric(row, 'p2p_energy'),
    anomalyFlag: boolean(row, 'anomaly_flag'),
    anomalySource: row.anomaly_source,
    ...(row.energy_price == null ? {} : { energyPrice: numeric(row, 'energy_price') }),
  };
}
export function mergeRecords(records: TimestepRecord[], limit = Infinity): TimestepRecord[] {
  return [...new Map(records.map((r) => [r.timestamp, r])).values()]
    .sort((a, b) => a.timestamp - b.timestamp)
    .slice(-limit);
}
export function adaptHistory(value: unknown): TimestepRecord[] {
  if (!Array.isArray(value)) throw new DataError('Historique invalide.');
  return mergeRecords(value.map(adaptRecord));
}
