import { describe, expect, it } from 'vitest';
import { adaptHistory, adaptRecord, mergeRecords, parseTimestamp } from './adapter';
const raw = {
  timestamp: '2025-06-01 00:00:00',
  coverage_ratio: 0.94,
  coverage_status: 'AT_RISK',
  active_actions: ['peak_shaving'],
  tier_1_protected: true,
  battery_soc: 62.3,
  grid_power: 12.4,
  p2p_energy: 0,
  anomaly_flag: false,
  anomaly_source: null,
};
describe('backend adapter', () => {
  it('preserves temperature alerts independently of Tier 1', () => {
    const record = adaptRecord({
      ...raw,
      temperatures: { cold_room_temp: 9 },
      temperature_status: 'CRITICAL',
      temperature_alerts: [
        {
          sensor: 'cold_room_temp',
          value: 9,
          status: 'CRITICAL',
          limit_low: 0,
          limit_high: 5,
          since: raw.timestamp,
        },
      ],
    });
    expect(record.tier1Protected).toBe(true);
    expect(record.temperatureStatus).toBe('CRITICAL');
    expect(record.temperatures?.display_freezer_temp).toBeUndefined();
    expect(record.temperatureAlerts?.[0].since).toBe(Date.UTC(2025, 5, 1));
    expect(adaptRecord(raw).temperatureStatus).toBeUndefined();
  });
  it('rejects malformed temperature payloads', () => {
    expect(() =>
      adaptRecord({
        ...raw,
        temperatures: { cold_room_temp: NaN },
        temperature_status: 'OK',
        temperature_alerts: [],
      }),
    ).toThrow();
    expect(() => adaptRecord({ ...raw, temperature_status: 'UNKNOWN' })).toThrow();
  });
  it('normalizes an import record without a price', () => {
    const record = adaptRecord(raw);
    expect(record.gridPower).toBe(12.4);
    expect(record.energyPrice).toBeUndefined();
    expect(record.timestamp).toBe(Date.UTC(2025, 5, 1));
    expect(record.coverageStatus).toBe('AT_RISK');
  });
  it('preserves export, prices and P2P signs', () => {
    for (const sign of [-1, 1]) {
      const record = adaptRecord({ ...raw, grid_power: -8, p2p_energy: sign * 2, energy_price: 0 });
      expect(record.gridPower).toBe(-8);
      expect(record.p2pPower).toBe(sign * 2);
      expect(record.energyPrice).toBe(0);
    }
  });
  it.each([
    [0.95, 'NORMAL'],
    [0.9, 'AT_RISK'],
    [0.899, 'CRITICAL'],
  ])('computes boundary %s consistently', (ratio, status) =>
    expect(adaptRecord({ ...raw, coverage_ratio: ratio }).coverageStatus).toBe(status),
  );
  it('never masks a Tier 1 failure or out-of-safe-band SOC', () => {
    const record = adaptRecord({ ...raw, tier_1_protected: false, battery_soc: 5 });
    expect(record.tier1Protected).toBe(false);
    expect(record.batterySoc).toBe(5);
  });
  it.each([
    { grid_power: NaN },
    { tier_1_protected: 'false' },
    { battery_soc: 101 },
    { active_actions: ['unknown'] },
    { coverage_ratio: 1.1 },
    { timestamp: 'invalid' },
    { energy_price: '0.18' },
  ])('rejects malformed fields %j', (fields) =>
    expect(() => adaptRecord({ ...raw, ...fields })).toThrow(),
  );
  it('supports zoned timestamps', () =>
    expect(parseTimestamp('2025-06-01T02:00:00+02:00')).toBe(Date.UTC(2025, 5, 1)));
  it('rejects impossible calendar dates', () =>
    expect(() => parseTimestamp('2025-02-30 00:00:00')).toThrow());
  it('sorts and deduplicates history, retaining the latest revision', () => {
    const result = adaptHistory([
      { ...raw, timestamp: '2025-06-01 00:15:00' },
      raw,
      { ...raw, grid_power: 2 },
    ]);
    expect(result).toHaveLength(2);
    expect(result[0].gridPower).toBe(2);
    expect(mergeRecords(result, 1)).toEqual([result[1]]);
  });
  it('rejects envelopes not in the contract', () =>
    expect(() => adaptHistory({ records: [] })).toThrow());
});
