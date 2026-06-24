import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { findingsApi } from '../services/api';

const statuses = ['PENDING', 'CONFIRMED', 'EXPLOITED', 'REJECTED', 'DUPLICATE'];
const severities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

function Pill({ active, children, onClick }) {
  return (
    <button onClick={onClick} className={`rounded-full border px-3 py-1 text-xs font-semibold ${active ? 'border-cyan-500 bg-cyan-500/20 text-cyan-200' : 'border-gray-700 bg-gray-900 text-gray-400 hover:text-gray-200'}`}>
      {children}
    </button>
  );
}

function Sev({ value }) {
  const cls = {
    CRITICAL: 'text-red-300',
    HIGH: 'text-orange-300',
    MEDIUM: 'text-yellow-300',
    LOW: 'text-blue-300',
    INFO: 'text-gray-300',
  }[value] || 'text-gray-300';
  return <span className={`font-bold ${cls}`}>{value || 'INFO'}</span>;
}

export default function AllFindings() {
  const [auditSearch, setAuditSearch] = useState('');
  const [findings, setFindings] = useState([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState(null);
  const [severity, setSeverity] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const params = { limit: 200 };
      if (status) params.status = status;
      if (severity) params.severity = severity;
      const data = await findingsApi.list(null, params);
      setFindings(data.findings || []);
      setTotal(data.total || 0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [status, severity]);

  const auditLabel = (finding) => finding.audit_name || finding.audit_id;
  const normalizedAuditSearch = auditSearch.trim().toLowerCase();
  const visibleFindings = normalizedAuditSearch
    ? findings.filter((finding) => {
      return [finding.audit_name, finding.audit_id]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedAuditSearch));
    })
    : findings;
  const visibleTotal = normalizedAuditSearch ? visibleFindings.length : total;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-4xl font-bold">All Findings</h2>
        <p className="mt-1 text-sm text-gray-400">Findings across every audit in the database.</p>
      </div>

      <div className="vortex-panel rounded-xl p-4">
        <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">Audit Search</div>
        <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto]">
          <input
            value={auditSearch}
            onChange={(event) => setAuditSearch(event.target.value)}
            className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200"
            placeholder="Search audit name or ID..."
          />
          {auditSearch && <button onClick={() => setAuditSearch('')} className="rounded-lg bg-gray-800 px-3 py-2 text-sm hover:bg-gray-700">Clear search</button>}
        </div>
        <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">Status</div>
        <div className="flex flex-wrap gap-2">
          <Pill active={!status} onClick={() => setStatus(null)}>All</Pill>
          {statuses.map((item) => <Pill key={item} active={status === item} onClick={() => setStatus(item)}>{item}</Pill>)}
        </div>
        <div className="mb-2 mt-4 text-xs uppercase tracking-wide text-gray-500">Severity</div>
        <div className="flex flex-wrap gap-2">
          <Pill active={!severity} onClick={() => setSeverity(null)}>All</Pill>
          {severities.map((item) => <Pill key={item} active={severity === item} onClick={() => setSeverity(item)}>{item}</Pill>)}
        </div>
      </div>

      <div className="vortex-card rounded-xl p-5">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Findings ({visibleTotal})</h3>
          <button onClick={load} className="rounded bg-gray-800 px-3 py-2 text-sm hover:bg-gray-700">Refresh</button>
        </div>
        {loading ? <div className="text-gray-400">Loading...</div> : (
          <div className="space-y-2">
            {visibleFindings.map((finding) => (
            <Link key={`${finding.audit_id}-${finding.id}`} to={`/audit/${finding.audit_id}/findings/${finding.id}`} className="block rounded-lg border border-gray-800 bg-gray-950/70 p-3 hover:border-cyan-700/70 hover:bg-gray-900">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-cyan-300">{finding.id}</span>
                  <span className="rounded-full bg-gray-800 px-2 py-0.5 text-xs text-gray-300">{finding.status}</span>
                  <Sev value={finding.severity} />
                  <span className="truncate text-gray-200">{finding.title}</span>
                </div>
                <div className="mt-1 truncate text-xs text-gray-500">Audit {auditLabel(finding)} · {finding.category || 'uncategorized'} · {finding.file_path || 'no file'}</div>
              </Link>
            ))}
            {!visibleFindings.length && <div className="text-center text-gray-500">No findings match the filters.</div>}
          </div>
        )}
      </div>
    </div>
  );
}
