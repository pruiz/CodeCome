import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Settings from './Settings';

describe('Settings', () => {
  beforeEach(() => {
    global.fetch = vi.fn((url, options = {}) => {
      if (String(url).includes('/api/preview/config') && options.method === 'PUT') {
        return Promise.resolve(new Response(options.body, { status: 200 }));
      }
      if (String(url).includes('/api/preview/config')) {
        return Promise.resolve(new Response(JSON.stringify({ prompt: 'Default enrichment prompt', updated: false }), { status: 200 }));
      }
      if (String(url).includes('/api/settings/code-server') && options.method === 'PUT') {
        return Promise.resolve(new Response(options.body, { status: 200 }));
      }
      if (String(url).includes('/api/settings/code-server')) {
        return Promise.resolve(new Response(JSON.stringify({ bind_addr: '127.0.0.1', public_base_url: '', updated: false }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: 'not found' }), { status: 404 }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('edits code-server bind and public URL settings', async () => {
    const user = userEvent.setup();
    render(<Settings />);

    expect(await screen.findByText('Settings')).toBeInTheDocument();
    expect(await screen.findByDisplayValue('Default enrichment prompt')).toBeInTheDocument();
    await user.clear(screen.getByLabelText('Bind address'));
    await user.type(screen.getByLabelText('Bind address'), '0.0.0.0');
    await user.type(screen.getByLabelText('Public base URL'), 'http://server.local');
    await user.click(screen.getByRole('button', { name: 'Save Settings' }));

    await waitFor(() => {
      const saveCall = global.fetch.mock.calls.find(([url, options]) => String(url).includes('/api/settings/code-server') && options?.method === 'PUT');
      expect(saveCall).toBeTruthy();
      expect(JSON.parse(saveCall[1].body)).toMatchObject({ bind_addr: '0.0.0.0', public_base_url: 'http://server.local' });
    });
    expect(await screen.findByText(/Settings saved/i)).toBeInTheDocument();
  });

  it('edits the user prompt enrichment default prompt from config', async () => {
    const user = userEvent.setup();
    render(<Settings />);

    const prompt = await screen.findByDisplayValue('Default enrichment prompt');
    await user.clear(prompt);
    await user.type(prompt, 'New enrichment prompt');
    await user.click(screen.getByRole('button', { name: 'Save Prompt' }));

    await waitFor(() => {
      const saveCall = global.fetch.mock.calls.find(([url, options]) => String(url).includes('/api/preview/config') && options?.method === 'PUT');
      expect(saveCall).toBeTruthy();
      expect(JSON.parse(saveCall[1].body)).toEqual({ prompt: 'New enrichment prompt' });
    });
    expect(await screen.findByText(/User Prompt Enrichment prompt saved/i)).toBeInTheDocument();
  });
});
