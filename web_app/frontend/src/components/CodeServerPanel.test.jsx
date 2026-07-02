import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CodeServerPanel from './CodeServerPanel';

describe('CodeServerPanel', () => {
  beforeEach(() => {
    let running = false;
    global.fetch = vi.fn((url, options = {}) => {
      const requested = new URL(String(url), 'http://localhost');
      if (requested.pathname.includes('/code-server/status')) {
        return Promise.resolve(new Response(JSON.stringify(running ? { running: true, url: 'http://localhost:32123', password: 'pw', workspace_path: '/work/audit-1' } : { running: false }), { status: 200 }));
      }
      if (requested.pathname.includes('/code-server/start')) {
        running = true;
        return Promise.resolve(new Response(JSON.stringify({ running: true, url: 'http://localhost:32123', password: 'pw', workspace_path: '/work/audit-1' }), { status: 200 }));
      }
      if (requested.pathname.includes('/code-server/stop')) {
        running = false;
        return Promise.resolve(new Response(JSON.stringify({ running: false }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: 'not found' }), { status: 404 }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('starts and stops code-server for an audit workspace', async () => {
    const user = userEvent.setup();
    render(<CodeServerPanel auditId="audit-1" />);

    expect(await screen.findByText(/Start VS Code to inspect/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Start VS Code' }));
    expect(await screen.findByText('http://localhost:32123')).toBeInTheDocument();
    expect(screen.getByText('pw')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Stop' }));
    expect(await screen.findByText(/Start VS Code to inspect/i)).toBeInTheDocument();
  });
});
