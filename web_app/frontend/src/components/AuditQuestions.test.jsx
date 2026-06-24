import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AuditQuestions from './AuditQuestions';

describe('AuditQuestions', () => {
  beforeEach(() => {
    global.fetch = vi.fn((url, options = {}) => {
      const requested = new URL(String(url), 'http://localhost');
      if (requested.pathname.endsWith('/answer')) {
        return Promise.resolve(new Response(JSON.stringify({ id: 1, status: 'ANSWERED' }), { status: 200 }));
      }
      if (requested.pathname.endsWith('/auto-answer')) {
        return Promise.resolve(new Response(JSON.stringify({ id: 1, status: 'AUTO_ANSWERED', answer: 'AI answer' }), { status: 200 }));
      }
      if (requested.pathname.endsWith('/dismiss')) {
        return Promise.resolve(new Response(JSON.stringify({ id: 1, status: 'DISMISSED' }), { status: 200 }));
      }
      if (requested.pathname.includes('/continue-after-questions')) {
        return Promise.resolve(new Response(JSON.stringify({ message: 'Audit continued after questions' }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        total: 1,
        questions: [{
          id: 1,
          audit_id: 'audit-1',
          phase_execution_id: 7,
          phase: 'phase-3',
          question: 'Should CC-0007 be rejected?',
          context: 'Phase 3 asked for user decision.',
          source: 'stdout',
          status: 'OPEN',
          blocking: true,
          created_at: '2026-06-24T11:01:00+00:00',
        }],
      }), { status: 200 }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('renders questions and saves an answer', async () => {
    const user = userEvent.setup();
    render(<AuditQuestions auditId="audit-1" />);

    expect(await screen.findByText('Should CC-0007 be rejected?')).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText(/answer this question/i), 'Reject it because source has schema.');
    await user.click(screen.getByRole('button', { name: 'Save Answer' }));

    await waitFor(() => {
      const answerCall = global.fetch.mock.calls.find(([url]) => String(url).includes('/answer'));
      expect(answerCall).toBeTruthy();
      expect(JSON.parse(answerCall[1].body)).toMatchObject({
        answer: 'Reject it because source has schema.',
        status: 'ANSWERED',
      });
    });
  });

  it('can request a fake AI answer', async () => {
    const user = userEvent.setup();
    render(<AuditQuestions auditId="audit-1" />);

    expect(await screen.findByText('Should CC-0007 be rejected?')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Ask Fake AI' }));

    await waitFor(() => {
      const autoAnswerCall = global.fetch.mock.calls.find(([url]) => String(url).includes('/auto-answer'));
      expect(autoAnswerCall).toBeTruthy();
    });
  });
});
