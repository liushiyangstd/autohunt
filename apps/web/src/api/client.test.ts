import { afterEach, describe, expect, it, vi } from 'vitest';
import { ensureUiSession } from './client';

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
