import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Phase1EnrichmentPanel from './Phase1EnrichmentPanel';

const audit = { id: 'audit-1' };

describe('Phase1EnrichmentPanel', () => {
  beforeEach(() => {
    global.fetch = vi.fn((url, options = {}) => {
      const requested = new URL(String(url), 'http://localhost');
      if (requested.pathname.includes('/api/audits/audit-1/phase-1-enrichment-artifacts')) {
        return Promise.resolve(new Response(JSON.stringify({
          audit_id: 'audit-1',
          semgrep_summary: { total_results: 2, by_severity: { ERROR: 1, WARNING: 1 }, by_file: { 'src/app.php': 2 } },
          artifacts: [
            { path: 'itemdb/notes/semgrep-results.yml', exists: true },
            { path: 'itemdb/notes/file-risk-index.yml', exists: true },
            { path: 'runs/phase-1-enrichment-prompt.md', exists: false },
          ],
          run_summaries: ['phase-1-semgrep-2026-06-30-120000.md'],
        }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/audits/audit-1/phase-1-enrichment-prompt')) {
        return Promise.resolve(new Response(JSON.stringify({
          path: 'web_app/backend/data/preview-analysis.md',
          prompt: options.method === 'PUT' ? JSON.parse(options.body || '{}').prompt : 'Preview prompt',
          default_prompt: 'Preview prompt',
          custom: options.method === 'PUT',
          local_sync: 'runs/phase-1-enrichment-user-prompt.md',
        }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/audits/audit-1/phase-1-semgrep')) {
        return Promise.resolve(new Response(JSON.stringify({ message: 'Phase 1 Semgrep enrichment queued' }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/audits/audit-1/phase-1-prompt-enrich')) {
        return Promise.resolve(new Response(JSON.stringify({ message: 'Phase 1 prompt enrichment queued' }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: 'not found' }), { status: 404 }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows enrichment warning, summaries, artifacts, and run summaries', async () => {
    render(<Phase1EnrichmentPanel audit={audit} />);

    expect(await screen.findByText(/Phase 1 enrichment is optional/i)).toBeInTheDocument();
    expect(screen.getByText(/not confirmed vulnerabilities or findings/i)).toBeInTheDocument();
    expect(screen.getByText('Semgrep Results')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getAllByText('itemdb/notes/semgrep-results.yml').length).toBeGreaterThan(0);
    expect(screen.getByText('runs/phase-1-semgrep-2026-06-30-120000.md')).toBeInTheDocument();
  });

  it('saves the prompt and queues enrichment jobs', async () => {
    const user = userEvent.setup();
    render(<Phase1EnrichmentPanel audit={audit} />);

    expect(await screen.findByDisplayValue('Preview prompt')).toBeInTheDocument();
    await user.clear(screen.getByDisplayValue('Preview prompt'));
    await user.type(screen.getByPlaceholderText(/Preview Analysis prompt/i), 'Focus on authorization.');
    await user.click(screen.getByRole('button', { name: 'Save Prompt' }));
    expect(await screen.findByText('Phase 1 enrichment prompt saved.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Run Semgrep Enrichment' }));
    expect(await screen.findByText('Phase 1 Semgrep enrichment queued')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Run Prompt Enrichment' }));
    expect(await screen.findByText('Phase 1 prompt enrichment queued')).toBeInTheDocument();

    await waitFor(() => {
      const saveCall = global.fetch.mock.calls.find(([url, options]) => String(url).includes('/phase-1-enrichment-prompt') && options?.method === 'PUT');
      const semgrepCall = global.fetch.mock.calls.find(([url, options]) => String(url).includes('/phase-1-semgrep') && options?.method === 'POST');
      const promptCall = global.fetch.mock.calls.find(([url, options]) => String(url).includes('/phase-1-prompt-enrich') && options?.method === 'POST');
      expect(JSON.parse(saveCall[1].body).prompt).toBe('Focus on authorization.');
      expect(semgrepCall).toBeTruthy();
      expect(promptCall).toBeTruthy();
    });
  });
});
