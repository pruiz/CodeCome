import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAudit } from '../hooks/useAudits';
import { auditsApi, logsApi, phasesApi, questionsApi, usersApi } from '../services/api';
import LiveLogs from './LiveLogs';
import FindingsList from './FindingsList';
import AuditQuestions from './AuditQuestions';
import { formatSpainDateTime, formatSpainTime } from '../utils/dates';

function cleanTerminalText(value) {
  return String(value || '')
    .replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, '')
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, '')
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '');
}

function formatDateTime(value) {
  return formatSpainDateTime(value);
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return '-';
  const total = Math.max(0, Number(seconds) || 0);
  if (total < 60) return `${Math.round(total)}s`;

  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = Math.round(total % 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m${secs && hours < 2 ? ` ${secs}s` : ''}`;
  }
  return `${minutes}m ${secs}s`;
}

function StatusBadge({ status }) {
  const colorMap = {
    'initializing': 'yellow',
    'ready': 'green',
    'completed': 'green',
    'paused': 'orange',
  };
  
  const getColor = () => {
    if (status.includes('_running')) return 'blue';
    if (status.includes('_complete')) return 'green';
    if (status.includes('_failed')) return 'red';
    return colorMap[status] || 'gray';
  };
  
  const bgMap = {
    'yellow': 'bg-yellow-500/20 text-yellow-300',
    'green': 'bg-green-500/20 text-green-300',
    'blue': 'bg-blue-500/20 text-blue-300',
    'orange': 'bg-orange-500/20 text-orange-300',
    'red': 'bg-red-500/20 text-red-300',
    'gray': 'bg-gray-500/20 text-gray-300',
  };
  
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-semibold ${bgMap[getColor()]}`}>
      {status.replace(/_/g, ' ')}
    </span>
  );
}

const auditSteps = [
  { key: 'make init', statusPrefix: 'make_init', label: 'make init', sub: 'venv + deps' },
  { key: 'make check', statusPrefix: 'make_check', label: 'make check', sub: 'preflight' },
  { key: 'phase-1', statusPrefix: 'phase_1', label: 'make phase-1', sub: 'Reconnaissance' },
  { key: 'phase-2', statusPrefix: 'phase_2', label: 'make phase-2', sub: 'Hypothesis' },
  { key: 'make sweep', statusPrefix: 'make_sweep', label: 'make sweep', sub: 'Optional deep sweep' },
  { key: 'phase-3', statusPrefix: 'phase_3', label: 'make phase-3', sub: 'Counter-analysis' },
  { key: 'make validate-all', statusPrefix: 'make_validate_all', label: 'make validate-all', sub: 'Validate findings' },
  { key: 'make exploit-all', statusPrefix: 'make_exploit_all', label: 'make exploit-all', sub: 'Exploit confirmed' },
  { key: 'phase-6', statusPrefix: 'phase_6', label: 'make phase-6', sub: 'Reporting' },
];

function stepStatus(audit, step) {
  const executions = audit?.phase_executions || [];
  const execution = latestExecutionForPhase(executions, step.key);
  if (execution?.status === 'success') return 'complete';
  if (execution?.status === 'triaged_complete') return 'complete';
  if (execution?.status === 'running') return 'running';
  if (execution?.status === 'failed') return 'failed';
  const auditStatus = audit?.status || '';
  if (auditStatus.startsWith(step.statusPrefix) && auditStatus.endsWith('_running')) return 'running';
  if (auditStatus.startsWith(step.statusPrefix) && auditStatus.endsWith('_complete')) return 'complete';
  if (auditStatus.startsWith(step.statusPrefix) && auditStatus.endsWith('_failed')) return 'failed';
  return 'empty';
}

function latestExecutionForPhase(executions, phase) {
  const matches = (executions || []).filter((item) => item.phase === phase);
  if (!matches.length) return null;
  return matches.reduce((latest, item) => {
    const latestTime = latest.started_at ? new Date(latest.started_at).getTime() : 0;
    const itemTime = item.started_at ? new Date(item.started_at).getTime() : 0;
    if (itemTime > latestTime) return item;
    if (itemTime === latestTime && (item.id || 0) > (latest.id || 0)) return item;
    return latest;
  }, matches[0]);
}

