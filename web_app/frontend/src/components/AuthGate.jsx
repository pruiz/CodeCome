import React, { useEffect, useRef, useState } from 'react';
import { authApi } from '../services/api';

export default function AuthGate({ children }) {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState(null);
  const [bootstrapRequired, setBootstrapRequired] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const ignoreNextAuthChange = useRef(false);

  const load = async () => {
    setLoading(true);
    try {
      const status = await authApi.status();
      setBootstrapRequired(!!status.bootstrap_required);
      if (authApi.getToken()) {
        try {
          setUser(await authApi.me());
        } catch (_) {
          authApi.logout();
          setUser(null);
        }
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const onAuthChanged = () => {
      if (ignoreNextAuthChange.current) {
        ignoreNextAuthChange.current = false;
        return;
      }
      if (!authApi.getToken()) {
        setUser(null);
        authApi.status().then((status) => setBootstrapRequired(!!status.bootstrap_required)).catch(() => {});
        return;
      }
      load();
    };
    window.addEventListener(authApi.authChangedEvent, onAuthChanged);
    return () => window.removeEventListener(authApi.authChangedEvent, onAuthChanged);
  }, []);

  const submit = async () => {
    setMessage('');
    try {
      ignoreNextAuthChange.current = true;
      const data = bootstrapRequired
        ? await authApi.bootstrap({ username, password, display_name: username, is_llm_user: false })
        : await authApi.login(username, password);
      setUser(data.user);
      setPassword('');
      setBootstrapRequired(false);
    } catch (error) {
      ignoreNextAuthChange.current = false;
      setMessage(error.message);
    }
  };

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-slate-400">Loading...</div>;
  }

  if (user) return children;

  return (
    <div className="flex min-h-screen items-center justify-center px-6 text-slate-100">
      <div className="vortex-card w-full max-w-md rounded-2xl p-8 shadow-2xl">
        <div className="text-xs uppercase tracking-[0.35em] text-cyan-400">CodeCome</div>
        <h1 className="mt-3 text-3xl font-bold">{bootstrapRequired ? 'Create First User' : 'Sign In'}</h1>
        <p className="mt-2 text-sm text-slate-400">
          {bootstrapRequired
            ? 'No active human user exists yet. Create the first local user to unlock the control plane.'
            : 'Authentication is required to access audits, findings, workers, and logs.'}
        </p>
        {message && <div className="mt-4 rounded border border-red-900/60 bg-red-950/30 px-3 py-2 text-sm text-red-200">{message}</div>}
        <div className="mt-6 space-y-3">
          <input value={username} onChange={(event) => setUsername(event.target.value)} className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100" placeholder="username" />
          <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100" placeholder="password" />
          <button onClick={submit} disabled={!username.trim() || !password.trim()} className="w-full rounded-lg bg-blue-600 px-4 py-2 font-semibold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-500">
            {bootstrapRequired ? 'Create User' : 'Login'}
          </button>
        </div>
      </div>
    </div>
  );
}
