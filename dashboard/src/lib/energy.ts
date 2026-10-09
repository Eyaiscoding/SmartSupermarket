import type { TimestepRecord } from '../api/types';
import { DEFAULT_BUY_PRICE, FEED_IN_TARIFF, P2P_PRICE, STEP_HOURS } from '../config/market';
export interface EnergyMetrics {
  bought: number;
  sold: number;
  p2p: number;
  cost: number;
  revenue: number;
  net: number;
  p2pValue: number;
}
export const kWh = (power: number): number => power * STEP_HOURS;
export function stepMetrics(record: TimestepRecord): EnergyMetrics {
  const bought = kWh(Math.max(record.gridPower, 0));
  const sold = kWh(Math.max(-record.gridPower, 0));
  const p2p = kWh(Math.abs(record.p2pPower));
  const cost = bought * (record.energyPrice ?? DEFAULT_BUY_PRICE);
  const revenue = sold * FEED_IN_TARIFF;
  return { bought, sold, p2p, cost, revenue, net: revenue - cost, p2pValue: p2p * P2P_PRICE };
}
export function totalMetrics(records: TimestepRecord[]): EnergyMetrics {
  return records.reduce(
    (sum, record) => {
      const step = stepMetrics(record);
      return {
        bought: sum.bought + step.bought,
        sold: sum.sold + step.sold,
        p2p: sum.p2p + step.p2p,
        cost: sum.cost + step.cost,
        revenue: sum.revenue + step.revenue,
        net: sum.net + step.net,
        p2pValue: sum.p2pValue + step.p2pValue,
      };
    },
    { bought: 0, sold: 0, p2p: 0, cost: 0, revenue: 0, net: 0, p2pValue: 0 },
  );
}
export type Aggregation = 'step' | 'hour' | 'day';
export function aggregateEnergy(records: TimestepRecord[], aggregation: Aggregation) {
  const duration = { step: 900000, hour: 3600000, day: 86400000 }[aggregation];
  const buckets = new Map<number, { timestamp: number; bought: number; sold: number }>();
  for (const record of records) {
    const timestamp = Math.floor(record.timestamp / duration) * duration;
    const bucket = buckets.get(timestamp) ?? { timestamp, bought: 0, sold: 0 };
    const step = stepMetrics(record);
    bucket.bought += step.bought;
    bucket.sold += step.sold;
    buckets.set(timestamp, bucket);
  }
  return [...buckets.values()].sort((a, b) => a.timestamp - b.timestamp);
}
export function cumulativeBalance(records: TimestepRecord[]) {
  let balance = 0;
  return [...records]
    .sort((a, b) => a.timestamp - b.timestamp)
    .map((record) => ({
      timestamp: record.timestamp,
      balance: (balance += stepMetrics(record).net),
    }));
}
