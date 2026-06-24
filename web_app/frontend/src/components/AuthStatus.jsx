import React, { useEffect, useState } from 'react';
import { authApi } from '../services/api';

export default function AuthStatus() {
  const [user, setUser] = useState(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [bootstrapRequired, setBootstrapRequired] = useState(false);

  useEffect(() => {
    authApi.status().then((status) => setBootstrapRequired(!!status.bootstrap_required)).catch(() => {});
    if (authApi.getToken()) authApi.me().then(setUser).catch(() => authApi.logout());
  }, []);

  const login = async () => {
    setMessage('');
    try {
      const data = await authApi.login(username, password);
      setUser(data.user);
      setPassword('');
    } catch (error) {
      setMessage(error.message);
    }
  };

  const logout = () => {
    authApi.logout();
    setUser(null);
    setMessage('Logged out.');
  };

  const bootstrap = async () => {
    setMessage('');
    try {
      const data = await authApi.bootstrap({ username, password, display_name: username, is_llm_user: false });
      setUser(data.user);
      setBootstrapRequired(false);
      setPassword('');
    } catch (error) {
      setMessage(error.message);
    }
  };

  if (user) {
    return (
      <div className="space-y-2">
        <div className="font-semibold text-slate-300">Signed in</div>
        <div className="truncate text-slate-400">{user.display_name}</div>
        <button onClick={logout} className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 hover:bg-slate-700">Logout</button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="font-semibold text-slate-300">{bootstrapRequired ? 'Create First User' : 'Login'}</div>
      <input value={username} onChange={(event) => setUsername(event.target.value)} className="w-full rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-200" placeholder="username" />
      <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" className="w-full rounded border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-200" placeholder="password" />
      <button onClick={bootstrapRequired ? bootstrap : login} disabled={!username || !password} className="rounded bg-blue-700 px-2 py-1 text-xs font-semibold text-white hover:bg-blue-600 disabled:bg-slate-700 disabled:text-slate-500">{bootstrapRequired ? 'Create User' : 'Login'}</button>
      {message && <div className="text-[10px] text-slate-500">{message}</div>}
    </div>
  );
}
