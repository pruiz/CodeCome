import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AuthStatus from './AuthStatus';

describe('AuthStatus', () => {
  beforeEach(() => {
    window.localStorage.clear();
    global.fetch = vi.fn((url, options = {}) => {
      if (String(url).includes('/api/auth/status')) {
        return Promise.resolve(new Response(JSON.stringify({ bootstrap_required: false }), { status: 200 }));
      }
      if (String(url).includes('/api/auth/login')) {
        return Promise.resolve(new Response(JSON.stringify({
          access_token: 'token-123',
          token_type: 'bearer',
          user: { id: 1, username: 'derek', display_name: 'Derek', is_llm_user: false, active: true, auto_answer_enabled: true, created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' },
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: 'not found' }), { status: 404 }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('logs in and stores token', async () => {
    const user = userEvent.setup();
    render(<AuthStatus />);

    await user.type(screen.getByPlaceholderText('username'), 'derek');
    await user.type(screen.getByPlaceholderText('password'), 'secret');
    await user.click(screen.getByRole('button', { name: 'Login' }));

    expect(await screen.findByText('Derek')).toBeInTheDocument();
    expect(window.localStorage.getItem('codecome_access_token')).toBe('token-123');

    await waitFor(() => {
      const loginCall = global.fetch.mock.calls.find(([url]) => String(url).includes('/api/auth/login'));
      expect(JSON.parse(loginCall[1].body)).toMatchObject({ username: 'derek', password: 'secret' });
    });
  });

  it('bootstraps the first human user when required', async () => {
    global.fetch = vi.fn((url, options = {}) => {
      if (String(url).includes('/api/auth/status')) {
        return Promise.resolve(new Response(JSON.stringify({ bootstrap_required: true }), { status: 200 }));
      }
      if (String(url).includes('/api/auth/bootstrap')) {
        return Promise.resolve(new Response(JSON.stringify({
          access_token: 'bootstrap-token',
          token_type: 'bearer',
          user: { id: 1, username: 'admin', display_name: 'admin', is_llm_user: false, active: true, auto_answer_enabled: true, created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' },
        }), { status: 201 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: 'not found' }), { status: 404 }));
    });
    const user = userEvent.setup();
    render(<AuthStatus />);

    expect(await screen.findByText('Create First User')).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText('username'), 'admin');
    await user.type(screen.getByPlaceholderText('password'), 'secret');
    await user.click(screen.getByRole('button', { name: 'Create User' }));

    expect(await screen.findByText('admin')).toBeInTheDocument();
    expect(window.localStorage.getItem('codecome_access_token')).toBe('bootstrap-token');
  });
});
