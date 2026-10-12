import { expect, it } from 'vitest';
import { DATA_START, DATA_END, mockHistory } from './mock';
it('generates all 11712 steps with protected refrigeration and realistic exchange', () => {
  const records = mockHistory(DATA_START, DATA_END);
  expect(records).toHaveLength(11712);
  expect(records.every((r) => r.tier1Protected && r.batterySoc >= 10 && r.batterySoc <= 95)).toBe(
    true,
  );
  expect(records.some((r) => r.gridPower < 0)).toBe(true);
  expect(records.some((r) => r.coverageStatus === 'CRITICAL')).toBe(true);
  expect(records.some((r) => r.coverageStatus === 'AT_RISK')).toBe(true);
  expect(records.some((r) => r.anomalyFlag)).toBe(true);
});
