export const ACTIONS = [
  'peak_shaving',
  'hvac_soft_shed',
  'valley_filling',
  'hard_shedding',
] as const;
export type Action = (typeof ACTIONS)[number];
export type CoverageStatus = 'NORMAL' | 'AT_RISK' | 'CRITICAL';
export const TEMPERATURE_SENSORS = [
  'display_freezer_temp',
  'freezer_room_temp',
  'display_refrigerator_temp',
  'cold_room_temp',
] as const;
export type TemperatureSensor = (typeof TEMPERATURE_SENSORS)[number];
export type TemperatureStatus = 'OK' | 'WARNING' | 'CRITICAL';
export interface TemperatureAlert {
  sensor: TemperatureSensor;
  value: number;
  status: 'WARNING' | 'CRITICAL';
  limitLow: number;
  limitHigh: number;
  since: number;
}
export interface TimestepRecord {
  neighbors?: Neighbor[];
  trades?: Trade[];
  p2pSavings?: number;
  cost?: number;
  revenue?: number;
  sellPrice?: number;
  p2pPrice?: number;
  demandKw?: number;
  pvPower?: number;
  temperatureLimits?: Partial<Record<TemperatureSensor, { low: number; high: number; hardLimit: number }>>;
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
  temperatures?: Partial<Record<TemperatureSensor, number>>;
  temperatureAlerts?: TemperatureAlert[];
  temperatureStatus?: TemperatureStatus;
}
export interface Neighbor {
  id: string;
  type: string;
  distanceKm: number;
  productionType: string;
  offerKw?: number;
  deficitKw?: number;
}
export interface Trade {
  counterpartyId: string;
  buildingType: string;
  direction: 'buy' | 'sell';
  quantityKw: number;
  quantityKwh: number;
  pricePerKwh: number;
  wheelingFee: number;
  distanceKm: number;
  savingVsGrid: number;
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