function PhaseProgress({ audit, selectedPhase, onSelectPhase }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-9 gap-2 mb-6">
      {auditSteps.map((step) => {
        const status = stepStatus(audit, step);
        const selected = selectedPhase === step.key;
        const styles = {
          empty: 'border-gray-800 bg-gray-900/80 text-gray-500',
          complete: 'border-green-700/70 bg-green-950/50 text-green-200 shadow-green-950/30',
          running: 'border-blue-700/70 bg-blue-950/50 text-blue-200 shadow-blue-950/30',
          failed: 'border-red-700/70 bg-red-950/50 text-red-200 shadow-red-950/30',
        };
        const dot = {
          empty: 'bg-gray-600',
          complete: 'bg-green-400',
          running: 'bg-blue-400 animate-pulse',
          failed: 'bg-red-400',
        };
        
        return (
          <button
            key={step.key}
            onClick={() => onSelectPhase(step.key)}
            className={`min-w-0 rounded-xl border p-3 text-left shadow-lg transition ${styles[status]} ${selected ? 'ring-2 ring-blue-300' : ''}`}
          >
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${dot[status]}`}></span>
              <span className="truncate text-xs font-bold">{step.label}</span>
            </div>
            <div className="mt-1 truncate text-[10px] opacity-75">{step.sub}</div>
          </button>
        );
      })}
    </div>
  );
}

function PhaseLogs({ auditId, phase, refreshToken = 0 }) {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const pageSize = 500;

  const loadLogs = async (skip = 0, appendOlder = false) => {
    setLoading(true);
    try {
      const data = await logsApi.list(auditId, { phase, limit: pageSize, skip });
      const page = [...(data.logs || [])].reverse();
      setLogs((current) => appendOlder ? [...page, ...current] : page);
      setTotal(data.total || 0);
    } finally {
      setLoading(false);
    }
  };

  const loadOlder = async () => {
    if (logs.length >= total) return;
    setLoadingMore(true);
    try {
      const data = await logsApi.list(auditId, { phase, limit: pageSize, skip: logs.length });
      const page = [...(data.logs || [])].reverse();
      setLogs((current) => [...page, ...current]);
      setTotal(data.total || 0);
    } finally {
      setLoadingMore(false);
    }
  };

  const loadAll = async () => {
    setLoadingMore(true);
    try {
      let loaded = logs.length;
      let currentLogs = logs;
      let currentTotal = total;
      while (loaded < currentTotal) {
        const data = await logsApi.list(auditId, { phase, limit: pageSize, skip: loaded });
        const page = [...(data.logs || [])].reverse();
        currentLogs = [...page, ...currentLogs];
        currentTotal = data.total || currentTotal;
        loaded = currentLogs.length;
        setLogs(currentLogs);
        setTotal(currentTotal);
        if (!page.length) break;
      }
    } finally {
      setLoadingMore(false);
    }
  };

  React.useEffect(() => {
    loadLogs();
  }, [auditId, phase, refreshToken]);

  return (
    <div className="mt-6 rounded-xl border border-gray-700 bg-gray-950 p-4">
      <div className="mb-3 flex items-center justify-between gap-4">
        <div>
          <h4 className="font-semibold">Logs for {phase}</h4>
          <p className="text-xs text-gray-500">Showing {logs.length} of {total} log entries</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => loadLogs()} className="rounded bg-gray-800 px-3 py-1 text-sm hover:bg-gray-700">Refresh</button>
          <button
            onClick={loadOlder}
            disabled={loadingMore || logs.length >= total}
            className="rounded bg-gray-800 px-3 py-1 text-sm hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loadingMore ? 'Loading...' : 'Load Older'}
          </button>
          <button
            onClick={loadAll}
            disabled={loadingMore || logs.length >= total}
            className="rounded bg-gray-800 px-3 py-1 text-sm hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Load All
          </button>
        </div>
      </div>
      {loading ? (
        <div className="text-gray-500">Loading logs...</div>
      ) : logs.length === 0 ? (
        <div className="text-gray-500">No logs for this phase yet.</div>
      ) : (
        <div className="max-h-96 overflow-y-auto font-mono text-xs">
          {logs.map((log) => (
            <LogLine key={log.id} log={log} />
          ))}
        </div>
      )}
    </div>
  );
}

function LogLine({ log }) {
  const message = cleanTerminalText(log.message);
  const tokenMatch = message.match(/step finished: ([^(]+) \(input=(\d+), output=(\d+), reasoning=(\d+), total=(\d+)\)/);
  const modelMatch = message.match(/^> Assistant · (.+?)(?: \(|$)/);

  return (
    <div className="py-0.5 text-gray-300">
      <span className="text-gray-500">[{formatSpainTime(log.timestamp)}]</span>
      <span className={log.level === 'ERROR' ? 'ml-2 text-red-300' : log.level === 'WARN' ? 'ml-2 text-yellow-300' : 'ml-2 text-blue-300'}>{log.level}</span>
      <span className="ml-2 text-gray-500">{log.source || '-'}</span>
      {modelMatch && <span className="ml-2 rounded bg-purple-500/20 px-1.5 py-0.5 text-[10px] text-purple-200">LLM turn model: {modelMatch[1]}</span>}
      {tokenMatch && (
        <span className="ml-2 rounded bg-cyan-500/20 px-1.5 py-0.5 text-[10px] text-cyan-200">
          step tokens: in {tokenMatch[2]} / out {tokenMatch[3]} / reasoning {tokenMatch[4]} / total {tokenMatch[5]}
        </span>
      )}
      <span className="ml-2">{message}</span>
    </div>
  );
}

function SelectedPhasePanel({ audit, selectedPhase, selectedExecutionId, onRerun, onSaveEnv }) {
  const [refreshToken, setRefreshToken] = useState(0);
  const [envRows, setEnvRows] = useState([{ key: '', value: '' }]);
  const [envMessage, setEnvMessage] = useState('');
  const [tokenSummary, setTokenSummary] = useState(null);
  const [phaseDetails, setPhaseDetails] = useState(null);
  const [phaseFindings, setPhaseFindings] = useState(null);
  const [phaseTriages, setPhaseTriages] = useState(null);
  const [triageMessage, setTriageMessage] = useState('');
  const [reportMessage, setReportMessage] = useState('');
  const executions = audit?.phase_executions || [];
  const execution = selectedExecutionId
    ? executions.find((item) => item.id === selectedExecutionId)
    : latestExecutionForPhase(executions, selectedPhase);
  const step = auditSteps.find((item) => item.key === selectedPhase);
  const status = step ? stepStatus(audit, step) : 'empty';
  const style = phaseHistoryStyle(execution?.status || (status === 'complete' ? 'success' : status));
  const canRerun = execution && execution.status !== 'running' && !audit.status.includes('_running');
  const isOptionalPhase = selectedPhase === 'make sweep';
  const canRunOptional = isOptionalPhase && !audit.status.includes('_running');

  React.useEffect(() => {
    const env = audit?.model_settings?.[selectedPhase]?.env || audit?.model_settings?.[selectedPhase]?.env_overrides || {};
    const rows = Object.entries(env).map(([key, value]) => ({ key, value: String(value ?? '') }));
    setEnvRows(rows.length ? rows : [{ key: '', value: '' }]);
    setEnvMessage('');
  }, [audit?.id, selectedPhase, audit?.model_settings]);

  React.useEffect(() => {
    if (!audit?.id || !selectedPhase) return;
    logsApi.tokenSummary(audit.id, selectedPhase)
      .then((data) => setTokenSummary(data.summary))
      .catch(() => setTokenSummary(null));
  }, [audit?.id, selectedPhase, refreshToken]);

  React.useEffect(() => {
    setPhaseDetails(null);
    setPhaseFindings(null);
    setPhaseTriages(null);
    if (!execution?.id) return;
    phasesApi.get(execution.id).then(setPhaseDetails).catch(() => setPhaseDetails(null));
    phasesApi.findings(execution.id).then(setPhaseFindings).catch(() => setPhaseFindings(null));
    phasesApi.triages(execution.id).then(setPhaseTriages).catch(() => setPhaseTriages(null));
  }, [execution?.id, refreshToken]);

  const runTriage = async () => {
    if (!execution?.id) return;
    setTriageMessage('');
    try {
      const response = await phasesApi.runTriage(execution.id);
      setTriageMessage(response.message || 'Failure triage queued.');
      setRefreshToken((value) => value + 1);
    } catch (error) {
      setTriageMessage(`Triage failed: ${error.message}`);
    }
  };

  const applyTriage = async (triage) => {
    setTriageMessage('');
    try {
      const response = await phasesApi.applyTriage(triage.id, { apply_env: true });
      setTriageMessage(response.message || 'Triage decision applied.');
      setRefreshToken((value) => value + 1);
      audit.onRefresh?.();
    } catch (error) {
      setTriageMessage(`Apply failed: ${error.message}`);
    }
  };

  const saveEnv = async () => {
    setEnvMessage('');
    try {
      const env = {};
      for (const row of envRows) {
        const key = row.key.trim();
        if (!key && !row.value.trim()) continue;
        if (!key) throw new Error('Every value must have an environment variable name.');
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
          throw new Error(`${key} is not a valid environment variable name.`);
        }
        env[key] = row.value;
      }
      await onSaveEnv(selectedPhase, env);
      setEnvMessage('Environment variables saved for this phase.');
    } catch (error) {
      setEnvMessage(`Save failed: ${error.message}`);
    }
  };

  const updateEnvRow = (index, field, value) => {
    setEnvRows((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row));
  };

  const addEnvRow = () => setEnvRows((rows) => [...rows, { key: '', value: '' }]);

  const removeEnvRow = (index) => {
    setEnvRows((rows) => {
      const next = rows.filter((_, rowIndex) => rowIndex !== index);
      return next.length ? next : [{ key: '', value: '' }];
    });
  };

  const downloadReport = async () => {
    setReportMessage('');
    try {
      const { blob, filename } = await auditsApi.downloadReport(audit.id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setReportMessage(`Downloaded ${filename}.`);
    } catch (error) {
      setReportMessage(`Download failed: ${error.message}`);
    }
  };

  return (
    <div className={`mt-6 rounded-xl border p-4 ${style.row}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-wide text-gray-400">Selected phase</div>
          <h3 className={`mt-1 text-xl font-bold ${style.phase}`}>{step?.label || selectedPhase}</h3>
          <p className="mt-1 text-sm text-gray-400">{step?.sub || 'CodeCome step'}</p>
          {execution && (
            <p className="mt-1 text-xs text-gray-500">
              Showing {selectedExecutionId ? 'selected history attempt' : 'latest attempt'}: execution #{execution.id}, attempt {execution.attempt}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setRefreshToken((value) => value + 1)}
            className="rounded bg-gray-800 px-3 py-2 text-sm hover:bg-gray-700"
          >
            Refresh Logs
          </button>
          <button
            onClick={() => onRerun(execution)}
            disabled={!canRerun}
            title={execution ? (canRerun ? 'Rerun selected phase' : 'Cannot rerun while an audit is running') : 'This phase has not run yet'}
            className="rounded bg-blue-600 px-3 py-2 text-sm font-semibold hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-gray-700 disabled:text-gray-400"
          >
            Rerun Phase
          </button>
          {isOptionalPhase && (
            <button
              onClick={() => audit.onRunOptionalPhase?.(selectedPhase)}
              disabled={!canRunOptional}
              className="rounded bg-cyan-600 px-3 py-2 text-sm font-semibold hover:bg-cyan-500 disabled:cursor-not-allowed disabled:bg-gray-700 disabled:text-gray-400"
            >
              Run Optional Sweep
            </button>
          )}
          {selectedPhase === 'phase-6' && (
            <button
              onClick={downloadReport}
              className="rounded bg-green-700 px-3 py-2 text-sm font-semibold hover:bg-green-600"
            >
              Download Report
            </button>
          )}
        </div>
      </div>

      {reportMessage && <div className="mt-3 rounded bg-gray-950 px-3 py-2 text-sm text-gray-300">{reportMessage}</div>}

      {execution ? (
        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-6">
          <div className="rounded bg-gray-950/70 p-3">
            <div className="text-xs text-gray-500">Status</div>
            <div className="font-semibold">{execution.status}</div>
          </div>
          <div className="rounded bg-gray-950/70 p-3">
            <div className="text-xs text-gray-500">Attempt</div>
            <div className="font-semibold">{execution.attempt}</div>
          </div>
          <div className="rounded bg-gray-950/70 p-3">
            <div className="text-xs text-gray-500">Exit Code</div>
            <div className="font-semibold">{execution.exit_code ?? '-'}</div>
          </div>
          <div className="rounded bg-gray-950/70 p-3">
            <div className="text-xs text-gray-500">Duration</div>
            <div className="font-semibold">{formatDuration(execution.duration_seconds)}</div>
          </div>
          <div className="rounded bg-gray-950/70 p-3 xl:col-span-2">
            <div className="text-xs text-gray-500">Started</div>
            <div className="font-semibold">{formatDateTime(execution.started_at)}</div>
          </div>
          <div className="rounded bg-gray-950/70 p-3 xl:col-span-2">
            <div className="text-xs text-gray-500">Completed</div>
            <div className="font-semibold">{formatDateTime(execution.completed_at)}</div>
          </div>
          {execution.command_line && (
            <div className="rounded bg-gray-950/70 p-3 md:col-span-2 xl:col-span-6">
              <div className="mb-1 text-xs text-gray-500">Command</div>
              <pre className="overflow-x-auto text-xs text-gray-200">{execution.command_line}</pre>
            </div>
          )}
          {(execution.remote_job_dir || execution.remote_pid) && (
            <div className="rounded border border-cyan-900/60 bg-cyan-950/20 p-3 md:col-span-2 xl:col-span-6">
              <div className="mb-1 text-xs uppercase tracking-wide text-cyan-400">Recoverable Remote Job</div>
              <div className="grid grid-cols-1 gap-2 text-xs text-gray-300 md:grid-cols-2">
                <div><span className="text-gray-500">PID:</span> {execution.remote_pid || '-'}</div>
                <div className="break-all"><span className="text-gray-500">Job dir:</span> {execution.remote_job_dir || '-'}</div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-4 rounded border border-gray-700 bg-gray-950/70 p-3 text-sm text-gray-400">
          This phase has not run yet. Use Start/Continue to advance the audit to the next pending step.
        </div>
      )}

      {tokenSummary && tokenSummary.turns > 0 && (
        <div className="mt-4 rounded bg-gray-950/70 p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">Approximate token usage</div>
              <div className="text-xs text-gray-500">Sum of OpenCode per-turn <code>step finished</code> log lines for this phase.</div>
            </div>
            <span className="rounded-full bg-cyan-500/20 px-2 py-1 text-xs text-cyan-200">{tokenSummary.turns} turns</span>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
            <div className="rounded bg-gray-900 p-3"><div className="text-xs text-gray-500">Input</div><div className="font-semibold">{tokenSummary.input_tokens.toLocaleString()}</div></div>
            <div className="rounded bg-gray-900 p-3"><div className="text-xs text-gray-500">Output</div><div className="font-semibold">{tokenSummary.output_tokens.toLocaleString()}</div></div>
            <div className="rounded bg-gray-900 p-3"><div className="text-xs text-gray-500">Reasoning</div><div className="font-semibold">{tokenSummary.reasoning_tokens.toLocaleString()}</div></div>
            <div className="rounded bg-gray-900 p-3"><div className="text-xs text-gray-500">Total</div><div className="font-semibold">{tokenSummary.total_tokens.toLocaleString()}</div></div>
          </div>
          {Object.keys(tokenSummary.models || {}).length > 0 && (
            <div className="mt-3 space-y-2">
              {Object.entries(tokenSummary.models).map(([model, usage]) => (
                <div key={model} className="flex flex-wrap items-center justify-between gap-2 rounded bg-gray-900 px-3 py-2 text-xs">
                  <span className="text-purple-300">{model}</span>
                  <span className="text-gray-400">{usage.turns} turns · total {usage.total_tokens.toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {execution && (
        <div className="mt-4 rounded border border-purple-900/60 bg-purple-950/20 p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-purple-100">Failure triage</div>
              <div className="text-xs text-purple-200/70">OpenCode reviews non-OK phase output and recommends accept, rerun, or rerun with safer options.</div>
            </div>
            <button
              onClick={runTriage}
              disabled={execution.status === 'running'}
              className="rounded bg-purple-700 px-3 py-1.5 text-sm font-semibold hover:bg-purple-600 disabled:cursor-not-allowed disabled:bg-gray-700 disabled:text-gray-400"
            >
              Run Triage Now
            </button>
          </div>
          {triageMessage && <div className="mb-2 rounded bg-gray-950 px-2 py-1 text-xs text-gray-300">{triageMessage}</div>}
          {phaseTriages?.triages?.length ? (
            <div className="space-y-2">
              {phaseTriages.triages.map((triage) => (
                <div key={triage.id} className="rounded border border-gray-800 bg-gray-950/80 p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-purple-200">#{triage.id}</span>
                    <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-300">{triage.status}</span>
                    {triage.decision && <span className="rounded bg-cyan-900/60 px-2 py-0.5 text-xs text-cyan-200">{triage.decision}</span>}
                    {triage.confidence && <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-300">{triage.confidence}</span>}
                    {triage.report_path && <span className="text-xs text-gray-500">{triage.report_path}</span>}
                  </div>
                  {triage.reason && <p className="mt-2 text-gray-300">{triage.reason}</p>}
                  {Object.keys(triage.recommended_env || {}).length > 0 && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs font-semibold text-gray-400">Recommended env overrides</summary>
                      <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap rounded bg-gray-900 p-2 text-xs text-gray-300">{JSON.stringify(triage.recommended_env, null, 2)}</pre>
                    </details>
                  )}
                  {triage.evidence?.length > 0 && (
                    <ul className="mt-2 list-disc pl-5 text-xs text-gray-400">
                      {triage.evidence.map((item, index) => <li key={index}>{item}</li>)}
                    </ul>
                  )}
                  {triage.error_message && <div className="mt-2 text-xs text-red-300">{triage.error_message}</div>}
                  {['ACCEPT_AS_COMPLETE', 'RERUN_SAME_OPTIONS', 'RERUN_WITH_OPTIONS'].includes(triage.decision) && triage.status === 'completed' && (
                    <button onClick={() => applyTriage(triage)} className="mt-3 rounded bg-cyan-700 px-3 py-1.5 text-xs font-semibold hover:bg-cyan-600">
                      Apply Decision
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-purple-200/60">No triage records for this execution yet.</div>
          )}
        </div>
      )}

      {execution && <div className="mt-4"><AuditQuestions auditId={audit.id} phaseExecutionId={execution.id} auditStatus={audit.status} /></div>}

      {phaseDetails && (
        <div className="mt-4 rounded bg-gray-950/70 p-3">
          <div className="mb-3 text-sm font-semibold">Captured command output</div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <details open className="rounded border border-gray-800 bg-gray-950 p-3">
              <summary className="cursor-pointer text-xs font-semibold text-gray-300">stdout</summary>
              <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs text-gray-300">{cleanTerminalText(phaseDetails.stdout_log || 'No stdout captured.')}</pre>
            </details>
            <details className="rounded border border-gray-800 bg-gray-950 p-3">
              <summary className="cursor-pointer text-xs font-semibold text-gray-300">stderr</summary>
              <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs text-yellow-200">{cleanTerminalText(phaseDetails.stderr_log || 'No stderr captured.')}</pre>
            </details>
          </div>
        </div>
      )}

      {phaseFindings && (
        <div className="mt-4 rounded bg-gray-950/70 p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">Findings associated with this phase</div>
              <div className="text-xs text-gray-500">Best effort: {phaseFindings.inference}</div>
            </div>
            <span className="rounded-full bg-gray-900 px-2 py-1 text-xs text-gray-300">{phaseFindings.total} findings</span>
          </div>
          {phaseFindings.findings?.length ? (
            <div className="space-y-2">
              {phaseFindings.findings.map((finding) => (
                <a key={`${finding.audit_id}-${finding.id}`} href={`/audit/${finding.audit_id}/findings/${finding.id}`} className="block rounded border border-gray-800 bg-gray-950 px-3 py-2 text-sm hover:border-cyan-700">
                  <span className="font-mono text-cyan-300">{finding.id}</span>
                  <span className="ml-2 text-gray-200">{finding.title}</span>
                  <span className="ml-2 text-xs text-gray-500">{finding.status} · {finding.severity}</span>
                </a>
              ))}
            </div>
          ) : (
            <div className="text-sm text-gray-500">No findings can be attributed to this phase by timestamp.</div>
          )}
        </div>
      )}

      <div className="mt-4 rounded bg-gray-950/70 p-3">
        <div className="mb-2 flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">Environment overrides</div>
            <div className="text-xs text-gray-500">Injected into this phase command. These override audit-level environment variables with the same name.</div>
          </div>
          <div className="flex gap-2">
            <button onClick={addEnvRow} className="rounded bg-gray-800 px-3 py-1 text-sm hover:bg-gray-700">Add Row</button>
            <button onClick={saveEnv} className="rounded bg-blue-600 px-3 py-1 text-sm font-semibold hover:bg-blue-500">Save Env</button>
          </div>
        </div>
        {envMessage && <div className="mb-2 rounded bg-gray-900 px-2 py-1 text-xs text-gray-300">{envMessage}</div>}
        <div className="space-y-3">
          {envRows.map((row, index) => (
            <div key={index} className="rounded border border-gray-800 bg-gray-950 p-3">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-[10px] uppercase tracking-wide text-gray-500">Variable</label>
                <input
                  value={row.key}
                  onChange={(event) => updateEnvRow(index, 'key', event.target.value)}
                  className="h-24 w-full rounded border border-gray-800 bg-gray-900 px-3 py-2 font-mono text-xs text-gray-200"
                  placeholder="PROMPT_EXTRA"
                />
              </div>
              <div>
                <label className="mb-1 block text-[10px] uppercase tracking-wide text-gray-500">Value</label>
                <textarea
                  value={row.value}
                  onChange={(event) => updateEnvRow(index, 'value', event.target.value)}
                  spellCheck={false}
                  className="h-24 w-full rounded border border-gray-800 bg-gray-900 px-3 py-2 font-mono text-xs text-gray-200"
                  placeholder="Focus on authentication flows first..."
                />
              </div>
              </div>
              <div className="mt-2 flex justify-end">
                <button
                  onClick={() => removeEnvRow(index)}
                  className="rounded bg-red-900/50 px-3 py-1.5 text-xs text-red-200 hover:bg-red-800/70"
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 rounded border border-gray-800 bg-gray-950 px-3 py-2 text-xs text-gray-500">
          Common variables: <code>CODECOME_THINKING</code>, <code>CODECOME_MODEL</code>, <code>CODECOME_MODEL_VARIANT</code>, <code>PROMPT_EXTRA</code>, <code>PROMPT_EXTRA_FILE</code>, <code>CODECOME_ALLOW_NO_SANDBOX</code>.
        </div>
      </div>

      <PhaseLogs auditId={audit.id} phase={selectedPhase} refreshToken={refreshToken} />
    </div>
  );
}

function phaseHistoryStyle(status) {
  if (status === 'success' || status === 'triaged_complete') {
    return {
      row: 'border-green-700/60 bg-green-950/30',
      phase: 'text-green-200',
      badge: 'bg-green-500/20 text-green-300 border-green-600/40',
    };
  }
  if (status === 'running') {
    return {
      row: 'border-blue-700/60 bg-blue-950/30',
      phase: 'text-blue-200',
      badge: 'bg-blue-500/20 text-blue-300 border-blue-600/40',
    };
  }
  if (status === 'failed') {
    return {
      row: 'border-red-700/60 bg-red-950/30',
      phase: 'text-red-200',
      badge: 'bg-red-500/20 text-red-300 border-red-600/40',
    };
  }
  return {
    row: 'border-gray-700 bg-gray-700',
    phase: 'text-gray-200',
    badge: 'bg-gray-500/20 text-gray-300 border-gray-600/40',
  };
}

function PhaseHistory({ audit, selectedPhase, selectedExecutionId, onSelectExecution }) {
  const executions = [...(audit.phase_executions || [])].sort((left, right) => {
    const rightTime = right.started_at ? new Date(right.started_at).getTime() : 0;
    const leftTime = left.started_at ? new Date(left.started_at).getTime() : 0;
    if (rightTime !== leftTime) return rightTime - leftTime;
    return (right.id || 0) - (left.id || 0);
  });

  return (
    <section className="rounded-xl border border-gray-700 bg-gray-900 p-4 shadow-lg shadow-black/20">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-100">Phase History</h3>
          <p className="mt-1 text-sm text-gray-400">All CodeCome commands executed for this audit. Click one to inspect command, output, logs, and associated findings.</p>
        </div>
        <span className="rounded-full border border-gray-700 bg-gray-950 px-2.5 py-1 text-xs text-gray-400">
          {audit.phase_executions?.length || 0} entries
        </span>
      </div>
      {executions.length ? (
        <div className="space-y-2">
          {executions.map(exec => {
            const style = phaseHistoryStyle(exec.status);
            return (
              <button key={exec.id} onClick={() => onSelectExecution(exec)} className={`block w-full rounded border p-3 text-left ${style.row} ${selectedExecutionId === exec.id ? 'ring-2 ring-blue-300' : ''}`}>
                <div className="flex items-center gap-3">
                  <span className={`font-semibold ${style.phase}`}>{exec.phase}</span>
                  <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${style.badge}`}>{exec.status}</span>
                  {exec.duration_seconds !== null && exec.duration_seconds !== undefined && <span className="text-gray-400 text-sm">({formatDuration(exec.duration_seconds)})</span>}
                  {exec.model_used && <span className="text-purple-400 text-sm">{exec.model_used}</span>}
                </div>
                <div className="mt-2 grid grid-cols-1 gap-2 text-xs text-gray-400 md:grid-cols-3">
                  <div><span className="text-gray-500">Started:</span> {formatDateTime(exec.started_at)}</div>
                  <div><span className="text-gray-500">Completed:</span> {formatDateTime(exec.completed_at)}</div>
                  <div><span className="text-gray-500">Attempt:</span> {exec.attempt ?? '-'}</div>
                </div>
                {exec.command_line && <pre className="mt-2 overflow-x-auto rounded bg-gray-950 px-3 py-2 text-xs text-gray-300">{exec.command_line}</pre>}
              </button>
            );
          })}
        </div>
      ) : (
        <div className="rounded border border-gray-800 bg-gray-950 p-6 text-center text-gray-500">No phase executions yet.</div>
      )}
    </section>
  );
}

function EnvRowsEditor({ initialEnv, onSave, title, description }) {
  const [rows, setRows] = useState([{ key: '', value: '' }]);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const entries = Object.entries(initialEnv || {}).map(([key, value]) => ({ key, value: String(value ?? '') }));
    setRows(entries.length ? entries : [{ key: '', value: '' }]);
    setMessage('');
  }, [JSON.stringify(initialEnv || {})]);

  const updateRow = (index, field, value) => {
    setRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row));
  };

  const addRow = () => setRows((current) => [...current, { key: '', value: '' }]);
  const removeRow = (index) => setRows((current) => {
    const next = current.filter((_, rowIndex) => rowIndex !== index);
    return next.length ? next : [{ key: '', value: '' }];
  });

  const save = async () => {
    try {
      const env = {};
      for (const row of rows) {
        const key = row.key.trim();
        if (!key && !row.value.trim()) continue;
        if (!key) throw new Error('Every value must have a variable name.');
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) throw new Error(`${key} is not a valid environment variable name.`);
        env[key] = row.value;
      }
      await onSave(env);
      setMessage('Environment saved.');
    } catch (error) {
      setMessage(`Save failed: ${error.message}`);
    }
  };

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-950/70 p-4">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <h3 className="font-semibold">{title}</h3>
          <p className="mt-1 text-xs text-gray-500">{description}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={addRow} className="rounded bg-gray-800 px-3 py-1 text-sm hover:bg-gray-700">Add Row</button>
          <button onClick={save} className="rounded bg-blue-600 px-3 py-1 text-sm font-semibold hover:bg-blue-500">Save</button>
        </div>
      </div>
      {message && <div className="mb-3 rounded bg-gray-900 px-3 py-2 text-xs text-gray-300">{message}</div>}
      <div className="space-y-3">
        {rows.map((row, index) => (
          <div key={index} className="rounded border border-gray-800 bg-gray-950 p-3">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-[10px] uppercase tracking-wide text-gray-500">Variable</label>
                <input value={row.key} onChange={(event) => updateRow(index, 'key', event.target.value)} className="h-24 w-full rounded border border-gray-800 bg-gray-900 px-3 py-2 font-mono text-xs text-gray-200" placeholder="PROMPT_EXTRA" />
              </div>
              <div>
                <label className="mb-1 block text-[10px] uppercase tracking-wide text-gray-500">Value</label>
                <textarea value={row.value} onChange={(event) => updateRow(index, 'value', event.target.value)} spellCheck={false} className="h-24 w-full rounded border border-gray-800 bg-gray-900 px-3 py-2 font-mono text-xs text-gray-200" placeholder="Long mini-prompt or env value..." />
              </div>
            </div>
            <div className="mt-2 flex justify-end">
              <button onClick={() => removeRow(index)} className="rounded bg-red-900/50 px-3 py-1.5 text-xs text-red-200 hover:bg-red-800/70">Remove</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ConfigEditor({ audit, onRefresh }) {
  const [ymlContent, setYmlContent] = useState(audit?.codecome_yml || '');
  const [saving, setSaving] = useState(false);
  
  const handleSave = async () => {
    setSaving(true);
    try {
      await auditsApi.update(audit.id, { codecome_yml: ymlContent });
      await onRefresh?.();
    } catch (error) {
      alert(`Failed to save: ${error.message}`);
    } finally {
      setSaving(false);
    }
  };
  
  return (
    <div>
      <div className="mb-6">
        <EnvRowsEditor
          title="Audit-level Environment Overrides"
          description="Applied to every CodeCome command in this audit. Phase-specific variables override these values."
          initialEnv={audit?.model_settings?.__audit_env?.env || {}}
          onSave={async (env) => {
            const nextSettings = { ...(audit.model_settings || {}) };
            nextSettings.__audit_env = { ...(nextSettings.__audit_env || {}), env };
            await auditsApi.update(audit.id, { model_settings: nextSettings });
            await onRefresh?.();
          }}
        />
      </div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">codecome.yml</h3>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 text-white text-sm rounded"
        >
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
      <textarea
        value={ymlContent}
        onChange={(e) => setYmlContent(e.target.value)}
        className="w-full h-96 bg-gray-950 text-gray-300 font-mono text-sm px-4 py-3 rounded border border-gray-700"
        spellCheck={false}
      />
    </div>
  );
}

function ToggleSwitch({ checked, disabled, onChange }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-7 w-12 flex-shrink-0 overflow-hidden rounded-full border transition ${
        checked
          ? 'border-cyan-500 bg-cyan-500/40 shadow-lg shadow-cyan-950/40'
          : 'border-gray-700 bg-gray-800'
      } ${disabled ? 'cursor-not-allowed opacity-60' : 'hover:border-cyan-400'}`}
      aria-pressed={checked}
    >
      <span
        className={`absolute left-1 top-1 h-5 w-5 rounded-full bg-white shadow transition-transform ${
          checked ? 'translate-x-5' : 'translate-x-0'
        }`}
      />
    </button>
  );
}

function InfoItem({ label, value, mono = false }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-950/70 p-3">
      <div className="text-[10px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`mt-1 min-w-0 break-words text-sm text-gray-200 ${mono ? 'font-mono text-xs leading-5' : ''}`}>
        {value || '-'}
      </div>
    </div>
  );
}

function AuditOverview({ audit, onRefresh }) {
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [sandboxStarting, setSandboxStarting] = useState(false);
  const [users, setUsers] = useState([]);

  useEffect(() => {
    usersApi.list({ active: true, limit: 500 })
      .then((data) => setUsers(data.users || []))
      .catch(() => setUsers([]));
  }, []);

  const updateAudit = async (changes) => {
    setSaving(true);
    setMessage('');
    try {
      await auditsApi.update(audit.id, changes);
      await onRefresh?.();
      setMessage('Audit settings saved.');
    } catch (error) {
      setMessage(`Save failed: ${error.message}`);
    } finally {
      setSaving(false);
    }
  };

  const envCount = Object.keys(audit.model_settings?.__audit_env?.env || {}).length;
  const auditOptions = audit.model_settings?.__audit_options || {};

  const updateAuditOption = async (key, value) => {
    const nextSettings = { ...(audit.model_settings || {}) };
    nextSettings.__audit_options = { ...(nextSettings.__audit_options || {}), [key]: value };
    await updateAudit({ model_settings: nextSettings });
  };

  const startSandbox = async () => {
    setSandboxStarting(true);
    setMessage('');
    try {
      const result = await auditsApi.startSandbox(audit.id);
      setMessage(`Sandbox command finished with exit code ${result.exit_code}: ${result.command}`);
    } catch (error) {
      setMessage(`Sandbox start failed: ${error.message}`);
    } finally {
      setSandboxStarting(false);
    }
  };

  return (
    <div className="space-y-6">
      {message && <div className="rounded bg-gray-700 px-3 py-2 text-sm text-gray-200">{message}</div>}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="vortex-stat-blue rounded-xl p-5 text-white">
          <div className="text-sm font-semibold text-white/80">Status</div>
          <div className="mt-2 break-words text-2xl font-bold">{audit.status}</div>
        </div>
        <div className="vortex-stat-green rounded-xl p-5 text-white">
          <div className="text-sm font-semibold text-white/80">Current Phase</div>
          <div className="mt-2 break-words text-2xl font-bold">{audit.current_phase || 'None'}</div>
        </div>
        <div className="vortex-stat-amber rounded-xl p-5 text-white">
          <div className="text-sm font-semibold text-white/80">Worker</div>
          <div className="mt-2 text-2xl font-bold">{audit.assigned_worker_id || 'Auto'}</div>
        </div>
        <div className="vortex-stat-red rounded-xl p-5 text-white">
          <div className="text-sm font-semibold text-white/80">Findings</div>
          <div className="mt-2 text-2xl font-bold">{audit.total_findings}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="vortex-card rounded-xl p-5">
          <h3 className="text-lg font-semibold">Execution Controls</h3>
          <div className="mt-4 space-y-4">
            <div className="flex items-center justify-between gap-4 rounded-xl border border-gray-800 bg-gray-950/70 px-4 py-4">
              <div>
                <div className="font-semibold">Auto-continue between phases</div>
                <div className="text-sm text-gray-500">When enabled, CodeCome automatically advances to the next required command after success.</div>
              </div>
              <ToggleSwitch
                checked={!!audit.auto_continue}
                disabled={saving}
                onChange={(value) => updateAudit({ auto_continue: value })}
              />
            </div>

            {audit.auto_continue && (
              <div className="ml-4 rounded-xl border border-cyan-900/50 bg-cyan-950/20 px-4 py-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="font-semibold text-cyan-100">Include optional make sweep</div>
                    <div className="text-sm text-cyan-200/70">When auto-continue is enabled, run <code>make sweep</code> after <code>make phase-2</code> before continuing to <code>make phase-3</code>.</div>
                  </div>
                  <ToggleSwitch
                    checked={!!auditOptions.run_sweep_auto}
                    disabled={saving}
                    onChange={(value) => updateAuditOption('run_sweep_auto', value)}
                  />
                </div>
              </div>
            )}

            <div className="flex items-center justify-between gap-4 rounded-xl border border-gray-800 bg-gray-950/70 px-4 py-4">
              <div>
                <div className="font-semibold">Auto-triage failed phases</div>
                <div className="text-sm text-gray-500">When enabled, failed phases queue an OpenCode triage report with a recommended next action. Decisions still require manual apply.</div>
              </div>
              <ToggleSwitch
                checked={auditOptions.failure_triage_enabled !== false}
                disabled={saving}
                onChange={(value) => updateAuditOption('failure_triage_enabled', value)}
              />
            </div>

            <div className="rounded-xl border border-gray-800 bg-gray-950/70 px-4 py-4">
              <div className="mb-2">
                <div className="font-semibold">Question owner</div>
                <div className="text-sm text-gray-500">Blocking phase questions are assigned here. Fake AI users auto-answer and allow auto-continue.</div>
              </div>
              <select
                value={audit.question_owner_user_id || ''}
                disabled={saving}
                onChange={(event) => updateAudit({ question_owner_user_id: event.target.value ? Number(event.target.value) : null })}
                className="w-full rounded border border-gray-800 bg-gray-900 px-3 py-2 text-sm text-gray-200"
              >
                <option value="">No owner</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>{user.display_name} ({user.is_llm_user ? 'AI' : 'Human'})</option>
                ))}
              </select>
            </div>

            <div className="flex items-center justify-between gap-4 rounded-xl border border-gray-800 bg-gray-950/70 px-4 py-4">
              <div>
                <div className="font-semibold">Sandbox</div>
                <div className="text-sm text-gray-500">Run the audit workspace sandbox startup command from <code>codecome.yml</code>.</div>
              </div>
              <button onClick={startSandbox} disabled={sandboxStarting} className="rounded bg-cyan-700 px-3 py-2 text-sm font-semibold text-white hover:bg-cyan-600 disabled:cursor-not-allowed disabled:bg-gray-700">
                {sandboxStarting ? 'Starting...' : 'Launch Sandbox'}
              </button>
            </div>

          </div>
        </div>

        <div className="vortex-card rounded-xl p-5">
          <h3 className="text-lg font-semibold">Audit Configuration Summary</h3>
          <div className="mt-4 grid grid-cols-1 gap-3">
            <InfoItem label="Source type" value={audit.source_type || '-'} />
            <InfoItem label="Source location" value={audit.source_location || '-'} mono />
            <InfoItem label="Workspace" value={audit.workspace_path} mono />
            <div className="grid grid-cols-2 gap-3">
              <InfoItem label="Audit env variables" value={envCount} />
              <InfoItem label="Has codecome.yml" value={audit.has_codecome_yml ? 'yes' : 'no'} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function AuditDetails() {
  const { id } = useParams();
  const { audit, loading, refetch } = useAudit(id);
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedPhase, setSelectedPhase] = useState('make init');
  const [selectedExecutionId, setSelectedExecutionId] = useState(null);
  const [phaseSelectedByUser, setPhaseSelectedByUser] = useState(false);
  const [phaseActionMessage, setPhaseActionMessage] = useState('');
  const [questionSummary, setQuestionSummary] = useState({ open: 0, blocking: 0 });

  const loadQuestionSummary = async () => {
    if (!id) return;
    try {
      const data = await questionsApi.list({ audit_id: id });
      const questions = data.questions || [];
      setQuestionSummary({
        open: questions.filter((question) => question.status === 'OPEN').length,
        blocking: questions.filter((question) => question.status === 'OPEN' && question.blocking).length,
      });
    } catch (_) {
      setQuestionSummary({ open: 0, blocking: 0 });
    }
  };

  useEffect(() => {
    if (!audit) return;
    if (phaseSelectedByUser) return;
    if ((audit.phase_executions || []).some((phase) => phase.phase === selectedPhase)) return;
    const currentStep = auditSteps.find((step) => audit.status?.startsWith(step.statusPrefix));
    if (currentStep) {
      setSelectedPhase(currentStep.key);
      setSelectedExecutionId(null);
      return;
    }
    const firstExecution = audit.phase_executions?.[0];
    if (firstExecution) {
      setSelectedPhase(firstExecution.phase);
      setSelectedExecutionId(firstExecution.id);
      return;
    }
    setSelectedPhase('make init');
    setSelectedExecutionId(null);
  }, [audit, phaseSelectedByUser, selectedPhase]);

  useEffect(() => {
    loadQuestionSummary();
  }, [id, audit?.updated_at, audit?.status]);
  
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
      </div>
    );
  }
  
  if (!audit) {
    return <div className="text-gray-400">Audit not found</div>;
  }
  
  const tabs = [
    { key: 'overview', label: 'Overview' },
    { key: 'currentPhase', label: 'Current Phase' },
    { key: 'phaseHistory', label: 'Phase History' },
    { key: 'logs', label: 'Live Logs' },
    { key: 'findings', label: 'Findings' },
    { key: 'questions', label: 'Questions' },
    { key: 'config', label: 'Config' },
  ];
  
  const isRunning = audit.status.includes('_running');
  const canPause = isRunning;
  const hasBlockingQuestions = questionSummary.blocking > 0;
  const canStart = !isRunning && audit.status !== 'completed' && !hasBlockingQuestions;
  const canContinue = audit.status.includes('_complete') && !hasBlockingQuestions;

  const rerunSelectedPhase = async (execution) => {
    if (!execution) return;
    setPhaseActionMessage('');
    try {
      const response = await phasesApi.retry(execution.id);
      setPhaseActionMessage(response.message || 'Phase rerun queued');
      await refetch();
    } catch (error) {
      setPhaseActionMessage(`Rerun failed: ${error.message}`);
    }
  };

  const savePhaseEnv = async (phase, env) => {
    const nextSettings = { ...(audit.model_settings || {}) };
    nextSettings[phase] = { ...(nextSettings[phase] || {}), env };
    await auditsApi.update(id, { model_settings: nextSettings });
    await refetch();
  };

  const runOptionalPhase = async (phase) => {
    setPhaseActionMessage('');
    try {
      const response = await auditsApi.runPhase(id, phase);
      setPhaseActionMessage(response.message || `${phase} queued`);
      await refetch();
    } catch (error) {
      setPhaseActionMessage(`Run failed: ${error.message}`);
    }
  };

  const auditWithActions = { ...audit, onRunOptionalPhase: runOptionalPhase, onRefresh: refetch };
  
  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold">{audit.name}</h2>
            <StatusBadge status={audit.status} />
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full border border-gray-700 bg-gray-900 px-2.5 py-1 text-gray-300">
              Phase: <span className="text-white">{audit.current_phase || 'None'}</span>
            </span>
            <span className="rounded-full border border-gray-700 bg-gray-900 px-2.5 py-1 text-gray-300">
              Worker: <span className="text-white">{audit.assigned_worker_id || 'Auto'}</span>
            </span>
            <span className="rounded-full border border-gray-700 bg-gray-900 px-2.5 py-1 text-gray-300">
              Findings: <span className="text-white">{audit.total_findings}</span>
            </span>
            <span className={`rounded-full border px-2.5 py-1 text-gray-300 ${questionSummary.open ? 'border-amber-700 bg-amber-950/40' : 'border-gray-700 bg-gray-900'}`}>
              Questions: <span className="text-white">{questionSummary.open}</span>
            </span>
            <span className={`rounded-full border px-2.5 py-1 text-gray-300 ${questionSummary.blocking ? 'border-red-700 bg-red-950/40' : 'border-gray-700 bg-gray-900'}`}>
              Blocking: <span className="text-white">{questionSummary.blocking}</span>
            </span>
            <span className="rounded-full border border-gray-700 bg-gray-900 px-2.5 py-1 text-gray-300">
              Owner: <span className="text-white">{audit.question_owner_name ? `${audit.question_owner_name} (${audit.question_owner_is_llm ? 'AI' : 'Human'})` : 'None'}</span>
            </span>
            <span className="rounded-full border border-gray-700 bg-gray-900 px-2.5 py-1 text-gray-300">
              Auto: <span className="text-white">{audit.auto_continue ? 'yes' : 'no'}</span>
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          {canStart && (
            <button
              onClick={() => auditsApi.start(id)}
              className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded font-semibold"
            >
              {audit.status.includes('_failed') ? 'Retry / Continue' : 'Start'}
            </button>
          )}
          {canContinue && (
            <button
              onClick={() => auditsApi.start(id)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded font-semibold"
            >
              Continue
            </button>
          )}
          {!isRunning && audit.status !== 'completed' && hasBlockingQuestions && (
            <button
              onClick={() => setActiveTab('questions')}
              className="px-4 py-2 bg-amber-700 hover:bg-amber-600 text-white rounded font-semibold"
            >
              Answer Questions
            </button>
          )}
          {canPause && (
            <button
              onClick={() => auditsApi.pause(id)}
              className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 text-white rounded font-semibold"
            >
              Pause
            </button>
          )}
        </div>
      </div>
      
      <PhaseProgress audit={auditWithActions} selectedPhase={selectedPhase} onSelectPhase={(phase) => {
        setSelectedPhase(phase);
        setSelectedExecutionId(null);
        setPhaseSelectedByUser(true);
        setActiveTab('currentPhase');
      }} />
      
      <div className="mb-4">
        <div className="flex gap-2">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 rounded font-semibold ${
                activeTab === tab.key
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      
      <div className={(activeTab === 'overview' || activeTab === 'currentPhase') ? 'space-y-6' : 'vortex-card rounded-xl p-5'}>
        {activeTab === 'overview' && (
          <AuditOverview audit={audit} onRefresh={refetch} />
        )}

        {activeTab === 'currentPhase' && (
          <div>
            {phaseActionMessage && (
              <div className="mb-4 rounded bg-gray-700 px-3 py-2 text-sm text-gray-200">{phaseActionMessage}</div>
            )}
            <SelectedPhasePanel audit={auditWithActions} selectedPhase={selectedPhase} selectedExecutionId={selectedExecutionId} onRerun={rerunSelectedPhase} onSaveEnv={savePhaseEnv} />

          </div>
        )}

        {activeTab === 'phaseHistory' && (
          <PhaseHistory audit={audit} selectedPhase={selectedPhase} selectedExecutionId={selectedExecutionId} onSelectExecution={(execution) => {
            setSelectedPhase(execution.phase);
            setSelectedExecutionId(execution.id);
            setPhaseSelectedByUser(true);
            setActiveTab('currentPhase');
          }} />
        )}
        
        {activeTab === 'logs' && <LiveLogs auditId={id} />}
        {activeTab === 'findings' && <FindingsList auditId={id} />}
        {activeTab === 'questions' && <AuditQuestions auditId={id} auditStatus={audit.status} onRefreshSummary={loadQuestionSummary} />}
        {activeTab === 'config' && <ConfigEditor audit={audit} onRefresh={refetch} />}
      </div>
    </div>
  );
}
