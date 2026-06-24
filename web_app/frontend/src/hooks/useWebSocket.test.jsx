import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { useWebSocket } from './useWebSocket';

function Harness() {
  useWebSocket('/ws/audits/audit-1/logs', () => {});
  return <div>ws</div>;
}

describe('useWebSocket', () => {
  let originalWebSocket;

  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem('codecome_access_token', 'token 123');
    originalWebSocket = global.WebSocket;
    global.WebSocket = vi.fn(function MockWebSocket(url) {
      this.url = url;
      this.close = vi.fn();
    });
  });

  afterEach(() => {
    cleanup();
    global.WebSocket = originalWebSocket;
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('adds auth token to websocket url', () => {
    render(<Harness />);

    expect(global.WebSocket).toHaveBeenCalledTimes(1);
    expect(global.WebSocket.mock.calls[0][0]).toContain('/ws/audits/audit-1/logs?token=token%20123');
  });
});
