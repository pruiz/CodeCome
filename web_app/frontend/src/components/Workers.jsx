import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { workersApi } from '../services/api';

const workerTypes = [
  { value: 'local', label: 'Local' },
  { value: 'ssh', label: 'SSH / Remote machine' },
  { value: 'proxmox-vm', label: 'Proxmox VM' },
  { value: 'proxmox-lxc', label: 'Proxmox LXC' },
];

function Badge({ children, color = 'gray' }) {
  const colors = {
    gray: 'bg-gray-500/20 text-gray-300',
    green: 'bg-green-500/20 text-green-300',
    blue: 'bg-blue-500/20 text-blue-300',
    yellow: 'bg-yellow-500/20 text-yellow-300',
    red: 'bg-red-500/20 text-red-300',
    purple: 'bg-purple-500/20 text-purple-300',
  };
  return <span className={`px-2 py-1 rounded-full text-xs font-semibold ${colors[color] || colors.gray}`}>{children}</span>;
}

function statusColor(status) {
  if (status === 'idle') return 'green';
  if (status === 'running') return 'blue';
  if (status === 'offline') return 'yellow';
  if (status === 'error') return 'red';
  if (status === 'disabled') return 'gray';
  return 'gray';
}

function WorkerCard({ worker, onDelete, onDisable, onEnable }) {
  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4 shadow-lg shadow-black/20">
      <div className="flex items-start justify-between gap-3">
        <div>
          <Link to={`/workers/${worker.id}`} className="text-lg font-semibold text-blue-300 hover:text-blue-200">
            {worker.name}
          </Link>
          <div className="flex gap-2 mt-2">
            <Badge color="purple">{worker.type}</Badge>
            <Badge color={statusColor(worker.status)}>{worker.status}</Badge>
          </div>
        </div>
        <div className="text-right text-sm text-gray-400">
          <div>{worker.current_jobs}/{worker.max_concurrent_jobs} jobs</div>
          <div>ID {worker.id}</div>
        </div>
      </div>

      <div className="mt-4 space-y-1 text-sm">
        <div><span className="text-gray-500">Host:</span> {worker.host || 'local'}</div>
        <div><span className="text-gray-500">User:</span> {worker.username || '-'}</div>
        <div><span className="text-gray-500">Workspace:</span> {worker.workspace_base_path || '-'}</div>
      </div>

      <div className="mt-4 flex gap-2">
        {worker.status === 'disabled' ? (
          <button onClick={() => onEnable(worker.id)} className="px-3 py-1 bg-green-600 hover:bg-green-500 rounded text-sm">
            Enable
          </button>
        ) : (
          <button onClick={() => onDisable(worker.id)} className="px-3 py-1 bg-yellow-600 hover:bg-yellow-500 rounded text-sm">
            Disable
          </button>
        )}
        {worker.current_jobs === 0 && worker.name !== 'local' && (
          <button onClick={() => onDelete(worker.id)} className="px-3 py-1 bg-red-600 hover:bg-red-500 rounded text-sm">
            Delete
          </button>
        )}
        <Link to={`/workers/${worker.id}`} className="px-3 py-1 bg-gray-800 hover:bg-gray-700 rounded text-sm">
          Details
        </Link>
      </div>
    </div>
  );
}

