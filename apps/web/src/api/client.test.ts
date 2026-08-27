import { afterEach, describe, expect, it, vi } from 'vitest';
import { ensureUiSession, httpApi } from './client';

describe('ensureUiSession（UI session 引导端点）', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('以 credentials:include 调用 GET /api/v1/ui/session', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 })));
    vi.stubGlobal('fetch', fetchMock);
    await ensureUiSession();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/ui/session', { credentials: 'include' });
  });

  it('后端未就绪（网络错误）时静默返回，不抛出', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))));
    await expect(ensureUiSession()).resolves.toBeUndefined();
  });
});

describe('httpApi.listKeys（契约：裸数组，非 {items} 信封）', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('按裸数组解析，queryFn 不得返回 undefined（React Query 约束）', async () => {
    const rows = [{ id: 'k1', name: 'agent', prefix: 'ah_live_ab', created_at: '2026-08-28T00:00:00', last_used_at: null }];
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify(rows), { status: 200 }))));
    await expect(httpApi.listKeys()).resolves.toEqual(rows);
  });
});

