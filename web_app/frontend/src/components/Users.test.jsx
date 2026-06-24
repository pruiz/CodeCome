import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Users from './Users';

describe('Users', () => {
  beforeEach(() => {
    global.fetch = vi.fn((url, options = {}) => {
      if (options.method === 'POST') {
        return Promise.resolve(new Response(JSON.stringify({ id: 2, username: 'ai-reviewer', display_name: 'AI Reviewer', is_llm_user: true, active: true, auto_answer_enabled: true, created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' }), { status: 201 }));
      }
      if (options.method === 'PATCH') {
        return Promise.resolve(new Response(JSON.stringify({ id: 1, username: 'human', display_name: 'Human', is_llm_user: false, active: false, auto_answer_enabled: true, created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        total: 1,
        users: [{ id: 1, username: 'human', display_name: 'Human Owner', is_llm_user: false, active: true, auto_answer_enabled: true, created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' }],
      }), { status: 200 }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('creates a fake AI user', async () => {
    const user = userEvent.setup();
    render(<Users />);

    expect(await screen.findByText('Human Owner')).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText('username'), 'ai-reviewer');
    await user.type(screen.getByPlaceholderText('display name'), 'AI Reviewer');
    await user.type(screen.getByPlaceholderText(/AI model/i), 'local/qwen3.6-27b');
    await user.type(screen.getByPlaceholderText(/context\/persona/i), 'Answer carefully.');
    await user.click(screen.getByRole('button', { name: 'Create User' }));

    await waitFor(() => {
      const createCall = global.fetch.mock.calls.find(([, options]) => options?.method === 'POST');
      expect(createCall).toBeTruthy();
      expect(JSON.parse(createCall[1].body)).toMatchObject({
        username: 'ai-reviewer',
        display_name: 'AI Reviewer',
        is_llm_user: true,
        llm_model: 'local/qwen3.6-27b',
        llm_context: 'Answer carefully.',
      });
    });
  });
});