function RegisterWorkerForm({ onCreated }) {
  const [form, setForm] = useState({
    name: '',
    type: 'ssh',
    host: '',
    port: '22',
    username: 'codecome',
    workspace_base_path: '/srv/codecome/workspaces',
    max_concurrent_jobs: '1',
    auth_method: 'key',
    ssh_password: '',
    ssh_private_key: '',
    ssh_passphrase: '',
  });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setSaving(true);
    try {
      await workersApi.create({
        name: form.name,
        type: form.type,
        host: form.host || null,
        port: form.port ? Number(form.port) : null,
        username: form.username || null,
        workspace_base_path: form.workspace_base_path || null,
        max_concurrent_jobs: Number(form.max_concurrent_jobs || 1),
        capabilities: { docker: true, codecome: true },
        config: {
          ssh_auth: {
            method: form.auth_method,
            password: form.auth_method === 'password' ? form.ssh_password : undefined,
            private_key: form.auth_method === 'key' ? form.ssh_private_key : undefined,
            passphrase: form.auth_method === 'key' ? form.ssh_passphrase : undefined,
          }
        },
      });
      setForm({ ...form, name: '', host: '', ssh_password: '', ssh_private_key: '', ssh_passphrase: '' });
      onCreated();
    } catch (err) {
      setError(err.message || 'Failed to create worker');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-4">
      <h3 className="text-lg font-semibold">Register Worker</h3>
      {error && <div className="bg-red-500/20 text-red-300 px-3 py-2 rounded text-sm">{error}</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="block text-sm text-gray-400 mb-1">Name</label>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required className="w-full bg-gray-800 px-3 py-2 rounded border border-gray-700" placeholder="runner-01" />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Type</label>
          <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="w-full bg-gray-800 px-3 py-2 rounded border border-gray-700">
            {workerTypes.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Host / IP</label>
          <input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} className="w-full bg-gray-800 px-3 py-2 rounded border border-gray-700" placeholder="192.168.1.50" />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">SSH Port</label>
          <input value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} className="w-full bg-gray-800 px-3 py-2 rounded border border-gray-700" />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">SSH Username</label>
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="w-full bg-gray-800 px-3 py-2 rounded border border-gray-700" />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Max Concurrent Jobs</label>
          <input type="number" min="1" max="64" value={form.max_concurrent_jobs} onChange={(e) => setForm({ ...form, max_concurrent_jobs: e.target.value })} className="w-full bg-gray-800 px-3 py-2 rounded border border-gray-700" />
        </div>
        <div className="md:col-span-2">
          <label className="block text-sm text-gray-400 mb-1">Workspace Base Path</label>
          <input value={form.workspace_base_path} onChange={(e) => setForm({ ...form, workspace_base_path: e.target.value })} className="w-full bg-gray-800 px-3 py-2 rounded border border-gray-700" />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">SSH Auth Method</label>
          <select value={form.auth_method} onChange={(e) => setForm({ ...form, auth_method: e.target.value })} className="w-full bg-gray-800 px-3 py-2 rounded border border-gray-700">
            <option value="key">Private key</option>
            <option value="password">Password</option>
          </select>
        </div>
        {form.auth_method === 'password' ? (
          <div>
            <label className="block text-sm text-gray-400 mb-1">SSH Password</label>
            <input type="password" value={form.ssh_password} onChange={(e) => setForm({ ...form, ssh_password: e.target.value })} className="w-full bg-gray-800 px-3 py-2 rounded border border-gray-700" placeholder="Stored server-side, not shown after save" />
          </div>
        ) : (
          <>
            <div className="md:col-span-2">
              <label className="block text-sm text-gray-400 mb-1">SSH Private Key</label>
              <textarea value={form.ssh_private_key} onChange={(e) => setForm({ ...form, ssh_private_key: e.target.value })} className="w-full h-32 bg-gray-800 px-3 py-2 rounded border border-gray-700 font-mono text-xs" placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Private Key Passphrase</label>
              <input type="password" value={form.ssh_passphrase} onChange={(e) => setForm({ ...form, ssh_passphrase: e.target.value })} className="w-full bg-gray-800 px-3 py-2 rounded border border-gray-700" placeholder="Optional" />
            </div>
          </>
        )}
      </div>

      <button disabled={saving} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 rounded font-semibold">
        {saving ? 'Saving...' : 'Register Worker'}
      </button>
    </form>
  );
}

function OpenCodeConfigPanel() {
  const defaultTemplate = `{
  // Paste your OpenCode config for worker machines here.
  // This is served at /api/workers/opencode-config/raw and pulled by bootstrap.
  // Include your custom providers, model aliases, auth config, etc.
}`;
  const [content, setContent] = useState(defaultTemplate);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    workersApi.getOpenCodeConfig()
      .then((data) => {
        if (data.updated && data.content) setContent(data.content);
        setLoaded(true);
      })
      .catch((error) => {
        setMessage(`Could not load saved config: ${error.message}`);
        setLoaded(true);
      });
  }, []);

  const save = async () => {
    setSaving(true);
    setMessage('');
    try {
      await workersApi.updateOpenCodeConfig(content);
      setMessage('OpenCode config saved. New workers will pull this during bootstrap.');
    } catch (error) {
      setMessage(`Save failed: ${error.message}`);
    } finally {
      setSaving(false);
    }
  };

  const rawUrl = `${window.location.protocol}//${window.location.hostname}:8000/api/workers/opencode-config/raw`;

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div>
          <h3 className="text-lg font-semibold">Worker OpenCode Config</h3>
          <p className="text-gray-400 text-sm mt-1">
            Save the OpenCode config that workers pull during bootstrap. Use this for custom providers and model aliases.
          </p>
        </div>
        <button onClick={save} disabled={saving || !loaded} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 rounded font-semibold text-sm">
          {saving ? 'Saving...' : 'Save Config'}
        </button>
      </div>

      {message && <div className="mb-3 bg-gray-800 text-gray-200 px-3 py-2 rounded text-sm">{message}</div>}
      <div className="mb-2 text-xs text-gray-500">Raw URL: <code className="text-gray-300">{rawUrl}</code></div>

      <textarea
        value={content}
        onChange={(event) => setContent(event.target.value)}
        spellCheck={false}
        className="w-full h-72 bg-gray-950 text-gray-200 font-mono text-sm px-4 py-3 rounded border border-gray-800"
      />
      <p className="text-yellow-300 text-xs mt-3">This can contain provider credentials. Keep this web app trusted/local.</p>
    </div>
  );
}

