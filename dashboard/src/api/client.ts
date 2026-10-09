import { adaptHistory, adaptRecord } from './adapter';
import type { Scenario } from './types';
export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
export const FORCE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';
export const SCENARIO_TRANSPORT = import.meta.env.VITE_SCENARIO_TRANSPORT || 'websocket';
export function streamUrl() {
  const url = new URL(`${API_URL}/ws/stream`);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}
export class HttpError extends Error {
  constructor(public status: number) {
    super(`Le serveur a répondu avec une erreur (${status}).`);
  }
}
export async function request(
  path: string,
  options: RequestInit = {},
  timeout = 8000,
): Promise<unknown> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    signal: AbortSignal.any([
      AbortSignal.timeout(timeout),
      ...(options.signal ? [options.signal] : []),
    ]),
  });
  if (!response.ok) throw new HttpError(response.status);
  return response.json() as Promise<unknown>;
}
export const health = (signal?: AbortSignal) => request('/health', { signal });
export async function latest(signal?: AbortSignal) {
  try {
    return adaptRecord(await request('/api/v1/latest', { signal }));
  } catch (error) {
    if (error instanceof HttpError && error.status === 404) return null;
    throw error;
  }
}
export async function history(start: string, end: string, signal?: AbortSignal) {
  return adaptHistory(
    await request(
      `/api/v1/history?${new URLSearchParams({ start: `${start} 00:00:00`, end: `${end} 23:59:59` })}`,
      { signal },
    ),
  );
}
export const runScenario = (scenario: Scenario) =>
  request(
    '/api/v1/scenario',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario }),
    },
    300000,
  );
