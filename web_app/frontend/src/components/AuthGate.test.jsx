import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AuthGate from './AuthGate';

describe('AuthGate', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('renders children when token resolves to current user', async () => {
    window.localStorage.setItem('codecome_access_token', 'token-123');
    global.fetch = vi.fn((url) => {
      if (String(url).includes('/api/auth/status')) {
        return Promise.resolve(new Response(JSON.stringify({ bootstrap_required: false }), { status: 200 }));
      }
      if (String(url).includes('/api/auth/me')) {
        return Promise.resolve(new Response(JSON.stringify({ id: 1, username: 'derek', display_name: 'Derek', is_llm_user: false, active: true, auto_answer_enabled: true, created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: 'not found' }), { status: 404 }));
    });

    render(<AuthGate><div>Protected App</div></AuthGate>);

    expect(await screen.findByText('Protected App')).toBeInTheDocument();
    expect(global.fetch.mock.calls.some(([url, options]) => String(url).includes('/api/auth/me') && options?.headers?.Authorization === 'Bearer token-123')).toBe(true);
  });

  it('shows bootstrap form before first user exists', async () => {
    global.fetch = vi.fn((url, options = {}) => {
      if (String(url).includes('/api/auth/status')) {
        return Promise.resolve(new Response(JSON.stringify({ bootstrap_required: true }), { status: 200 }));
      }
      if (String(url).includes('/api/auth/bootstrap')) {
        return Promise.resolve(new Response(JSON.stringify({ access_token: 'new-token', user: { id: 1, username: 'admin', display_name: 'admin', is_llm_user: false, active: true, auto_answer_enabled: true, created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' } }), { status: 201 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: 'not found' }), { status: 404 }));
    });
    const user = userEvent.setup();

    render(<AuthGate><div>Protected App</div></AuthGate>);

    expect(await screen.findByText('Create First User')).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText('username'), 'admin');
    await user.type(screen.getByPlaceholderText('password'), 'secret');
    await user.click(screen.getByRole('button', { name: 'Create User' }));

    expect(await screen.findByText('Protected App')).toBeInTheDocument();
    expect(window.localStorage.getItem('codecome_access_token')).toBe('new-token');
  });
});
