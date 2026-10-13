import { adaptRecord } from './adapter';
import type { Scenario, TimestepRecord } from './types';
import { GRID_IMPORT_SIGN } from '../config/market';
export const DATA_START = Date.UTC(2025, 5, 1);
export const DATA_END = Date.UTC(2025, 8, 30, 23, 45);
export const STEP_MS = 15 * 60 * 1000;
export function mockRecord(timestamp: number, scenario: Scenario = 'none'): TimestepRecord {
  const step = Math.floor((timestamp - DATA_START) / STEP_MS);
  const hour = (step % 96) / 4;
  const dayOfPeriod = Math.floor(step / 96);
  
  // Base solar and demand patterns
  const solar = Math.max(0, Math.sin(((hour - 6) / 12) * Math.PI)) * 62;
  const evening = Math.exp(-(((hour - 19) / 2.2) ** 2)) * 22;
  let demand = 20 + (hour > 7 && hour < 22 ? 17 : 0) + evening + Math.sin(step * 1.7) * 2;
  
  // ========== SCENARIO VARIATIONS - VERY VISIBLE ==========
  
  let batterySoc: number;
  let gridPower: number;
  let coverageRatio: number;
  let activeActions: string[];
  let tier1Protected = true;
  let price = 0.18;
  let anomalyFlag = false;
  let anomalySource: string | null = null;
  
  if (scenario === 'forced_grid_outage') {
    // GRID OUTAGE: Grid is ZERO, battery drains, coverage drops
    batterySoc = Math.max(5, 90 - step * 0.3); // Rapid drain
    gridPower = 0; // NO GRID
    coverageRatio = Math.max(0.65, 0.95 - step * 0.005); // Deteriorating
    activeActions = batterySoc < 30 ? ['hard_shedding'] : ['peak_shaving', 'hvac_soft_shed'];
    tier1Protected = batterySoc > 15;
    price = 0.0; // No price during outage
    
  } else if (scenario === 'price_spike') {
    // PRICE SPIKE: High price, aggressive battery use, reduced grid
    const inPeakHour = hour >= 18 && hour < 21;
    price = inPeakHour ? 1.20 : 0.18; // 7x price during peak
    batterySoc = inPeakHour 
      ? Math.max(20, 85 - (hour - 18) * 20) // Discharge fast during peak
      : Math.min(90, 50 + hour * 2); // Charge otherwise
    gridPower = inPeakHour
      ? Math.max(5, (demand - solar) * 0.3) * GRID_IMPORT_SIGN // Minimal grid use
      : (demand - solar) * GRID_IMPORT_SIGN;
    coverageRatio = 0.96;
    activeActions = inPeakHour ? ['peak_shaving', 'hvac_soft_shed'] : hour < 6 ? ['valley_filling'] : [];
    
  } else if (scenario === 'sensor_corruption') {
    // SENSOR CORRUPTION: Erratic readings, high demand, unstable
    demand *= 1.8; // Sensor reads HIGH
    batterySoc = 30 + Math.sin(step * 0.5) * 25; // Erratic (5-55%)
    gridPower = (demand - solar) * 1.5 * GRID_IMPORT_SIGN; // Over-importing due to bad readings
    coverageRatio = 0.88 + Math.sin(step * 0.7) * 0.08; // Unstable (80-96%)
    activeActions = ['peak_shaving'];
    anomalyFlag = true;
    anomalySource = 'Capteur de consommation défaillant - lecture +80%';
    
  } else {
    // NORMAL: Smooth, optimal operation
    batterySoc = Math.max(15, Math.min(95, 52 + 34 * Math.sin(((hour - 8) / 24) * 2 * Math.PI)));
    gridPower = (demand - solar) * GRID_IMPORT_SIGN;
    coverageRatio = 0.98 + Math.sin(step) * 0.014;
    activeActions = hour < 5 ? ['valley_filling'] : evening > 12 ? ['peak_shaving'] : [];
    anomalyFlag = step % 53 === 12;
    anomalySource = anomalyFlag ? 'Écart inhabituel entre prévision et mesure' : null;
  }
  
  // Coverage status
  const critical = coverageRatio < 0.90 || !tier1Protected;
  const risk = coverageRatio >= 0.90 && coverageRatio < 0.95;
  
  return adaptRecord({
    timestamp: new Date(timestamp).toISOString(),
    coverage_ratio: Math.round(coverageRatio * 10000) / 10000,
    coverage_status: critical ? 'CRITICAL' : risk ? 'AT_RISK' : 'NORMAL',
    active_actions: activeActions,
    tier_1_protected: tier1Protected,
    battery_soc: Math.round(batterySoc * 100) / 100,
    grid_power: Math.round(gridPower * 100) / 100,
    p2p_energy: solar > 45 ? -4 : hour > 18 && hour < 21 ? 3 : 0,
    anomaly_flag: anomalyFlag,
    anomaly_source: anomalySource,
    energy_price: price,
    demand_kw: Math.round(demand * 100) / 100,
    pv_power: Math.round(solar * 100) / 100,
  });
}
export function mockHistory(start: number, end: number, scenario: Scenario = 'none') {
  const records: TimestepRecord[] = [];
  for (let t = Math.max(start, DATA_START); t <= Math.min(end, DATA_END); t += STEP_MS)
    records.push(mockRecord(t, scenario));
  return records;
}
