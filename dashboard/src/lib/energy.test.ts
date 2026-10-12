import { describe, expect, it } from 'vitest';
import { aggregateEnergy, cumulativeBalance, kWh, stepMetrics, totalMetrics } from './energy';
import { mockRecord, DATA_START } from '../api/mock';
const base = mockRecord(DATA_START);
describe('energy accounting', () => {
  it('converts one 15-minute step into kWh', () => expect(kWh(12)).toBe(3));
  it('accounts for an import-only step', () => {
    const result = stepMetrics({ ...base, gridPower: 12, p2pPower: 0, energyPrice: 0.2 });
    expect(result.bought).toBe(3);
    expect(result.sold).toBe(0);
    expect(result.cost).toBeCloseTo(0.6);
    expect(result.revenue).toBe(0);
    expect(result.net).toBeCloseTo(-0.6);
  });
  it('accounts for an export-only step', () => {
    const result = stepMetrics({ ...base, gridPower: -8, p2pPower: 0 });
    expect(result.bought).toBe(0);
    expect(result.sold).toBe(2);
    expect(result.cost).toBe(0);
    expect(result.revenue).toBeCloseTo(0.16);
    expect(result.net).toBeCloseTo(0.16);
  });
  it('uses default buy price when energy_price is missing', () =>
    expect(stepMetrics({ ...base, gridPower: 4, energyPrice: undefined }).cost).toBeCloseTo(0.18));
  it('preserves a zero or negative buy price', () => {
    expect(stepMetrics({ ...base, gridPower: 4, energyPrice: 0 }).cost).toBe(0);
    expect(stepMetrics({ ...base, gridPower: 4, energyPrice: -0.1 }).net).toBeCloseTo(0.1);
  });
  it.each([-8, 8])('uses absolute P2P volume for sign %s', (power) => {
    const result = stepMetrics({ ...base, gridPower: 0, p2pPower: power });
    expect(result.p2p).toBe(2);
    expect(result.p2pValue).toBeCloseTo(0.24);
    expect(result.net).toBe(0);
  });
  it('aggregates by hour and day without losing volume', () => {
    const records = [0, 1, 4, 96].map((i) => ({
      ...base,
      timestamp: DATA_START + i * 900000,
      gridPower: 4,
    }));
    expect(aggregateEnergy(records, 'step')).toHaveLength(4);
    expect(aggregateEnergy(records, 'hour').map((r) => r.bought)).toEqual([2, 1, 1]);
    expect(aggregateEnergy(records, 'day').map((r) => r.bought)).toEqual([3, 1]);
    expect(totalMetrics(records).bought).toBe(4);
    expect(cumulativeBalance(records).at(-1)?.balance).toBeCloseTo(totalMetrics(records).net);
  });
  it('handles empty periods', () => {
    expect(totalMetrics([]).net).toBe(0);
    expect(cumulativeBalance([])).toEqual([]);
  });
});
