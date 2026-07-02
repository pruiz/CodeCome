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

  it('queues gap scan workflow actions with auth headers', async () => {
    window.localStorage.setItem(authApi.tokenKey, 'fresh-token');
    global.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ message: 'queued' }), { status: 200 })));

    await auditsApi.runGapScan('audit-1');
    await auditsApi.runGapCompare('audit-1');
    await auditsApi.runGapSweep('audit-1', 'GAP-0007');
    await auditsApi.gapPrompt('audit-1');
    await auditsApi.updateGapPrompt('audit-1', 'Custom prompt');
    await auditsApi.markGapCandidate('audit-1', 'GAP-0007', { decision: 'ignored', note: 'not relevant' });

    expect(global.fetch.mock.calls[0][0]).toBe('/api/audits/audit-1/gap-scan');
    expect(global.fetch.mock.calls[1][0]).toBe('/api/audits/audit-1/gap-compare');
    expect(global.fetch.mock.calls[2][0]).toBe('/api/audits/audit-1/gap-sweep?candidate=GAP-0007');
    expect(global.fetch.mock.calls[3][0]).toBe('/api/audits/audit-1/gap-prompt');
    expect(global.fetch.mock.calls[4][0]).toBe('/api/audits/audit-1/gap-prompt');
    expect(global.fetch.mock.calls[4][1].method).toBe('PUT');
    expect(JSON.parse(global.fetch.mock.calls[4][1].body)).toEqual({ prompt: 'Custom prompt' });
    expect(global.fetch.mock.calls[5][0]).toBe('/api/audits/audit-1/gap-candidates/GAP-0007/mark');
    expect(global.fetch.mock.calls.every(([, options]) => options.headers.Authorization === 'Bearer fresh-token')).toBe(true);
    expect(JSON.parse(global.fetch.mock.calls[5][1].body)).toEqual({ decision: 'ignored', note: 'not relevant' });
  });

  it('calls phase 1 enrichment APIs with auth headers', async () => {
    window.localStorage.setItem(authApi.tokenKey, 'fresh-token');
    global.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ message: 'ok' }), { status: 200 })));

    await auditsApi.phase1EnrichmentArtifacts('audit-1');
    await auditsApi.phase1EnrichmentPrompt('audit-1');
    await auditsApi.updatePhase1EnrichmentPrompt('audit-1', 'Custom recon prompt');
    await auditsApi.runPhase1Semgrep('audit-1');
    await auditsApi.runPhase1PromptEnrichment('audit-1');

    expect(global.fetch.mock.calls[0][0]).toBe('/api/audits/audit-1/phase-1-enrichment-artifacts');
    expect(global.fetch.mock.calls[1][0]).toBe('/api/audits/audit-1/phase-1-enrichment-prompt');
    expect(global.fetch.mock.calls[2][0]).toBe('/api/audits/audit-1/phase-1-enrichment-prompt');
    expect(global.fetch.mock.calls[2][1].method).toBe('PUT');
    expect(JSON.parse(global.fetch.mock.calls[2][1].body)).toEqual({ prompt: 'Custom recon prompt' });
    expect(global.fetch.mock.calls[3][0]).toBe('/api/audits/audit-1/phase-1-semgrep');
    expect(global.fetch.mock.calls[4][0]).toBe('/api/audits/audit-1/phase-1-prompt-enrich');
    expect(global.fetch.mock.calls.every(([, options]) => options.headers.Authorization === 'Bearer fresh-token')).toBe(true);
  });

  it('calls code-server APIs with auth headers', async () => {
    window.localStorage.setItem(authApi.tokenKey, 'fresh-token');
    global.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ running: false }), { status: 200 })));

    await auditsApi.codeServerStatus('audit-1');
    await auditsApi.startCodeServer('audit-1');
    await auditsApi.stopCodeServer('audit-1');

    expect(global.fetch.mock.calls[0][0]).toBe('/api/audits/audit-1/code-server/status');
    expect(global.fetch.mock.calls[1][0]).toBe('/api/audits/audit-1/code-server/start');
    expect(global.fetch.mock.calls[1][1].method).toBe('POST');
    expect(global.fetch.mock.calls[2][0]).toBe('/api/audits/audit-1/code-server/stop');
    expect(global.fetch.mock.calls[2][1].method).toBe('POST');
    expect(global.fetch.mock.calls.every(([, options]) => options.headers.Authorization === 'Bearer fresh-token')).toBe(true);
  });
});
