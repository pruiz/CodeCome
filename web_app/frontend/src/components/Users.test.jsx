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
        return Promise.resolve(new Response(JSON.stringify({ id: 2, username: 'ai-owner', display_name: 'AI Owner Updated', is_llm_user: true, active: true, auto_answer_enabled: false, llm_model: 'local/new-model', llm_context: 'Updated context.', created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        total: 2,
        users: [
          { id: 1, username: 'human', display_name: 'Human Owner', is_llm_user: false, active: true, auto_answer_enabled: true, created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' },
          { id: 2, username: 'ai-owner', display_name: 'AI Owner', is_llm_user: true, active: true, auto_answer_enabled: true, llm_model: 'local/old-model', llm_context: 'Old context.', created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' },
        ],
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
    await user.type(screen.getAllByPlaceholderText('display name')[0], 'AI Reviewer');
    await user.type(screen.getByPlaceholderText(/AI model/i), 'local/qwen3.6-27b');
    await user.type(screen.getAllByPlaceholderText(/context\/persona/i)[0], 'Answer carefully.');
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

  it('requires a password for human users', async () => {
    const user = userEvent.setup();
    render(<Users />);

    expect(await screen.findByText('Human Owner')).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText('username'), 'new-human');
    await user.click(screen.getByLabelText('Fake AI user'));

    expect(screen.getByRole('button', { name: 'Create User' })).toBeDisabled();
    expect(global.fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0);
  });

  it('edits fake AI user model and context', async () => {
    const user = userEvent.setup();
    render(<Users />);

    expect(await screen.findByText('AI Owner')).toBeInTheDocument();
    const modelInput = screen.getByLabelText('AI model for ai-owner');
    await user.clear(modelInput);
    await user.type(modelInput, 'local/new-model');
    const contextInput = screen.getByLabelText('AI context for ai-owner');
    await user.clear(contextInput);
    await user.type(contextInput, 'Updated context.');
    await user.click(screen.getAllByLabelText('Auto-answer')[0]);
    await user.click(screen.getAllByRole('button', { name: 'Save User' })[1]);

    await waitFor(() => {
      const updateCall = global.fetch.mock.calls.find(([, options]) => options?.method === 'PATCH');
      expect(updateCall).toBeTruthy();
      expect(JSON.parse(updateCall[1].body)).toMatchObject({
        llm_model: 'local/new-model',
        llm_context: 'Updated context.',
        auto_answer_enabled: false,
      });
    });
  });
});
