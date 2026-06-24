import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard';

vi.mock('../hooks/useAudits', () => ({
  useAudits: () => ({
    audits: [
      {
        id: 'audit-1',
        name: 'Demo Audit',
        status: 'ready',
        total_findings: 0,
        findings_by_status: {},
        created_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'audit-2',
        name: 'Production Review',
        status: 'completed',
        total_findings: 3,
        findings_by_status: { CONFIRMED: 1 },
        created_at: '2026-01-02T00:00:00Z',
      },
    ],
    total: 2,
    loading: false,
    refetch: vi.fn(),
  }),
}));

const deleteMock = vi.fn(() => Promise.resolve());
vi.mock('../services/api', () => ({
  auditsApi: {
    delete: (...args) => deleteMock(...args),
    start: vi.fn(() => Promise.resolve()),
    pause: vi.fn(() => Promise.resolve()),
  },
}));

describe('Dashboard', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('asks for confirmation before deleting an audit', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    await user.click(screen.getAllByRole('button', { name: 'Delete' })[0]);

    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('Demo Audit'));
    expect(deleteMock).not.toHaveBeenCalled();
  });

  it('deletes after confirmation', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    await user.click(screen.getAllByRole('button', { name: 'Delete' })[0]);

    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith('audit-1'));
  });

  it('filters the audit card list by name', async () => {
    const user = userEvent.setup();

    render(<MemoryRouter><Dashboard /></MemoryRouter>);
    await user.type(screen.getByPlaceholderText(/search by audit name/i), 'Production');

    expect(screen.getByText('Production Review')).toBeInTheDocument();
    expect(screen.queryByText('Demo Audit')).not.toBeInTheDocument();
  });
});
