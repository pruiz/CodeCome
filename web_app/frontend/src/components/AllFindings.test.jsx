import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import AllFindings from './AllFindings';

describe('AllFindings', () => {
  beforeEach(() => {
    global.fetch = vi.fn((url) => {
      const requested = new URL(String(url), 'http://localhost');
      const status = requested.searchParams.get('status');
      const severity = requested.searchParams.get('severity');
      const findings = [{
        id: 'CC-0001',
        audit_id: 'audit-1',
        audit_name: 'Audit One',
        title: 'Command injection in RCE endpoint',
        status: status || 'PENDING',
        severity: severity || 'CRITICAL',
        category: 'RCE',
        file_path: 'src/App.java',
      }, {
        id: 'CC-0002',
        audit_id: 'audit-2',
        audit_name: 'Audit Two',
        title: 'Path traversal in file download',
        status: status || 'PENDING',
        severity: severity || 'HIGH',
        category: 'Traversal',
        file_path: 'src/files.py',
      }];
      return Promise.resolve(new Response(JSON.stringify({ total: findings.length, findings }), { status: 200 }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('renders global findings and links to the audit finding page', async () => {
    render(<MemoryRouter><AllFindings /></MemoryRouter>);

    expect(await screen.findByText('Command injection in RCE endpoint')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /CC-0001/i })).toHaveAttribute('href', '/audit/audit-1/findings/CC-0001');
  });

  it('applies status and severity filters via API query params', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><AllFindings /></MemoryRouter>);
    await screen.findByText('Command injection in RCE endpoint');

    await user.click(screen.getAllByRole('button', { name: 'CONFIRMED' })[0]);
    await user.click(screen.getAllByRole('button', { name: 'HIGH' })[0]);

    await waitFor(() => {
      const urls = global.fetch.mock.calls.map(([url]) => String(url));
      expect(urls.some((url) => url.includes('status=CONFIRMED'))).toBe(true);
      expect(urls.some((url) => url.includes('severity=HIGH'))).toBe(true);
    });
  });

  it('filters findings by audit text search', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><AllFindings /></MemoryRouter>);
    await screen.findByText('Command injection in RCE endpoint');

    await user.type(screen.getByPlaceholderText(/search audit name/i), 'Audit Two');

    expect(await screen.findByText('Path traversal in file download')).toBeInTheDocument();
    expect(screen.queryByText('Command injection in RCE endpoint')).not.toBeInTheDocument();
  });
});
