import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import AuditDetails from './AuditDetails';

const audit = {
  id: 'audit-1',
  name: 'Question Audit',
  status: 'paused_for_questions',
  current_phase: 'phase-3',
  assigned_worker_id: 1,
  question_owner_user_id: 7,
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
  phase_executions: [],
};

describe('AuditDetails', () => {
  beforeEach(() => {
    global.fetch = vi.fn((url) => {
      const requested = new URL(String(url), 'http://localhost');
      if (requested.pathname.includes('/api/audits/audit-1')) {
        return Promise.resolve(new Response(JSON.stringify(audit), { status: 200 }));
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
    expect(screen.getAllByText('1').length).toBeGreaterThan(0);
  });
});
