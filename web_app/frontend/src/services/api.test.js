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
    const listener = vi.fn();
    window.addEventListener(authApi.authChangedEvent, listener);
    global.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: 'Token expired' }), { status: 401 })));

    await expect(auditsApi.list()).rejects.toThrow('Token expired');

    expect(window.localStorage.getItem(authApi.tokenKey)).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(authApi.authChangedEvent, listener);
  });

  it('clears stale token for raw response API calls', async () => {
    window.localStorage.setItem(authApi.tokenKey, 'stale-token');
    const listener = vi.fn();
    window.addEventListener(authApi.authChangedEvent, listener);
    global.fetch = vi.fn(() => Promise.resolve(new Response('', { status: 401 })));

    const response = await auditsApi.delete('audit-1');

    expect(response.status).toBe(401);
    expect(window.localStorage.getItem(authApi.tokenKey)).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(authApi.authChangedEvent, listener);
  });

  it('sends bearer token on protected API calls', async () => {
    window.localStorage.setItem(authApi.tokenKey, 'fresh-token');
    global.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ total: 0, audits: [] }), { status: 200 })));

    await auditsApi.list();

    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/audits/'), expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer fresh-token' }),
    }));
  });

  it('uploads zip audits as multipart with audit settings', async () => {
    window.localStorage.setItem(authApi.tokenKey, 'fresh-token');
    const file = new File(['zip-bytes'], 'target.zip', { type: 'application/zip' });
    global.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ id: 'audit-1' }), { status: 200 })));

    await auditsApi.uploadZip({
      file,
      name: 'Zip Audit',
      workerId: '2',
      questionOwnerUserId: '7',
      aiReviewEnabled: true,
      autoContinue: true,
      codecomeYml: 'project: demo',
    });

    const [, options] = global.fetch.mock.calls[0];
    expect(String(global.fetch.mock.calls[0][0])).toContain('/api/audits/upload-zip');
    expect(options.headers.Authorization).toBe('Bearer fresh-token');
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.body.get('file')).toBe(file);
    expect(options.body.get('name')).toBe('Zip Audit');
    expect(options.body.get('worker_id')).toBe('2');
    expect(options.body.get('question_owner_user_id')).toBe('7');
    expect(options.body.get('ai_review_enabled')).toBe('true');
    expect(options.body.get('auto_continue')).toBe('true');
    expect(options.body.get('codecome_yml')).toBe('project: demo');
  });
});
