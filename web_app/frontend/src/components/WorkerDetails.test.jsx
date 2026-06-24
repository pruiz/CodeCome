import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import WorkerDetails from './WorkerDetails';

describe('WorkerDetails', () => {
  beforeEach(() => {
    global.fetch = vi.fn((url) => {
      const requested = new URL(String(url), 'http://localhost');
      if (requested.pathname === '/api/workers/1') {
        return Promise.resolve(new Response(JSON.stringify({
          id: 1,
          name: 'local',
          type: 'local',
          status: 'idle',
          host: 'localhost',
          port: null,
          username: null,
          workspace_base_path: '/workspaces',
          max_concurrent_jobs: 1,
          current_jobs: 0,
          capabilities: {},
          config: {},
          created_at: '2026-01-01T00:00:00',
          updated_at: '2026-01-01T00:00:00',
        }), { status: 200 }));
      }
      if (requested.pathname === '/api/workers/1/checks') {
        return Promise.resolve(new Response(JSON.stringify({
          worker_id: 1,
          worker_name: 'local',
          source: 'live-local',
          checks: [{ key: 'opencode', label: 'OpenCode', required: true, ok: true, detail: 'installed' }],
        }), { status: 200 }));
      }
      if (requested.pathname === '/api/workers/1/models') {
        return Promise.resolve(new Response(JSON.stringify({
          total: 2,
          models: [
            { id: 'local/qwen3.6-27b', provider: 'local', model: 'qwen3.6-27b' },
            { id: 'openai/gpt-4.1', provider: 'openai', model: 'gpt-4.1' },
          ],
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: 'not found' }), { status: 404 }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows models discovered for the worker', async () => {
    render(
      <MemoryRouter initialEntries={['/workers/1']}>
        <Routes><Route path="/workers/:id" element={<WorkerDetails />} /></Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText('Available Models')).toBeInTheDocument();
    expect(await screen.findByText('local/qwen3.6-27b')).toBeInTheDocument();
    expect(screen.getByText('openai/gpt-4.1')).toBeInTheDocument();
    expect(screen.getByText('2 models')).toBeInTheDocument();
  });
});
