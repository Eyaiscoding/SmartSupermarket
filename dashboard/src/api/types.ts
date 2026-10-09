export const ACTIONS = [
  'peak_shaving',
  'hvac_soft_shed',
  'valley_filling',
  'hard_shedding',
] as const;
export type Action = (typeof ACTIONS)[number];
export type CoverageStatus = 'NORMAL' | 'AT_RISK' | 'CRITICAL';
export interface TimestepRecord {
  timestamp: number;
  coverageRatio: number;
  coverageStatus: CoverageStatus;
  activeActions: Action[];
  tier1Protected: boolean;
  batterySoc: number;
  gridPower: number;
  p2pPower: number;
  anomalyFlag: boolean;
  anomalySource: string | null;
  energyPrice?: number;
}
export type Scenario = 'none' | 'forced_grid_outage' | 'price_spike' | 'sensor_corruption';
export const SCENARIOS: Record<Scenario, string> = {
  none: 'Fonctionnement normal',
  forced_grid_outage: 'Coupure du réseau',
  price_spike: 'Pic de prix',
  sensor_corruption: 'Défaillance capteur',
};
export const ACTION_LABELS: Record<Action, string> = {
  peak_shaving: 'Écrêtage des pointes',
  hvac_soft_shed: 'Réduction CVC',
  valley_filling: 'Charge en heures creuses',
  hard_shedding: 'Délestage renforcé',
};