function BootstrapPanel() {
  const [webHost, setWebHost] = useState(window.location.hostname || 'localhost');
  const [workerName, setWorkerName] = useState('runner-01');
  const [workspace, setWorkspace] = useState('/srv/codecome/workspaces');
  const bootstrapUrl = `http://${webHost}:8000/api/workers/bootstrap-script`;
  const opencodeConfigUrl = `http://${webHost}:8000/api/workers/opencode-config/raw`;
  const command = `curl -fsSL ${bootstrapUrl} -o worker-bootstrap.sh\n\nsudo CODECOME_WORKER_NAME=${workerName} \\\n+  CODECOME_WORKSPACE_BASE=${workspace} \\\n+  CODECOME_HOME=/srv/codecome \\\n+  OPENCODE_CONFIG_URL=${opencodeConfigUrl} \\\n+  bash worker-bootstrap.sh`;
  const configCommand = `export OPENCODE_CONFIG_B64="$(base64 -w0 ~/.config/opencode/opencode.jsonc)"\n\nsudo OPENCODE_CONFIG_B64="$OPENCODE_CONFIG_B64" \\\n+  CODECOME_WORKER_NAME=${workerName} \\\n+  CODECOME_WORKSPACE_BASE=${workspace} \\\n+  CODECOME_HOME=/srv/codecome \\\n+  bash worker-bootstrap.sh`;

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
      <h3 className="text-lg font-semibold mb-2">Bootstrap Proxmox VM/LXC Worker</h3>
      <p className="text-gray-400 text-sm mb-4">
        Run this on the worker. It installs dependencies, Docker, creates the workspace folder, and pulls the saved Worker OpenCode config.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">Web Host/IP</label>
          <input value={webHost} onChange={(e) => setWebHost(e.target.value)} className="w-full bg-gray-800 px-3 py-2 rounded border border-gray-700" />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Worker Name</label>
          <input value={workerName} onChange={(e) => setWorkerName(e.target.value)} className="w-full bg-gray-800 px-3 py-2 rounded border border-gray-700" />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Workspace Path</label>
          <input value={workspace} onChange={(e) => setWorkspace(e.target.value)} className="w-full bg-gray-800 px-3 py-2 rounded border border-gray-700" />
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <div className="flex justify-between items-center mb-2">
            <h4 className="font-semibold text-sm">Bootstrap with saved Worker OpenCode config</h4>
            <button onClick={() => navigator.clipboard.writeText(command)} className="text-xs px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded">Copy</button>
          </div>
          <pre className="bg-gray-950 p-3 rounded text-xs overflow-x-auto whitespace-pre-wrap">{command}</pre>
        </div>
        <div>
          <div className="flex justify-between items-center mb-2">
            <h4 className="font-semibold text-sm">Alternative: bootstrap with local OpenCode config</h4>
            <button onClick={() => navigator.clipboard.writeText(configCommand)} className="text-xs px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded">Copy</button>
          </div>
          <pre className="bg-gray-950 p-3 rounded text-xs overflow-x-auto whitespace-pre-wrap">{configCommand}</pre>
        </div>
      </div>

      <p className="text-yellow-300 text-sm mt-4">VM workers are recommended. LXC workers may need privileged mode plus nesting/keyctl for Docker.</p>
    </div>
  );
}

export default function Workers() {
  const [workers, setWorkers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadWorkers = async () => {
    setError('');
    try {
      const data = await workersApi.list();
      setWorkers(data.workers || []);
    } catch (err) {
      setError(err.message || 'Failed to load workers');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadWorkers();
  }, []);

  const updateStatus = async (id, status) => {
    await workersApi.update(id, { status });
    loadWorkers();
  };

  const deleteWorker = async (id) => {
    if (!window.confirm('Delete this worker registration?')) return;
    await workersApi.delete(id);
    loadWorkers();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-3xl font-bold">Workers</h2>
          <p className="text-gray-400 mt-1">Register local, SSH, Proxmox VM, or Proxmox LXC runners for parallel audits.</p>
        </div>
        <button onClick={loadWorkers} className="px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded text-sm">Refresh</button>
      </div>

      {error && <div className="bg-red-500/20 text-red-300 px-3 py-2 rounded">{error}</div>}

      <OpenCodeConfigPanel />
      <BootstrapPanel />
      <RegisterWorkerForm onCreated={loadWorkers} />

      <div>
        <h3 className="text-lg font-semibold mb-3">Registered Workers</h3>
        {loading ? (
          <div className="text-gray-400">Loading workers...</div>
        ) : workers.length === 0 ? (
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 text-gray-400">No workers registered yet.</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {workers.map((worker) => (
              <WorkerCard
                key={worker.id}
                worker={worker}
                onDelete={deleteWorker}
                onDisable={(id) => updateStatus(id, 'disabled')}
                onEnable={(id) => updateStatus(id, 'idle')}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
