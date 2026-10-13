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
  
  // SCENARIO: FORCED GRID OUTAGE - Multiple full-day outages
  const outage = scenario === 'forced_grid_outage' && 
    (dayOfPeriod % 15 === 5 || dayOfPeriod % 15 === 10) && // Two outages every 15 days
    hour >= 10 && hour < 22; // 12 hours outage
  
  // SCENARIO: PRICE SPIKE - Extreme prices during evening peaks
  let price = 0.18; // Base price
  const priceSpike = scenario === 'price_spike' && hour >= 18 && hour < 21; // Every evening
  if (priceSpike) {
    price = 1.20; // 7x normal price
  } else if (hour < 6) {
    price = 0.10; // Cheap at night
  }
  
  // SCENARIO: SENSOR CORRUPTION - Erratic readings
  const sensorFailure = scenario === 'sensor_corruption' && 
    (dayOfPeriod % 10 === 3 || dayOfPeriod % 10 === 7) && // Two failures every 10 days
    hour >= 12 && hour < 18; // Afternoon failures
  
  if (sensorFailure) {
    demand *= 1.8; // Demand sensor reads high
  }
  
  // Calculate system state based on scenario
  let batterySoc: number;
  let gridPower: number;
  let coverageRatio: number;
  let activeActions: string[];
  let tier1Protected = true;
  
  if (outage) {
    // GRID OUTAGE: Must survive on battery + solar only
    const available = solar + Math.max(0, 70 - (hour - 10) * 5); // Battery draining
    batterySoc = Math.max(5, 90 - (hour - 10) * 7); // Rapid discharge
    gridPower = 0;
    coverageRatio = Math.min(0.95, available / demand);
    activeActions = batterySoc < 30 ? ['hard_shedding'] : ['peak_shaving', 'hvac_soft_shed'];
    tier1Protected = batterySoc > 15; // Risk if battery too low
  } else if (priceSpike) {
    // PRICE SPIKE: Avoid grid, use battery aggressively
    batterySoc = Math.max(20, 85 - (hour - 18) * 15); // Discharge during spike
    const batteryContribution = Math.min(40, demand - solar);
    gridPower = Math.max(0, demand - solar - batteryContribution) * GRID_IMPORT_SIGN;
    coverageRatio = 0.97;
    activeActions = ['peak_shaving', 'hvac_soft_shed']; // Reduce demand
    tier1Protected = true;
  } else if (sensorFailure) {
    // SENSOR CORRUPTION: System confused by bad readings
    batterySoc = 45 + Math.sin(step * 3.7) * 30; // Erratic behavior
    gridPower = (demand - solar) * GRID_IMPORT_SIGN * 1.3; // Over-importing
    coverageRatio = 0.92 + Math.random() * 0.06; // Unstable
    activeActions = ['peak_shaving']; // Wrong decisions
    tier1Protected = true;
  } else {
    // NORMAL: Optimal operation
    batterySoc = Math.max(15, Math.min(95, 52 + 34 * Math.sin(((hour - 8) / 24) * 2 * Math.PI)));
    gridPower = (demand - solar) * GRID_IMPORT_SIGN;
    coverageRatio = 0.98 + Math.sin(step) * 0.014;
    activeActions = hour < 5 ? ['valley_filling'] : evening > 12 ? ['peak_shaving'] : [];
    tier1Protected = true;
  }
  
  // Coverage status
  const critical = coverageRatio < 0.90 || !tier1Protected;
  const risk = coverageRatio >= 0.90 && coverageRatio < 0.95;
  
  // Anomaly detection
  const anomaly = sensorFailure || (scenario === 'none' && step % 53 === 12);
  
  return adaptRecord({
    timestamp: new Date(timestamp).toISOString(),
    coverage_ratio: Math.round(coverageRatio * 10000) / 10000,
    coverage_status: critical ? 'CRITICAL' : risk ? 'AT_RISK' : 'NORMAL',
    active_actions: activeActions,
    tier_1_protected: tier1Protected,
    battery_soc: Math.round(batterySoc * 100) / 100,
    grid_power: Math.round(gridPower * 100) / 100,
    p2p_energy: solar > 45 ? -4 : hour > 18 && hour < 21 ? 3 : 0,
    anomaly_flag: anomaly,
    anomaly_source: anomaly
      ? scenario === 'sensor_corruption'
        ? 'Capteur de consommation défaillant - lecture +80%'
        : 'Écart inhabituel entre prévision et mesure'
      : null,
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
