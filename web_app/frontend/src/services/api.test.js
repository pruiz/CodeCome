import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { auditsApi, authApi } from './api';

describe('api auth handling', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('clears stale token on protected API 401', async () => {
    window.localStorage.setItem(authApi.tokenKey, 'stale-token');
    global.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: 'Token expired' }), { status: 401 })));

    await expect(auditsApi.list()).rejects.toThrow('Token expired');

    expect(window.localStorage.getItem(authApi.tokenKey)).toBeNull();
  });

  it('sends bearer token on protected API calls', async () => {
    window.localStorage.setItem(authApi.tokenKey, 'fresh-token');
    global.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ total: 0, audits: [] }), { status: 200 })));

    await auditsApi.list();

    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/audits/'), expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer fresh-token' }),
    }));
  });
});
