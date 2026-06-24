import React, { useEffect, useState } from 'react';
import { usersApi } from '../services/api';

const blankForm = {
  username: '',
  display_name: '',
  password: '',
  is_llm_user: true,
  llm_model: '',
  llm_context: '',
  auto_answer_enabled: true,
  active: true,
};

function UserBadge({ user }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${user.is_llm_user ? 'bg-purple-500/20 text-purple-200' : 'bg-cyan-500/20 text-cyan-200'}`}>
      {user.is_llm_user ? 'AI' : 'Human'}
    </span>
  );
}

function UserCard({ user, onChanged }) {
  const [form, setForm] = useState({
    display_name: user.display_name || '',
    password: '',
    llm_model: user.llm_model || '',
    llm_context: user.llm_context || '',
    auto_answer_enabled: !!user.auto_answer_enabled,
  });
  const [message, setMessage] = useState('');

  useEffect(() => {
    setForm({
      display_name: user.display_name || '',
      password: '',
      llm_model: user.llm_model || '',
      llm_context: user.llm_context || '',
      auto_answer_enabled: !!user.auto_answer_enabled,
    });
    setMessage('');
  }, [user.id, user.display_name, user.llm_model, user.llm_context, user.auto_answer_enabled]);

  const save = async () => {
    setMessage('');
    try {
      const payload = { ...form };
      if (!payload.password) delete payload.password;
      await usersApi.update(user.id, payload);
      setMessage('User saved.');
      await onChanged?.();
    } catch (error) {
      setMessage(`Save failed: ${error.message}`);
    }
  };

  const toggleActive = async () => {
    await usersApi.update(user.id, { active: !user.active });
    await onChanged?.();
  };

  return (
    <div className="rounded border border-gray-800 bg-gray-950/70 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-gray-100">{user.display_name}</span>
        <span className="font-mono text-xs text-gray-500">@{user.username}</span>
        <UserBadge user={user} />
        <span className={`rounded-full px-2 py-0.5 text-xs ${user.active ? 'bg-green-500/15 text-green-200' : 'bg-gray-700 text-gray-300'}`}>{user.active ? 'active' : 'inactive'}</span>
        <button onClick={toggleActive} className="ml-auto rounded bg-gray-800 px-2 py-1 text-xs hover:bg-gray-700">{user.active ? 'Disable' : 'Enable'}</button>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        <input value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} className="rounded border border-gray-800 bg-gray-900 px-3 py-2 text-sm" aria-label={`Display name for ${user.username}`} placeholder="display name" />
        {!user.is_llm_user && (
          <input value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} type="password" className="rounded border border-gray-800 bg-gray-900 px-3 py-2 text-sm" aria-label={`New password for ${user.username}`} placeholder="new password" />
        )}
        {user.is_llm_user && (
          <input value={form.llm_model} onChange={(event) => setForm({ ...form, llm_model: event.target.value })} className="rounded border border-gray-800 bg-gray-900 px-3 py-2 text-sm" aria-label={`AI model for ${user.username}`} placeholder="model" />
        )}
        {user.is_llm_user && (
          <label className="flex items-center gap-2 rounded border border-gray-800 bg-gray-900 px-3 py-2 text-sm">
            <input type="checkbox" checked={form.auto_answer_enabled} onChange={(event) => setForm({ ...form, auto_answer_enabled: event.target.checked })} /> Auto-answer
          </label>
        )}
        {user.is_llm_user && (
          <textarea value={form.llm_context} onChange={(event) => setForm({ ...form, llm_context: event.target.value })} className="h-24 rounded border border-gray-800 bg-gray-900 px-3 py-2 text-sm md:col-span-2" aria-label={`AI context for ${user.username}`} placeholder="AI context/persona" />
        )}
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button onClick={save} className="rounded bg-blue-700 px-3 py-1.5 text-xs font-semibold hover:bg-blue-600">Save User</button>
        {message && <span className="text-xs text-gray-400">{message}</span>}
      </div>
    </div>
  );
}

export default function Users() {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState(blankForm);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const data = await usersApi.list({ limit: 500 });
      setUsers(data.users || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const createUser = async () => {
    setMessage('');
    if (!form.is_llm_user && !form.password.trim()) {
      setMessage('Create failed: password is required for human users.');
      return;
    }
    try {
      const payload = { ...form };
      if (!payload.password) delete payload.password;
      if (!payload.display_name) payload.display_name = payload.username;
      await usersApi.create(payload);
      setForm(blankForm);
      setMessage('User created.');
      await load();
    } catch (error) {
      setMessage(`Create failed: ${error.message}`);
    }
  };

  const toggleActive = async (user) => {
    await usersApi.update(user.id, { active: !user.active });
    await load();
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-4xl font-bold">Users</h2>
        <p className="mt-1 text-sm text-gray-400">Human and fake AI users for audit question ownership.</p>
      </div>

      <div className="vortex-card rounded-xl p-5">
        <h3 className="text-lg font-semibold">Create User</h3>
        {message && <div className="mt-3 rounded bg-gray-900 px-3 py-2 text-sm text-gray-300">{message}</div>}
        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="rounded border border-gray-800 bg-gray-950 px-3 py-2" placeholder="username" />
          <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} className="rounded border border-gray-800 bg-gray-950 px-3 py-2" placeholder="display name" />
          <input value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} type="password" className="rounded border border-gray-800 bg-gray-950 px-3 py-2" placeholder="password for human users" />
          <input value={form.llm_model} onChange={(e) => setForm({ ...form, llm_model: e.target.value })} className="rounded border border-gray-800 bg-gray-950 px-3 py-2" placeholder="AI model, e.g. local/qwen3.6-27b" />
          <label className="flex items-center gap-2 rounded border border-gray-800 bg-gray-950 px-3 py-2 text-sm">
            <input type="checkbox" checked={form.is_llm_user} onChange={(e) => setForm({ ...form, is_llm_user: e.target.checked })} /> Fake AI user
          </label>
          <label className="flex items-center gap-2 rounded border border-gray-800 bg-gray-950 px-3 py-2 text-sm">
            <input type="checkbox" checked={form.auto_answer_enabled} onChange={(e) => setForm({ ...form, auto_answer_enabled: e.target.checked })} /> Auto-answer questions
          </label>
          <textarea value={form.llm_context} onChange={(e) => setForm({ ...form, llm_context: e.target.value })} className="h-28 rounded border border-gray-800 bg-gray-950 px-3 py-2 md:col-span-2" placeholder="Fake AI context/persona..." />
        </div>
        <button onClick={createUser} disabled={!form.username.trim() || (!form.is_llm_user && !form.password.trim())} className="mt-4 rounded bg-blue-600 px-4 py-2 font-semibold hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-gray-700">Create User</button>
      </div>

      <div className="vortex-card rounded-xl p-5">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Existing Users</h3>
          <button onClick={load} className="rounded bg-gray-800 px-3 py-2 text-sm hover:bg-gray-700">Refresh</button>
        </div>
        {loading ? <div className="text-gray-500">Loading users...</div> : (
          <div className="space-y-2">
            {users.map((user) => <UserCard key={user.id} user={user} onChanged={load} />)}
            {!users.length && <div className="text-center text-gray-500">No users created yet.</div>}
          </div>
        )}
      </div>
    </div>
  );
}
