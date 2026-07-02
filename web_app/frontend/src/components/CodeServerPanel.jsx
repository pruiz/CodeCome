import React, { useEffect, useState } from 'react';
import { auditsApi } from '../services/api';

export default function CodeServerPanel({ auditId }) {
  const [status, setStatus] = useState({ running: false });
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setStatus(await auditsApi.codeServerStatus(auditId));
    } catch (err) {
      setError(err.message || 'Failed to load VS Code status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [auditId]);

  const start = async () => {
    setAction('start');
    setError('');
    try {
      setStatus(await auditsApi.startCodeServer(auditId));
    } catch (err) {
      setError(err.message || 'Failed to start VS Code');
    } finally {
      setAction('');
    }
  };

  const stop = async () => {
    setAction('stop');
    setError('');
    try {
      setStatus(await auditsApi.stopCodeServer(auditId));
    } catch (err) {
      setError(err.message || 'Failed to stop VS Code');
    } finally {
      setAction('');
    }
  };

  return (
    <section className="space-y-4">
      <div className="rounded-xl border border-cyan-900/70 bg-cyan-950/30 p-4 text-sm text-cyan-100">
        Open this audit workspace with code-server on the web host. It uses the web-side synced workspace, so `itemdb/` and `runs/` artifacts are available after worker phases sync back. By default it binds to localhost; set `CODE_SERVER_BIND_ADDR` and `CODE_SERVER_PUBLIC_BASE_URL` for LAN/server access.
      </div>
      {error && <div className="rounded bg-red-950/40 px-3 py-2 text-sm text-red-200">{error}</div>}
      <div className="rounded-xl border border-gray-800 bg-gray-950 p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h3 className="text-xl font-semibold">VS Code Workspace</h3>
            <p className="mt-1 text-sm text-gray-500">Status: {loading ? 'loading...' : status.running ? 'running' : 'stopped'}</p>
            {status.workspace_path && <p className="mt-1 break-all font-mono text-xs text-gray-500">{status.workspace_path}</p>}
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={start} disabled={!!action || status.running} className="rounded bg-blue-700 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-600 disabled:cursor-not-allowed disabled:bg-gray-700">
              {action === 'start' ? 'Starting...' : 'Start VS Code'}
            </button>
            <button onClick={stop} disabled={!!action || !status.running} className="rounded bg-red-800 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-gray-700">
              {action === 'stop' ? 'Stopping...' : 'Stop'}
            </button>
            <button onClick={load} disabled={loading} className="rounded bg-gray-800 px-3 py-2 text-sm hover:bg-gray-700 disabled:opacity-50">Refresh</button>
          </div>
        </div>
        {status.running ? (
          <div className="space-y-3 rounded border border-gray-800 bg-gray-900 p-4">
            <div>
              <div className="text-xs uppercase tracking-wide text-gray-500">URL</div>
              <a href={status.url} target="_blank" rel="noreferrer" className="break-all text-cyan-300 hover:text-cyan-200">{status.url}</a>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-gray-500">Password</div>
              <code className="break-all text-amber-200">{status.password}</code>
            </div>
            <p className="text-xs text-gray-500">code-server is bound to localhost on the web host. Use the password above when prompted.</p>
            {status.bind_addr && <p className="text-xs text-gray-500">Bind address: <code>{status.bind_addr}</code></p>}
          </div>
        ) : (
          <div className="rounded border border-gray-800 bg-gray-900 p-6 text-sm text-gray-500">Start VS Code to inspect the audit workspace.</div>
        )}
      </div>
    </section>
  );
}
