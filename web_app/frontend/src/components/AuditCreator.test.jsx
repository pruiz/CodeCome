import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import AuditCreator from './AuditCreator';

const navigateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

describe('AuditCreator', () => {
  beforeEach(() => {
    navigateMock.mockClear();
    global.fetch = vi.fn((url, options = {}) => {
      const requested = new URL(String(url), 'http://localhost');
      if (requested.pathname.includes('/api/workers')) {
        return Promise.resolve(new Response(JSON.stringify({
          total: 1,
          workers: [{ id: 1, name: 'local', type: 'local', status: 'idle', current_jobs: 0, max_concurrent_jobs: 1, capabilities: {}, config: {}, created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' }],
        }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/users')) {
        return Promise.resolve(new Response(JSON.stringify({
          total: 1,
          users: [{ id: 7, username: 'ai-owner', display_name: 'AI Owner', is_llm_user: true, active: true, auto_answer_enabled: true, created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' }],
        }), { status: 200 }));
      }
      if (requested.pathname.includes('/api/audits') && options.method === 'POST') {
        return Promise.resolve(new Response(JSON.stringify({ id: 'audit-1' }), { status: 201 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: 'not found' }), { status: 404 }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('includes selected question owner in create payload', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><AuditCreator /></MemoryRouter>);

    await user.type(screen.getByPlaceholderText('/path/to/source/code'), '/opt/tools/08_TETools/SmallCompany.zip');
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.type(screen.getByPlaceholderText('My Audit'), 'Question Owner Audit');
    await screen.findByText('AI Owner (AI)');
    await user.selectOptions(screen.getByLabelText('Question Owner'), '7');
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.click(screen.getByRole('button', { name: 'Create Audit' }));

    await waitFor(() => {
      const createCall = global.fetch.mock.calls.find(([url, options]) => String(url).includes('/api/audits/') && options?.method === 'POST');
      expect(createCall).toBeTruthy();
      expect(JSON.parse(createCall[1].body)).toMatchObject({
        name: 'Question Owner Audit',
        question_owner_user_id: 7,
      });
    });
  });

  it('passes selected zip file and settings to upload API', async () => {
    const user = userEvent.setup();
    const { container } = render(<MemoryRouter><AuditCreator /></MemoryRouter>);
    const zipFile = new File(['zip-bytes'], 'SmallCompany.zip', { type: 'application/zip' });

    await user.click(screen.getByRole('radio', { name: 'Upload ZIP' }));
    await user.upload(container.querySelector('input[type="file"]'), zipFile);
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.type(screen.getByPlaceholderText('My Audit'), 'Zip Question Audit');
    await screen.findByText('AI Owner (AI)');
    await user.selectOptions(screen.getByLabelText('Question Owner'), '7');
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.click(screen.getByRole('button', { name: 'Create Audit' }));

    await waitFor(() => {
      const uploadCall = global.fetch.mock.calls.find(([url, options]) => String(url).includes('/api/audits/upload-zip') && options?.method === 'POST');
      expect(uploadCall).toBeTruthy();
      expect(uploadCall[1].body).toBeInstanceOf(FormData);
      expect(uploadCall[1].body.get('file')).toBe(zipFile);
      expect(uploadCall[1].body.get('name')).toBe('Zip Question Audit');
      expect(uploadCall[1].body.get('question_owner_user_id')).toBe('7');
    });
  });
});
