import React, { useEffect, useState } from 'react';
import { auditsApi, workersApi } from '../services/api';

export default function Phase1EnrichmentPanel({ audit, onRefresh }) {
  const auditId = audit.id;
  const [artifacts, setArtifacts] = useState(null);
  const [prompt, setPrompt] = useState(null);
  const [promptDraft, setPromptDraft] = useState('');
  const [workerModels, setWorkerModels] = useState([]);
  const [promptModel, setPromptModel] = useState(audit.model_settings?.['phase-1-prompt-enrich']?.model || '');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [modelSaving, setModelSaving] = useState(false);
  const [running, setRunning] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [artifactResponse, promptResponse] = await Promise.all([
        auditsApi.phase1EnrichmentArtifacts(auditId),
        auditsApi.phase1EnrichmentPrompt(auditId),
      ]);
      setArtifacts(artifactResponse);
      setPrompt(promptResponse);
      setPromptDraft(promptResponse.prompt || '');
    } catch (err) {
      setError(err.message || 'Failed to load Phase 1 enrichment data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [auditId]);

  useEffect(() => {
    setPromptModel(audit.model_settings?.['phase-1-prompt-enrich']?.model || '');
    if (!audit.assigned_worker_id) {
      setWorkerModels([]);
      return;
    }
    workersApi.models(audit.assigned_worker_id)
      .then((data) => setWorkerModels(data.models || []))
      .catch(() => setWorkerModels([]));
  }, [audit.id, audit.assigned_worker_id, audit.model_settings]);

  const savePrompt = async (nextPrompt) => {
    setSaving(true);
    setMessage('');
    setError('');
    try {
      const response = await auditsApi.updatePhase1EnrichmentPrompt(auditId, nextPrompt);
      setPrompt(response);
      setPromptDraft(response.prompt || '');
      await onRefresh?.();
      setMessage(String(nextPrompt || '').trim() ? 'Phase 1 enrichment prompt saved.' : 'Phase 1 enrichment prompt reset to User Prompt Enrichment default.');
    } catch (err) {
      setError(err.message || 'Failed to save Phase 1 enrichment prompt');
    } finally {
      setSaving(false);
    }
  };

  const savePromptModel = async () => {
    setModelSaving(true);
    setMessage('');
    setError('');
    try {
      const nextSettings = { ...(audit.model_settings || {}) };
      const phaseSettings = { ...(nextSettings['phase-1-prompt-enrich'] || {}) };
      if (promptModel) {
        phaseSettings.model = promptModel;
      } else {
        delete phaseSettings.model;
      }
      nextSettings['phase-1-prompt-enrich'] = phaseSettings;
      await auditsApi.update(auditId, { model_settings: nextSettings });
      await onRefresh?.();
      setMessage(promptModel ? 'Prompt enrichment model saved.' : 'Prompt enrichment model reset to audit default.');
    } catch (err) {
      setError(err.message || 'Failed to save prompt enrichment model');
    } finally {
      setModelSaving(false);
    }
  };

  const runStep = async (kind) => {
    setRunning(kind);
    setMessage('');
    setError('');
    try {
      const response = kind === 'semgrep'
        ? await auditsApi.runPhase1Semgrep(auditId)
        : await auditsApi.runPhase1PromptEnrichment(auditId);
      setMessage(response.message || `${kind} enrichment queued.`);
      await onRefresh?.();
      await load();
    } catch (err) {
      setError(err.message || `Failed to queue ${kind} enrichment`);
    } finally {
      setRunning('');
    }
  };

  const semgrepSummary = artifacts?.semgrep_summary || {};
  const artifactRows = artifacts?.artifacts || [];
  const runSummaries = artifacts?.run_summaries || [];

  return (
    <section className="space-y-4">
      <div className="rounded-xl border border-amber-800/70 bg-amber-950/30 p-4 text-sm text-amber-100">
        Phase 1 enrichment is optional and should run after <code>make phase-1</code> and before <code>make phase-2</code>. Semgrep and prompt leads are reconnaissance signals, not confirmed vulnerabilities or findings.
      </div>

      {error && <div className="rounded bg-red-950/40 px-3 py-2 text-sm text-red-200">{error}</div>}
      {message && <div className="rounded bg-gray-900 px-3 py-2 text-sm text-gray-200">{message}</div>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-gray-800 bg-gray-950 p-4">
          <div className="text-xs uppercase tracking-wide text-gray-500">Semgrep Results</div>
          <div className="mt-1 text-3xl font-bold text-gray-100">{semgrepSummary.total_results || 0}</div>
          <div className="mt-2 text-xs text-gray-500">Normalized from <code>itemdb/notes/semgrep-results.yml</code>.</div>
        </div>
        <div className="rounded-xl border border-gray-800 bg-gray-950 p-4">
          <div className="text-xs uppercase tracking-wide text-gray-500">Severity Counts</div>
          <div className="mt-2 space-y-1 text-sm text-gray-300">
            {Object.keys(semgrepSummary.by_severity || {}).length ? Object.entries(semgrepSummary.by_severity).map(([severity, count]) => (
              <div key={severity} className="flex justify-between"><span>{severity}</span><span>{count}</span></div>
            )) : <div className="text-gray-500">No severity data yet.</div>}
          </div>
        </div>
        <div className="rounded-xl border border-gray-800 bg-gray-950 p-4">
          <div className="text-xs uppercase tracking-wide text-gray-500">File Leads</div>
          <div className="mt-1 text-3xl font-bold text-gray-100">{Object.keys(semgrepSummary.by_file || {}).length}</div>
          <div className="mt-2 text-xs text-gray-500">Merged into <code>file-risk-index.yml</code> when Semgrep has results.</div>
        </div>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-950 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold">Run Enrichment</h3>
            <p className="mt-1 text-sm text-gray-500">These actions queue optional worker jobs and do not alter default phase progression.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => runStep('semgrep')} disabled={!!running} className="rounded bg-blue-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-600 disabled:cursor-not-allowed disabled:bg-gray-700">
              {running === 'semgrep' ? 'Queueing...' : 'Run Semgrep Enrichment'}
            </button>
            <button onClick={() => runStep('prompt')} disabled={!!running} className="rounded bg-purple-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-purple-600 disabled:cursor-not-allowed disabled:bg-gray-700">
              {running === 'prompt' ? 'Queueing...' : 'Run Prompt Enrichment'}
            </button>
            <button onClick={load} disabled={loading} className="rounded bg-gray-800 px-3 py-1.5 text-sm hover:bg-gray-700 disabled:opacity-50">Refresh</button>
          </div>
        </div>

        <div className="overflow-x-auto rounded border border-gray-800">
          <table className="min-w-full divide-y divide-gray-800 text-sm">
            <thead className="bg-gray-900/80 text-xs uppercase tracking-wide text-gray-500">
              <tr><th className="px-3 py-2 text-left">Artifact</th><th className="px-3 py-2 text-left">Status</th></tr>
            </thead>
            <tbody className="divide-y divide-gray-900">
              {artifactRows.map((artifact) => (
                <tr key={artifact.path}>
                  <td className="break-all px-3 py-2 font-mono text-xs text-gray-300">{artifact.path}</td>
                  <td className="px-3 py-2">{artifact.exists ? <span className="text-green-300">present</span> : <span className="text-gray-500">missing</span>}</td>
                </tr>
              ))}
              {!artifactRows.length && <tr><td colSpan="2" className="px-3 py-3 text-gray-500">{loading ? 'Loading artifacts...' : 'No artifacts found yet.'}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-950 p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">User Prompt Enrichment</div>
            <div className="font-mono text-xs text-gray-500">{prompt?.custom ? 'Audit custom prompt' : (prompt?.path || 'User Prompt Enrichment prompt')}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => savePrompt(promptDraft)} disabled={saving || loading} className="rounded bg-blue-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-600 disabled:cursor-not-allowed disabled:bg-gray-700">
              {saving ? 'Saving...' : 'Save Prompt'}
            </button>
            <button onClick={() => savePrompt('')} disabled={saving || loading || !prompt?.custom} className="rounded bg-gray-800 px-3 py-1.5 text-xs font-semibold text-gray-100 hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50">
              Reset to Preview
            </button>
          </div>
        </div>
        <textarea
          value={promptDraft}
          onChange={(event) => setPromptDraft(event.target.value)}
          spellCheck={false}
          placeholder="User Prompt Enrichment prompt or audit-specific enrichment prompt will appear here."
          className="h-72 w-full rounded border border-gray-800 bg-gray-900 p-3 font-mono text-xs leading-5 text-gray-200 placeholder:text-gray-600"
        />
        <div className="mt-2 text-xs text-gray-500">Prompt enrichment writes a durable prompt copy under <code>runs/phase-1-enrichment-prompt.md</code> before invoking the recon agent.</div>

        <div className="mt-4 rounded-lg border border-purple-900/60 bg-purple-950/20 p-3">
          <label htmlFor="phase1PromptModel" className="block text-sm font-semibold text-purple-100">Prompt enrichment model</label>
          <div className="mt-1 text-xs text-purple-200/70">This model is used by the selected worker when running the user-prompt enrichment phase. Semgrep itself does not use an LLM model.</div>
          <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-[1fr_auto]">
            <select
              id="phase1PromptModel"
              value={promptModel}
              disabled={modelSaving || workerModels.length === 0}
              onChange={(event) => setPromptModel(event.target.value)}
              className="rounded border border-purple-900/70 bg-gray-950 px-3 py-2 text-sm text-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">Use audit/default model</option>
              {workerModels.map((model) => <option key={model.id} value={model.id}>{model.id}</option>)}
            </select>
            <button
              onClick={savePromptModel}
              disabled={modelSaving}
              className="rounded bg-purple-700 px-3 py-2 text-sm font-semibold text-white hover:bg-purple-600 disabled:cursor-not-allowed disabled:bg-gray-700"
            >
              {modelSaving ? 'Saving...' : 'Save Model'}
            </button>
          </div>
          {!audit.assigned_worker_id && <div className="mt-2 text-xs text-purple-200/60">Select or assign a worker to load available models.</div>}
        </div>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-950 p-4">
        <div className="text-sm font-semibold">Latest Enrichment Run Summaries</div>
        <div className="mt-2 space-y-1 text-xs text-gray-300">
          {runSummaries.length ? runSummaries.map((name) => <div key={name} className="font-mono">runs/{name}</div>) : <div className="text-gray-500">No Phase 1 enrichment run summaries found.</div>}
        </div>
      </div>
    </section>
  );
}
