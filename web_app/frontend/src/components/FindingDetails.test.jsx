import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import FindingDetails from './FindingDetails';

const finding = {
  id: 'CC-0001',
  audit_id: 'audit-1',
  title: 'Command injection in RCE endpoint',
  status: 'PENDING',
  severity: 'HIGH',
  confidence: 'MEDIUM',
  category: 'RCE',
  file_path: 'src/App.java',
  frontmatter: {
    cwe: ['CWE-78'],
    created_at: '2026-06-20T10:00:00Z',
    updated_at: '2026-06-21T11:00:00Z',
    files: ['src/App.java'],
    entry_points: ['GET /rce'],
    symbols: ['RceController.exec'],
    trust_boundary: 'HTTP user -> shell',
    validation: { status: 'NOT_STARTED', summary: 'Very long validation summary that should remain visible through a scrollable timeline card instead of being clipped out of view.' },
    exploitation: { status: 'NOT_STARTED', artifacts_dir: 'itemdb/evidence/CC-0001/exploits' },
  },
  content: '# Summary\n\nDangerous command execution.',
  has_evidence: true,
  has_exploit: false,
  created_at: '2026-06-20T10:00:00Z',
  updated_at: '2026-06-21T11:00:00Z',
};

describe('FindingDetails', () => {
  beforeEach(() => {
    global.fetch = vi.fn((url, options = {}) => {
      if (options.method === 'PATCH') {
        return Promise.resolve(new Response(JSON.stringify({ ...finding, status: 'CONFIRMED', severity: 'CRITICAL', confidence: 'CONFIRMED' }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify(finding), { status: 200 }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('renders markdown and saves manual review metadata', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/audit/audit-1/findings/CC-0001']}>
        <Routes>
          <Route path="/audit/:auditId/findings/:findingId" element={<FindingDetails />} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText('Command injection in RCE endpoint')).toBeInTheDocument();
    expect(screen.getByText('Dangerous command execution.')).toBeInTheDocument();
    expect(screen.getByText('Finding Timeline')).toBeInTheDocument();
    expect(screen.getByText('Hypothesis')).toBeInTheDocument();
    expect(screen.getByText('Counter-analysis')).toBeInTheDocument();
    expect(screen.getByText('Validation')).toBeInTheDocument();
    expect(screen.getByText(/Very long validation summary/)).toHaveClass('overflow-y-auto');
    expect(screen.getByText('Exploitation')).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('Status'), 'CONFIRMED');
    await user.selectOptions(screen.getByLabelText('Severity'), 'CRITICAL');
    await user.selectOptions(screen.getByLabelText('Confidence'), 'CONFIRMED');
    await user.type(screen.getByLabelText('Reviewer Note'), 'confirmed manually');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      const patchCall = global.fetch.mock.calls.find(([, options]) => options?.method === 'PATCH');
      expect(patchCall).toBeTruthy();
      expect(JSON.parse(patchCall[1].body)).toMatchObject({
        status: 'CONFIRMED',
        severity: 'CRITICAL',
        confidence: 'CONFIRMED',
        reviewer_note: 'confirmed manually',
      });
    });
  });
});
