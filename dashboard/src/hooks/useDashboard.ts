import { useCallback, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from '../api/client';
import { mergeRecords } from '../api/adapter';
import { DATA_START, DATA_END, STEP_MS, mockHistory, mockRecord } from '../api/mock';
import type { Scenario, TimestepRecord } from '../api/types';
import { useStream } from './useStream';
export function useDashboard() {
  const client = useQueryClient();
  const [mode, setMode] = useState<'live' | 'history'>('live');
  const [range, setRange] = useState({ start: '2025-06-01', end: '2025-06-01' });
  const [scenario, setScenario] = useState<Scenario>('none');
  const [mockScenario, setMockScenario] = useState<Scenario>('none');
  const availability = useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => api.health(signal),
    enabled: !api.FORCE_MOCK,
    retry: false,
    refetchInterval: 15000,
  });
  const mock = api.FORCE_MOCK || availability.isError;
  const online = !api.FORCE_MOCK && availability.isSuccess && !availability.isError;
  
  // Debug logging
  useEffect(() => {
    console.log('[Dashboard] FORCE_MOCK:', api.FORCE_MOCK);
    console.log('[Dashboard] availability.isError:', availability.isError);
    console.log('[Dashboard] availability.isSuccess:', availability.isSuccess);
    console.log('[Dashboard] mock:', mock);
    console.log('[Dashboard] online:', online);
    if (availability.error) {
      console.error('[Dashboard] Health check error:', availability.error);
    }
  }, [mock, online, availability.isError, availability.isSuccess, availability.error]);
  const onComplete = useCallback(() => {
    void client.invalidateQueries({ queryKey: ['history'] });
    void client.invalidateQueries({ queryKey: ['latest'] });
  }, [client]);
  const stream = useStream(online, onComplete);
  const current = useQuery({
    queryKey: ['latest'],
    queryFn: ({ signal }) => api.latest(signal),
    enabled: online,
    retry: false,
    refetchInterval: 15000,
  });
  const [mockRecords, setMockRecords] = useState<TimestepRecord[]>(() =>
    mockHistory(DATA_START, DATA_START + 95 * STEP_MS),
  );
  useEffect(() => {
    if (!mock) return;
    const timer = setInterval(
      () =>
        setMockRecords((previous) => {
          const next = (previous.at(-1)?.timestamp ?? DATA_START) + STEP_MS;
          return next > DATA_END
            ? mockHistory(DATA_START, DATA_START + 95 * STEP_MS, mockScenario)
            : [...previous, mockRecord(next, mockScenario)].slice(-96);
        }),
      2500,
    );
    return () => clearInterval(timer);
  }, [mock, mockScenario]);
  const historical = useQuery({
    queryKey: ['history', range, mock, mockScenario],
    enabled: mode === 'history' && (mock || online),
    queryFn: ({ signal }) =>
      mock
        ? Promise.resolve(
            mockHistory(
              Date.parse(`${range.start}T00:00:00Z`),
              Date.parse(`${range.end}T23:59:59Z`),
              mockScenario,
            ),
          )
        : api.history(range.start, range.end, signal),
    retry: false,
  });
  const mutation = useMutation({
    mutationFn: async (selected: Scenario) => {
      if (mock) {
        setMockScenario(selected);
        setMockRecords(mockHistory(DATA_START, DATA_START + 95 * STEP_MS, selected));
        return;
      }
      if (api.SCENARIO_TRANSPORT === 'websocket') {
        stream.start(selected);
        client.setQueryData(['latest'], null);
        setMode('live');
        return;
      }
      await api.runScenario(selected);
      await Promise.all([
        client.invalidateQueries({ queryKey: ['latest'] }),
        client.invalidateQueries({ queryKey: ['history'] }),
      ]);
    },
  });
  const records =
    mode === 'history'
      ? (historical.data ?? [])
      : mock
        ? mockRecords
        : mergeRecords([...(current.data ? [current.data] : []), ...stream.records], 96);
  const error =
    mode === 'history' && historical.error
      ? 'Impossible de charger l’historique. Vérifiez la disponibilité du stockage et réessayez.'
      : !mock
        ? stream.error ||
          (current.error ? 'La dernière mesure est indisponible. Le flux reste en écoute.' : '')
        : '';
  return {
    mode,
    setMode,
    range,
    setRange,
    scenario,
    setScenario,
    mock,
    records,
    status: mock ? ('mock' as const) : stream.status,
    loading: (!mock && availability.isPending) || (mode === 'history' && historical.isFetching),
    error,
    retry: () => {
      void historical.refetch();
      void current.refetch();
    },
    run: () => mutation.mutate(scenario),
    running: mutation.isPending || stream.running,
    runDisabled:
      !mock && (!online || (api.SCENARIO_TRANSPORT === 'websocket' && stream.status !== 'live')),
    runError: mutation.error?.message,
    runSuccess: mutation.isSuccess && !stream.running && !stream.error,
  };
}
