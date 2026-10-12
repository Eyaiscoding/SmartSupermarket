import { useCallback, useEffect, useRef, useState } from 'react';
import { adaptRecord, mergeRecords } from '../api/adapter';
import { streamUrl } from '../api/client';
import type { Scenario, TimestepRecord } from '../api/types';
export type Connection = 'live' | 'reconnecting' | 'offline' | 'mock';
export function useStream(enabled: boolean, onComplete: () => void) {
  const [records, setRecords] = useState<TimestepRecord[]>([]);
  const [status, setStatus] = useState<Connection>('offline');
  const [error, setError] = useState('');
  const [running, setRunning] = useState(false);
  const socket = useRef<WebSocket | null>(null);
  const busy = useRef(false);
  const pending = useRef<Scenario | null>(null);
  const watchdog = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const finish = useCallback(() => {
    busy.current = false;
    setRunning(false);
    clearTimeout(watchdog.current);
  }, []);
  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let attempt = 0;
    let reconnect: ReturnType<typeof setTimeout>;
    let opening: ReturnType<typeof setTimeout>;
    const connect = () => {
      if (stopped) return;
      setStatus(attempt ? 'reconnecting' : 'offline');
      const ws = new WebSocket(streamUrl());
      socket.current = ws;
      opening = setTimeout(() => ws.close(), 10000);
      ws.onopen = () => {
        if (stopped) {
          ws.close();
          return;
        }
        clearTimeout(opening);
        attempt = 0;
        setStatus('live');
        setError('');
        if (pending.current) {
          ws.send(JSON.stringify({ scenario: pending.current }));
          pending.current = null;
        }
      };
      ws.onmessage = (event: MessageEvent<string>) => {
        if (stopped) return;
        try {
          const data: unknown = JSON.parse(event.data);
          if (
            typeof data === 'object' &&
            data !== null &&
            'type' in data &&
            data.type === 'summary'
          ) {
            finish();
            onComplete();
            return;
          }
          const record = adaptRecord(data);
          setRecords((previous) => mergeRecords([...previous, record], 96));
        } catch {
          setError(
            'Une trame invalide a été ignorée. Les dernières mesures valides sont conservées.',
          );
        }
      };
      ws.onerror = () => {
        if (stopped) return;
        setError('Connexion au flux interrompue. Nouvelle tentative automatique.');
        ws.close();
      };
      ws.onclose = () => {
        clearTimeout(opening);
        if (stopped) return;
        if (busy.current && !pending.current) {
          setError(
            'Simulation interrompue : résultats potentiellement incomplets. Relancez le scénario.',
          );
          finish();
        }
        setStatus(navigator.onLine ? 'reconnecting' : 'offline');
        reconnect = setTimeout(
          connect,
          Math.min(30000, 1000 * 2 ** attempt++) + Math.random() * 300,
        );
      };
    };
    connect();
    return () => {
      stopped = true;
      clearTimeout(reconnect);
      clearTimeout(opening);
      clearTimeout(watchdog.current);
      pending.current = null;
      busy.current = false;
      setRunning(false);
      setStatus('offline');
      socket.current?.close();
      socket.current = null;
    };
  }, [enabled, finish, onComplete]);
  const start = useCallback(
    (scenario: Scenario) => {
      const ws = socket.current;
      if (!ws || ws.readyState !== WebSocket.OPEN || busy.current)
        throw new Error('Attendez la connexion au flux avant de lancer le scénario.');
      setRecords([]);
      setError('');
      setRunning(true);
      busy.current = true;
      // The repository server consumes one command per connection. Always use a fresh connection.
      pending.current = scenario;
      ws.close();
      watchdog.current = setTimeout(() => {
        pending.current = null;
        finish();
        socket.current?.close();
        setError('Le délai de simulation est dépassé. Vérifiez le serveur avant de relancer.');
      }, 300000);
    },
    [finish],
  );
  return { records, status, error, running, start };
}
