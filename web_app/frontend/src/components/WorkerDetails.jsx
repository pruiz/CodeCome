import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { workersApi } from '../services/api';

function CheckRow({ check }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-gray-800 bg-gray-900 p-4">
      <div>
        <div className="flex items-center gap-2">
          <span className={check.ok ? 'text-green-300' : check.required ? 'text-red-300' : 'text-yellow-300'}>
            {check.ok ? 'OK' : check.required ? 'Missing' : 'Optional'}
          </span>
          <h3 className="font-semibold">{check.label}</h3>
          {!check.required && <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400">optional</span>}
        </div>
        <p className="mt-1 text-sm text-gray-400">{check.detail || 'No detail'}</p>
      </div>
      <div className={`h-3 w-3 rounded-full ${check.ok ? 'bg-green-400' : check.required ? 'bg-red-400' : 'bg-yellow-400'}`} />
    </div>
  );
}

export default function WorkerDetails() {
  const { id } = useParams();
  const [worker, setWorker] = useState(null);
  const [checks, setChecks] = useState(null);
  const [models, setModels] = useState(null);
  const [form, setForm] = useState(null);
  const [error, setError] = useState('');
  const [saveMessage, setSaveMessage] = useState('');
  const [credentialForm, setCredentialForm] = useState({
    method: 'key',
    password: '',
    private_key: '',
    passphrase: '',
  });
  const [credentialMessage, setCredentialMessage] = useState('');
  const [savingCredentials, setSavingCredentials] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setError('');
    setLoading(true);
    try {
      const [workerData, checkData, modelData] = await Promise.all([
        workersApi.get(id),
        workersApi.checks(id),
        workersApi.models(id),
      ]);
      setWorker(workerData);
      setForm({
        name: workerData.name || '',
        host: workerData.host || '',
        port: workerData.port ? String(workerData.port) : '',
        username: workerData.username || '',
        workspace_base_path: workerData.workspace_base_path || '',
        max_concurrent_jobs: String(workerData.max_concurrent_jobs || 1),
        status: workerData.status || 'idle',
      });
      setChecks(checkData);
      setModels(modelData);
      setCredentialForm({
        method: workerData.config?.ssh_auth?.method || 'key',
        password: '',
        private_key: '',
        passphrase: '',
      });
    } catch (err) {
      setError(err.message || 'Failed to load worker');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [id]);

  if (loading) return <div className="text-gray-400">Loading worker...</div>;
  if (error) return <div className="rounded bg-red-500/20 p-4 text-red-300">{error}</div>;
  if (!worker) return <div className="text-gray-400">Worker not found.</div>;

  const allRequiredOk = (checks?.checks || []).filter((check) => check.required).every((check) => check.ok);
  const isLocalWorker = worker.type === 'local';

  const saveWorker = async () => {
    setSaving(true);
    setSaveMessage('');
    try {
      const updated = await workersApi.update(worker.id, {
        name: form.name,
        host: form.host || null,
        port: form.port ? Number(form.port) : null,
        username: form.username || null,
        workspace_base_path: form.workspace_base_path || null,
        max_concurrent_jobs: Number(form.max_concurrent_jobs || 1),
        status: form.status,
      });
      setWorker(updated);
      setSaveMessage('Worker settings saved. New audit assignments will use the updated workspace path.');
    } catch (err) {
      setSaveMessage(`Save failed: ${err.message || 'Unknown error'}`);
    } finally {
      setSaving(false);
    }
  };

  const saveCredentials = async () => {
    setSavingCredentials(true);
    setCredentialMessage('');
    try {
      const sshAuth = { method: credentialForm.method };
      if (credentialForm.method === 'password' && credentialForm.password) {
        sshAuth.password = credentialForm.password;
      }
      if (credentialForm.method === 'key') {
        if (credentialForm.private_key) sshAuth.private_key = credentialForm.private_key;
        if (credentialForm.passphrase) sshAuth.passphrase = credentialForm.passphrase;
      }
      const updated = await workersApi.update(worker.id, {
        config: {
          ...(worker.config || {}),
          ssh_auth: sshAuth,
        }
      });
      setWorker(updated);
      setCredentialForm({ ...credentialForm, password: '', private_key: '', passphrase: '' });
      setCredentialMessage('SSH credentials saved. Secrets are stored server-side and are not shown again.');
    } catch (err) {
      setCredentialMessage(`Credential save failed: ${err.message || 'Unknown error'}`);
    } finally {
      setSavingCredentials(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link to="/workers" className="text-sm text-blue-300 hover:text-blue-200">Back to Workers</Link>
          <h2 className="mt-2 text-3xl font-bold">{worker.name}</h2>
          <p className="mt-1 text-gray-400">
            {isLocalWorker ? 'Local CodeCome worker running on this web host' : `${worker.type} worker on ${worker.host || 'unknown host'}`}
          </p>
        </div>
        <button onClick={load} className="rounded bg-gray-800 px-3 py-2 text-sm hover:bg-gray-700">Refresh Checks</button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <div className="text-xs uppercase tracking-wide text-gray-500">Status</div>
          <div className="mt-1 text-lg font-semibold">{worker.status}</div>
        </div>
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <div className="text-xs uppercase tracking-wide text-gray-500">Capacity</div>
          <div className="mt-1 text-lg font-semibold">{worker.current_jobs}/{worker.max_concurrent_jobs}</div>
        </div>
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <div className="text-xs uppercase tracking-wide text-gray-500">Workspace</div>
          <div className="mt-1 truncate text-sm">{worker.workspace_base_path || '-'}</div>
        </div>
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <div className="text-xs uppercase tracking-wide text-gray-500">Readiness</div>
          <div className={`mt-1 text-lg font-semibold ${allRequiredOk ? 'text-green-300' : 'text-red-300'}`}>
            {allRequiredOk ? 'Ready' : 'Missing required'}
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-cyan-900/60 bg-cyan-950/20 p-5">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-xl font-semibold text-cyan-100">Available Models</h3>
            <p className="mt-1 text-sm text-gray-400">
              Models discovered from this worker's OpenCode configuration. These are used by audit creation when this worker is selected.
            </p>
          </div>
          <span className="rounded bg-gray-900 px-2 py-1 text-xs text-gray-300">{models?.total ?? 0} models</span>
        </div>

        {models?.models?.length ? (
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {models.models.map((model) => (
              <div key={model.id} className="rounded border border-gray-800 bg-gray-950 px-3 py-2">
                <div className="font-mono text-sm text-cyan-100">{model.id}</div>
                <div className="mt-1 text-xs text-gray-500">Provider: {model.provider} · Model: {model.model}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-yellow-700/50 bg-yellow-500/10 p-4 text-yellow-200">
            No models were discovered for this worker. Check the worker's OpenCode config and SSH credentials for remote workers.
          </div>
        )}
      </div>

      <div className="rounded-xl border border-blue-900/60 bg-blue-950/20 p-5">
        <h3 className="text-lg font-semibold text-blue-200">Execution Identity</h3>
        <div className="mt-3 grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
          <div><span className="text-gray-500">Worker type:</span> {worker.type}</div>
          <div><span className="text-gray-500">Runs CodeCome on:</span> {isLocalWorker ? 'this web host (local)' : (worker.host || 'remote host')}</div>
          <div><span className="text-gray-500">Connection user:</span> {worker.username || (isLocalWorker ? 'current web process user' : '-')}</div>
          <div><span className="text-gray-500">Checks source:</span> {checks?.source || 'unknown'}</div>
        </div>
        <p className="mt-3 text-xs text-gray-400">
          A local worker means FastAPI/Celery runs `make phase-X` directly on this machine. Remote workers will run CodeCome on the registered VM/LXC/physical host once the SSH adapter is enabled.
        </p>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-950 p-5">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-xl font-semibold">Worker Settings</h3>
            <p className="mt-1 text-sm text-gray-400">
              Change the workspace path or connection details for this worker. For remote workers, make sure the directory exists on the worker host.
            </p>
          </div>
          <button
            onClick={saveWorker}
            disabled={saving || !form}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold hover:bg-blue-500 disabled:bg-gray-700"
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>

        {saveMessage && <div className="mb-4 rounded bg-gray-900 px-3 py-2 text-sm text-gray-200">{saveMessage}</div>}

        {form && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm text-gray-400">Name</label>
              <input
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                className="w-full rounded border border-gray-800 bg-gray-900 px-3 py-2"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-gray-400">Status</label>
              <select
                value={form.status}
                onChange={(event) => setForm({ ...form, status: event.target.value })}
                className="w-full rounded border border-gray-800 bg-gray-900 px-3 py-2"
              >
                <option value="idle">idle</option>
                <option value="running">running</option>
                <option value="offline">offline</option>
                <option value="error">error</option>
                <option value="disabled">disabled</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm text-gray-400">Host / IP</label>
              <input
                value={form.host}
                onChange={(event) => setForm({ ...form, host: event.target.value })}
                className="w-full rounded border border-gray-800 bg-gray-900 px-3 py-2"
                placeholder="localhost or 192.168.1.50"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-gray-400">SSH Port</label>
              <input
                value={form.port}
                onChange={(event) => setForm({ ...form, port: event.target.value })}
                className="w-full rounded border border-gray-800 bg-gray-900 px-3 py-2"
                placeholder="22"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-gray-400">SSH Username</label>
              <input
                value={form.username}
                onChange={(event) => setForm({ ...form, username: event.target.value })}
                className="w-full rounded border border-gray-800 bg-gray-900 px-3 py-2"
                placeholder="codecome"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-gray-400">Max Concurrent Jobs</label>
              <input
                type="number"
                min="1"
                max="64"
                value={form.max_concurrent_jobs}
                onChange={(event) => setForm({ ...form, max_concurrent_jobs: event.target.value })}
                className="w-full rounded border border-gray-800 bg-gray-900 px-3 py-2"
              />
            </div>
            <div className="md:col-span-2">
              <label className="mb-1 block text-sm text-gray-400">Workspace Base Path</label>
              <input
                value={form.workspace_base_path}
                onChange={(event) => setForm({ ...form, workspace_base_path: event.target.value })}
                className="w-full rounded border border-gray-800 bg-gray-900 px-3 py-2 font-mono text-sm"
                placeholder="/srv/codecome/workspaces"
              />
              <p className="mt-1 text-xs text-gray-500">
                Existing audit workspaces are not moved automatically. This path is used for new assignments and remote worker setup.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-950 p-5">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-xl font-semibold">SSH Credentials</h3>
            <p className="mt-1 text-sm text-gray-400">
              Used by the web app when the SSH worker adapter connects to this worker. Secrets are redacted after saving.
            </p>
          </div>
          <button
            onClick={saveCredentials}
            disabled={savingCredentials}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold hover:bg-blue-500 disabled:bg-gray-700"
          >
            {savingCredentials ? 'Saving...' : 'Save Credentials'}
          </button>
        </div>

        {credentialMessage && <div className="mb-4 rounded bg-gray-900 px-3 py-2 text-sm text-gray-200">{credentialMessage}</div>}

        <div className="mb-3 text-sm text-gray-400">
          Saved: password {worker.config?.ssh_auth?.has_password ? 'yes' : 'no'}, private key {worker.config?.ssh_auth?.has_private_key ? 'yes' : 'no'}, passphrase {worker.config?.ssh_auth?.has_passphrase ? 'yes' : 'no'}
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm text-gray-400">Auth Method</label>
            <select
              value={credentialForm.method}
              onChange={(event) => setCredentialForm({ ...credentialForm, method: event.target.value })}
              className="w-full rounded border border-gray-800 bg-gray-900 px-3 py-2"
            >
              <option value="key">Private key</option>
              <option value="password">Password</option>
            </select>
          </div>

          {credentialForm.method === 'password' ? (
            <div>
              <label className="mb-1 block text-sm text-gray-400">SSH Password</label>
              <input
                type="password"
                value={credentialForm.password}
                onChange={(event) => setCredentialForm({ ...credentialForm, password: event.target.value })}
                className="w-full rounded border border-gray-800 bg-gray-900 px-3 py-2"
                placeholder="Leave blank to keep existing password"
              />
            </div>
          ) : (
            <>
              <div className="md:col-span-2">
                <label className="mb-1 block text-sm text-gray-400">SSH Private Key</label>
                <textarea
                  value={credentialForm.private_key}
                  onChange={(event) => setCredentialForm({ ...credentialForm, private_key: event.target.value })}
                  className="h-36 w-full rounded border border-gray-800 bg-gray-900 px-3 py-2 font-mono text-xs"
                  placeholder="Leave blank to keep existing key"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm text-gray-400">Private Key Passphrase</label>
                <input
                  type="password"
                  value={credentialForm.passphrase}
                  onChange={(event) => setCredentialForm({ ...credentialForm, passphrase: event.target.value })}
                  className="w-full rounded border border-gray-800 bg-gray-900 px-3 py-2"
                  placeholder="Leave blank to keep existing passphrase"
                />
              </div>
            </>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-950 p-5">
        <div className="mb-4 flex items-center justify-between gap-4">
          <div>
            <h3 className="text-xl font-semibold">CodeCome Requirements</h3>
            <p className="mt-1 text-sm text-gray-400">
              Source: {checks?.source || 'unknown'}. Required checks must pass for reliable audit execution.
            </p>
          </div>
        </div>

        {checks?.checks?.length ? (
          <div className="space-y-3">
            {checks.checks.map((check) => <CheckRow key={check.key} check={check} />)}
          </div>
        ) : (
          <div className="rounded-lg border border-yellow-700/50 bg-yellow-500/10 p-4 text-yellow-200">
            No requirement metadata reported for this worker yet. Run the bootstrap script and register the worker using the generated command.
          </div>
        )}
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h3 className="font-semibold">Worker Metadata</h3>
        <p className="mt-1 text-sm text-gray-400">
          Bootstrap and runner metadata stored for this worker. Remote workers use this for reported prerequisite checks and adapter settings.
        </p>
        <details className="mt-3">
          <summary className="cursor-pointer text-sm text-blue-300 hover:text-blue-200">Show raw JSON</summary>
          <pre className="mt-3 overflow-x-auto rounded bg-gray-950 p-3 text-xs text-gray-300">{JSON.stringify(worker.config || {}, null, 2)}</pre>
        </details>
      </div>
    </div>
  );
}
