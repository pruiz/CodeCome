import React, { useEffect, useState } from 'react';
import { previewApi } from '../services/api';

export default function PreviewAnalysis() {
  const [prompt, setPrompt] = useState('');
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    previewApi.getConfig()
      .then((data) => setPrompt(data.prompt || ''))
      .catch((error) => setMessage(`Load failed: ${error.message}`));
  }, []);

  const save = async () => {
    setSaving(true);
    setMessage('');
    try {
      await previewApi.updateConfig(prompt);
      setMessage('Preview analysis prompt saved.');
    } catch (error) {
      setMessage(`Save failed: ${error.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-4xl font-bold">Preview Analysis</h2>
        <p className="mt-1 text-sm text-gray-400">Configure a custom prompt for pre-analysis before the normal CodeCome phases.</p>
      </div>
      <div className="vortex-card rounded-xl p-5">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold">Custom Preview Prompt</h3>
            <p className="mt-1 text-sm text-gray-400">Use this to guide a future preview/preanalysis task. It can be a long mini-prompt.</p>
          </div>
          <button disabled={saving} onClick={save} className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold hover:bg-blue-500 disabled:bg-gray-700">
            {saving ? 'Saving...' : 'Save Prompt'}
          </button>
        </div>
        {message && <div className="mb-3 rounded bg-gray-950/70 px-3 py-2 text-sm text-gray-300">{message}</div>}
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} className="h-[32rem] w-full rounded border border-gray-800 bg-gray-950 px-4 py-3 font-mono text-sm text-gray-200" placeholder="Example: Before running full reconnaissance, summarize the target stack, identify likely auth boundaries, and propose 5 high-risk areas..." />
      </div>
    </div>
  );
}
