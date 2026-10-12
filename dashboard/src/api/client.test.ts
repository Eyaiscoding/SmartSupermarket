import { afterEach, describe, expect, it, vi } from 'vitest';
import { API_URL, history, latest, runScenario, streamUrl } from './client';
afterEach(() => vi.unstubAllGlobals());
describe('REST contract', () => {
  it('treats latest 404 as empty, not as mock data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 404 })));
    expect(await latest()).toBeNull();
  });
  it('surfaces unavailable history instead of replacing real results', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 503 })));
    await expect(history('2025-06-01', '2025-06-02')).rejects.toThrow('503');
  });
  it('sends the exact scenario body and content type', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    await runScenario('none');
    expect(fetch).toHaveBeenCalledWith(
      `${API_URL}/api/v1/scenario`,
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{"scenario":"none"}',
      }),
    );
  });
  it('encodes inclusive historical dates', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    await history('2025-06-01', '2025-06-02');
    const url = new URL(fetch.mock.calls[0][0] as string);
    expect(url.searchParams.get('start')).toBe('2025-06-01 00:00:00');
    expect(url.searchParams.get('end')).toBe('2025-06-02 23:59:59');
  });
  it('derives the socket endpoint from the configured API origin', () => {
    expect(new URL(streamUrl()).pathname).toBe(
      `${new URL(API_URL).pathname.replace(/\/$/, '')}/ws/stream`,
    );
  });
});
