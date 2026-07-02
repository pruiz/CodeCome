import React, { useEffect, useState } from 'react';
import { previewApi, settingsApi } from '../services/api';

export default function Settings() {
  const [bindAddr, setBindAddr] = useState('127.0.0.1');
  const [publicBaseUrl, setPublicBaseUrl] = useState('');
  const [enrichmentPrompt, setEnrichmentPrompt] = useState('');
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [promptSaving, setPromptSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      settingsApi.getCodeServer(),
      previewApi.getConfig(),
    ])
      .then(([data, promptData]) => {
        setBindAddr(data.bind_addr || '127.0.0.1');
        setPublicBaseUrl(data.public_base_url || '');
        setEnrichmentPrompt(promptData.prompt || '');
      })
      .catch((error) => setMessage(`Load failed: ${error.message}`));
  }, []);

  const save = async () => {
    setSaving(true);
    setMessage('');
    try {
      await settingsApi.updateCodeServer({ bind_addr: bindAddr, public_base_url: publicBaseUrl });
      setMessage('Settings saved. Restart existing VS Code sessions for changes to apply.');
    } catch (error) {
      setMessage(`Save failed: ${error.message}`);
    } finally {
      setSaving(false);
    }
  };

  const savePrompt = async () => {
    setPromptSaving(true);
    setMessage('');
    try {
      await previewApi.updateConfig(enrichmentPrompt);
      setMessage('User Prompt Enrichment prompt saved.');
    } catch (error) {
      setMessage(`Save failed: ${error.message}`);
    } finally {
      setPromptSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-4xl font-bold">Settings</h2>
        <p className="mt-1 text-sm text-gray-400">Configure web-host tools, access URLs, and global enrichment prompts.</p>
      </div>
      {message && <div className="rounded bg-gray-950/70 px-3 py-2 text-sm text-gray-300">{message}</div>}
      <div className="vortex-card rounded-xl p-5">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold">VS Code Server</h3>
            <p className="mt-1 text-sm text-gray-400">Controls how audit workspace code-server sessions bind and which URL is shown to browser users.</p>
          </div>
          <button disabled={saving} onClick={save} className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold hover:bg-blue-500 disabled:bg-gray-700">
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="block">
            <span id="codeServerBindAddrLabel" className="text-sm font-semibold text-gray-300">Bind address</span>
            <input aria-labelledby="codeServerBindAddrLabel" value={bindAddr} onChange={(event) => setBindAddr(event.target.value)} className="mt-1 w-full rounded border border-gray-800 bg-gray-950 px-3 py-2 font-mono text-sm text-gray-200" placeholder="127.0.0.1" />
            <span className="mt-1 block text-xs text-gray-500">Use <code>127.0.0.1</code> for local-only, or <code>0.0.0.0</code> for LAN access.</span>
          </label>
          <label className="block">
            <span id="codeServerPublicBaseUrlLabel" className="text-sm font-semibold text-gray-300">Public base URL</span>
            <input aria-labelledby="codeServerPublicBaseUrlLabel" value={publicBaseUrl} onChange={(event) => setPublicBaseUrl(event.target.value)} className="mt-1 w-full rounded border border-gray-800 bg-gray-950 px-3 py-2 font-mono text-sm text-gray-200" placeholder="http://192.168.20.18" />
            <span className="mt-1 block text-xs text-gray-500">Leave empty for localhost URLs. Set this to the server URL when using LAN mode.</span>
          </label>
        </div>
      </div>
      <div className="vortex-card rounded-xl p-5">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold">User Prompt Enrichment</h3>
            <p className="mt-1 text-sm text-gray-400">Default prompt used by optional Phase 1 prompt enrichment unless an audit-specific override is saved.</p>
          </div>
          <button disabled={promptSaving} onClick={savePrompt} className="rounded bg-purple-700 px-4 py-2 text-sm font-semibold hover:bg-purple-600 disabled:bg-gray-700">
            {promptSaving ? 'Saving...' : 'Save Prompt'}
          </button>
        </div>
        <textarea
          value={enrichmentPrompt}
          onChange={(event) => setEnrichmentPrompt(event.target.value)}
          className="h-[32rem] w-full rounded border border-gray-800 bg-gray-950 px-4 py-3 font-mono text-sm text-gray-200"
          placeholder="Describe how to enrich Phase 1 notes with operator context, Semgrep signals, high-risk files, trust boundaries, and Phase 2 focus areas..."
        />
        <p className="mt-2 text-xs text-gray-500">This prompt is materialized on the selected worker before the user-prompt enrichment phase runs. It should update standard Phase 1 notes and candidate leads, not findings.</p>
      </div>
    </div>
  );
}
