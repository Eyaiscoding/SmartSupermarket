import { adaptRecord } from './adapter';
import type { Scenario, TimestepRecord } from './types';
import { GRID_IMPORT_SIGN } from '../config/market';
export const DATA_START = Date.UTC(2025, 5, 1);
export const DATA_END = Date.UTC(2025, 8, 30, 23, 45);
export const STEP_MS = 15 * 60 * 1000;
export function mockRecord(timestamp: number, scenario: Scenario = 'none'): TimestepRecord {
  const step = Math.floor((timestamp - DATA_START) / STEP_MS);
  const hour = (step % 96) / 4;
  const solar = Math.max(0, Math.sin(((hour - 6) / 12) * Math.PI)) * 62;
  const evening = Math.exp(-(((hour - 19) / 2.2) ** 2)) * 22;
  const demand = 20 + (hour > 7 && hour < 22 ? 17 : 0) + evening + Math.sin(step * 1.7) * 2;
  const outage = scenario === 'forced_grid_outage' && hour >= 18 && hour < 20;
  const risk = hour >= 18.5 && hour < 19.25;
  const critical = outage || step % 191 === 75;
  const ratio = critical ? 0.87 : risk ? 0.927 : 0.98 + Math.sin(step) * 0.014;
  const anomaly = step % 53 === 12 || (scenario === 'sensor_corruption' && hour >= 14 && hour < 15);
  return adaptRecord({
    timestamp: new Date(timestamp).toISOString(),
    coverage_ratio: ratio,
    coverage_status: critical ? 'CRITICAL' : risk ? 'AT_RISK' : 'NORMAL',
    active_actions: critical
      ? ['hard_shedding']
      : risk
        ? ['peak_shaving', 'hvac_soft_shed']
        : hour < 5
          ? ['valley_filling']
          : evening > 12
            ? ['peak_shaving']
            : [],
    tier_1_protected: true,
    battery_soc: Math.max(10, Math.min(95, 52 + 34 * Math.sin(((hour - 8) / 24) * 2 * Math.PI))),
    grid_power: (outage ? 0 : demand - solar) * GRID_IMPORT_SIGN,
    p2p_energy: solar > 45 ? -4 : hour > 18 && hour < 21 ? 3 : 0,
    anomaly_flag: anomaly,
    anomaly_source: anomaly
      ? scenario === 'sensor_corruption'
        ? 'Capteur de température incohérent'
        : 'Écart entre prévision et consommation'
      : null,
    ...(scenario === 'price_spike' ? { energy_price: hour >= 18 && hour < 21 ? 0.9 : 0.18 } : {}),
  });
}
export function mockHistory(start: number, end: number, scenario: Scenario = 'none') {
  const records: TimestepRecord[] = [];
  for (let t = Math.max(start, DATA_START); t <= Math.min(end, DATA_END); t += STEP_MS)
    records.push(mockRecord(t, scenario));
  return records;
}
