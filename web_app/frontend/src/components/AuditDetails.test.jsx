import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import AuditDetails from './AuditDetails';

const baseAudit = {
  id: 'audit-1',
  name: 'Question Audit',
  status: 'paused_for_questions',
  current_phase: 'phase-3',
  assigned_worker_id: 1,
  question_owner_user_id: 7,
  question_owner_name: 'AI Owner',
  question_owner_is_llm: true,
  workspace_path: '/work/audit-1',
  source_type: 'local',
  source_location: '/src.zip',
  has_codecome_yml: true,
  codecome_yml: 'project: demo',
  model_settings: {},
  ai_review_enabled: false,
  auto_continue: true,
  total_findings: 3,
  findings_by_status: {},
  created_at: '2026-01-01T00:00:00',
  updated_at: '2026-01-01T00:00:00',
  phase_executions: [
    { id: 10, audit_id: 'audit-1', phase: 'phase-1', attempt: 1, status: 'success', duration_seconds: 65 },
    { id: 11, audit_id: 'audit-1', phase: 'phase-2', attempt: 1, status: 'success', duration_seconds: 125 },
  ],
};

let auditPayload;

describe('AuditDetails', () => {
  beforeEach(() => {
    auditPayload = { ...baseAudit };
    global.fetch = vi.fn((url, options = {}) => {
      const requested = new URL(String(url), 'http://localhost');
      if (requested.pathname.includes('/api/audits/audit-1/report/download')) {
        return Promise.resolve(new Response('# Report\n', {
          status: 200,
          headers: { 'content-disposition': 'attachment; filename="report.md"' },
        }));
      }
      if (requested.pathname.includes('/api/audits/audit-1/gap-candidates/GAP-0001/mark')) {
        const body = JSON.parse(options.body || '{}');
        return Promise.resolve(new Response(JSON.stringify({ message: `Gap candidate marked as ${body.decision}` }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/audits/audit-1/gap-candidates')) {
        return Promise.resolve(new Response(JSON.stringify({
          audit_id: 'audit-1',
          total: 2,
          candidates: [
            { id: 'GAP-0001', title: 'Stack trace disclosure', category: 'Information Disclosure', decision: 'missing_sweep', action: 'sweep', severity_hint: 'LOW', files: ['src/EmployeeController.java'], matched_existing_findings: [], matched_notes: ['itemdb/notes/attack-surface.md:66'], match_confidence: 'NONE', comparison_rationale: 'Notes-only gap.', sweep_files: ['src/EmployeeController.java'] },
            { id: 'GAP-0002', title: 'Covered issue', category: 'Access Control', decision: 'covered', action: 'none', severity_hint: 'MEDIUM', files: ['src/AdminController.java'], matched_existing_findings: ['CC-0002 (CONFIRMED)'], sweep_files: [] },
          ],
        }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/audits/audit-1/gap-sweep')) {
        return Promise.resolve(new Response(JSON.stringify({ message: 'Gap sweep queued', phase: 'gap-sweep' }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/audits/audit-1/gap-scan')) {
        return Promise.resolve(new Response(JSON.stringify({ message: 'Gap scan queued', phase: 'gap-scan' }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/audits/audit-1/gap-compare')) {
        return Promise.resolve(new Response(JSON.stringify({ message: 'Gap compare queued', phase: 'gap-compare' }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/audits/audit-1/sandbox/start')) {
        return Promise.resolve(new Response(JSON.stringify({ command: './sandbox/scripts/up.sh', exit_code: 0, stdout: 'ok', stderr: '' }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/audits/audit-1')) {
        return Promise.resolve(new Response(JSON.stringify(auditPayload), { status: 200 }));
      }
      if (requested.pathname.includes('/api/questions')) {
        return Promise.resolve(new Response(JSON.stringify({
          total: 2,
          questions: [
            { id: 1, audit_id: 'audit-1', phase_execution_id: 1, phase: 'phase-3', question: 'Blocking?', status: 'OPEN', blocking: true, created_at: '2026-01-01T00:00:00' },
            { id: 2, audit_id: 'audit-1', phase_execution_id: 1, phase: 'phase-3', question: 'Answered?', status: 'ANSWERED', blocking: true, created_at: '2026-01-01T00:00:00' },
          ],
        }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/logs')) {
        return Promise.resolve(new Response(JSON.stringify({
          total: 0,
          logs: [],
          summary: { turns: 3, input_tokens: 1000, output_tokens: 200, reasoning_tokens: 50, total_tokens: 1250, models: {}, steps: {} },
        }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/phases')) {
        return Promise.resolve(new Response(JSON.stringify({ triages: [], findings: [], total: 0 }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/users')) {
        return Promise.resolve(new Response(JSON.stringify({ total: 0, users: [] }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: 'not found' }), { status: 404 }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows audit-level question counts in the header', async () => {
    render(
      <MemoryRouter initialEntries={['/audit/audit-1']}>
        <Routes>
          <Route path="/audit/:id" element={<AuditDetails />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText('Question Audit')).toBeInTheDocument();
    expect(await screen.findByText('Questions:')).toBeInTheDocument();
    expect(screen.getByText('Blocking:')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Refresh Questions' })).not.toBeInTheDocument();
    expect(screen.getByText('AI Owner (AI)')).toBeInTheDocument();
    expect(screen.queryByText('AI Review:')).not.toBeInTheDocument();
    expect(screen.getAllByText('1').length).toBeGreaterThan(0);
  });

  it('refreshes audit-level question counts on demand', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/audit/audit-1']}>
        <Routes>
          <Route path="/audit/:id" element={<AuditDetails />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText('Question Audit')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Questions' }));
    expect(await screen.findByRole('button', { name: 'Refresh Questions' })).toBeInTheDocument();
    const before = global.fetch.mock.calls.filter(([url]) => String(url).includes('/api/questions')).length;
    await user.click(screen.getByRole('button', { name: 'Refresh Questions' }));
    const after = global.fetch.mock.calls.filter(([url]) => String(url).includes('/api/questions')).length;

    expect(after).toBeGreaterThan(before);
  });

  it('shows answer questions instead of start when blocking questions are open', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/audit/audit-1']}>
        <Routes>
          <Route path="/audit/:id" element={<AuditDetails />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText('Question Audit')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Answer Questions' }));
    expect(screen.getByRole('button', { name: 'Questions' })).toHaveClass('bg-blue-600');
  });

  it('launches sandbox from audit overview', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/audit/audit-1']}>
        <Routes>
          <Route path="/audit/:id" element={<AuditDetails />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText('Question Audit')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Launch Sandbox' }));

    await waitFor(() => {
      const sandboxCall = global.fetch.mock.calls.find(([url, options]) => String(url).includes('/sandbox/start') && options?.method === 'POST');
      expect(sandboxCall).toBeTruthy();
    });
    expect(await screen.findByText(/Sandbox command finished with exit code 0/i)).toBeInTheDocument();
  });

  it('shows total runtime and token usage in overview', async () => {
    render(
      <MemoryRouter initialEntries={['/audit/audit-1']}>
        <Routes>
          <Route path="/audit/:id" element={<AuditDetails />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText('Total Runtime')).toBeInTheDocument();
    expect(screen.getByText('3m 10s')).toBeInTheDocument();
    expect(await screen.findByText('Total Tokens')).toBeInTheDocument();
    expect(screen.getByText('1,250')).toBeInTheDocument();
    expect(screen.getByText('LLM Turns')).toBeInTheDocument();
    expect(screen.getAllByText('3').length).toBeGreaterThan(0);
  });

  it('downloads the report from the reporting phase', async () => {
    const user = userEvent.setup();
    auditPayload = {
      ...baseAudit,
      status: 'phase_6_complete',
      current_phase: 'phase-6',
      phase_executions: [{ id: 99, audit_id: 'audit-1', phase: 'phase-6', attempt: 1, status: 'success', exit_code: 0 }],
    };
    Object.defineProperty(window.URL, 'createObjectURL', { value: vi.fn(() => 'blob:report'), configurable: true });
    Object.defineProperty(window.URL, 'revokeObjectURL', { value: vi.fn(), configurable: true });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    render(
      <MemoryRouter initialEntries={['/audit/audit-1']}>
        <Routes>
          <Route path="/audit/:id" element={<AuditDetails />} />
        </Routes>
      </MemoryRouter>
    );

    await user.click(await screen.findByRole('button', { name: 'Current Phase' }));
    expect(await screen.findByRole('button', { name: 'Download Report' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Download Report' }));

    expect(window.URL.createObjectURL).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    expect(await screen.findByText('Downloaded report.md.')).toBeInTheDocument();
  });

  it('shows the gap scan tab with candidate summary and warning', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/audit/audit-1']}>
        <Routes>
          <Route path="/audit/:id" element={<AuditDetails />} />
        </Routes>
      </MemoryRouter>
    );

    await user.click(await screen.findByRole('button', { name: 'Gap Scan' }));

    expect(await screen.findByRole('heading', { name: 'Gap Scan' })).toBeInTheDocument();
    expect(screen.getByText(/not confirmed vulnerabilities/i)).toBeInTheDocument();
    expect(screen.getByText('Candidates')).toBeInTheDocument();
    expect(screen.getAllByText('missing sweep').length).toBeGreaterThan(0);
    expect(screen.getByText('needs human')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run Gap Scan' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Compare Candidates' })).toBeInTheDocument();
    expect(screen.getByText('Candidate')).toBeInTheDocument();
    expect(screen.getByText('Stack trace disclosure')).toBeInTheDocument();
    expect(screen.getAllByText('src/EmployeeController.java').length).toBeGreaterThan(0);
    expect(screen.getByText('CC-0002 (CONFIRMED)')).toBeInTheDocument();
    expect(screen.getByText('Recommended Sweep')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Run Sweep' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: 'Ignore' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: 'Needs Human' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: 'Open Candidate Details' }).length).toBeGreaterThan(0);
    expect(screen.getAllByText('1').length).toBeGreaterThan(0);
  });

  it('queues a gap scan from the gap scan tab', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/audit/audit-1']}>
        <Routes>
          <Route path="/audit/:id" element={<AuditDetails />} />
        </Routes>
      </MemoryRouter>
    );

    await user.click(await screen.findByRole('button', { name: 'Gap Scan' }));
    await user.click(await screen.findByRole('button', { name: 'Run Gap Scan' }));

    await waitFor(() => {
      const call = global.fetch.mock.calls.find(([url, options]) => String(url).includes('/gap-scan') && options?.method === 'POST');
      expect(call).toBeTruthy();
    });
    expect(await screen.findByText('Gap scan queued')).toBeInTheDocument();
  });

  it('queues gap comparison from the gap scan tab', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/audit/audit-1']}>
        <Routes>
          <Route path="/audit/:id" element={<AuditDetails />} />
        </Routes>
      </MemoryRouter>
    );

    await user.click(await screen.findByRole('button', { name: 'Gap Scan' }));
    await user.click(await screen.findByRole('button', { name: 'Compare Candidates' }));

    await waitFor(() => {
      const call = global.fetch.mock.calls.find(([url, options]) => String(url).includes('/gap-compare') && options?.method === 'POST');
      expect(call).toBeTruthy();
    });
    expect(await screen.findByText('Gap compare queued')).toBeInTheDocument();
  });

  it('runs sweep, marks, and opens candidate details from the gap table', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/audit/audit-1']}>
        <Routes>
          <Route path="/audit/:id" element={<AuditDetails />} />
        </Routes>
      </MemoryRouter>
    );

    await user.click(await screen.findByRole('button', { name: 'Gap Scan' }));
    await user.click((await screen.findAllByRole('button', { name: 'Open Candidate Details' }))[0]);
    expect(await screen.findByText(/itemdb\/notes\/attack-surface.md:66/)).toBeInTheDocument();

    await user.click((await screen.findAllByRole('button', { name: 'Run Sweep' }))[0]);
    await waitFor(() => {
      const call = global.fetch.mock.calls.find(([url, options]) => String(url).includes('/gap-sweep?candidate=GAP-0001') && options?.method === 'POST');
      expect(call).toBeTruthy();
    });
    expect(await screen.findByText('Gap sweep queued')).toBeInTheDocument();

    await user.click((await screen.findAllByRole('button', { name: 'Ignore' }))[0]);
    await waitFor(() => {
      const call = global.fetch.mock.calls.find(([url, options]) => String(url).includes('/gap-candidates/GAP-0001/mark') && options?.method === 'POST');
      expect(call).toBeTruthy();
    });
    expect(await screen.findByText('Gap candidate marked as ignored')).toBeInTheDocument();
  });
});
