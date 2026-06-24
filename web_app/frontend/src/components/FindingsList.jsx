import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { findingsApi } from '../services/api';

const statuses = ['PENDING', 'CONFIRMED', 'EXPLOITED', 'REJECTED', 'DUPLICATE'];
const severities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

function StatusBadge({ status }) {
  const colorMap = {
    PENDING: 'bg-yellow-500/20 text-yellow-300 border-yellow-700/50',
    CONFIRMED: 'bg-blue-500/20 text-blue-300 border-blue-700/50',
    EXPLOITED: 'bg-red-500/20 text-red-300 border-red-700/50',
    REJECTED: 'bg-gray-500/20 text-gray-300 border-gray-700/50',
    DUPLICATE: 'bg-gray-500/20 text-gray-300 border-gray-700/50',
  };
  return <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${colorMap[status] || colorMap.PENDING}`}>{status}</span>;
}

function SeverityBadge({ severity }) {
  const colorMap = {
    CRITICAL: 'bg-red-600/20 text-red-300 border-red-700/60',
    HIGH: 'bg-orange-600/20 text-orange-300 border-orange-700/60',
    MEDIUM: 'bg-yellow-600/20 text-yellow-300 border-yellow-700/60',
    LOW: 'bg-blue-600/20 text-blue-300 border-blue-700/60',
    INFO: 'bg-gray-600/20 text-gray-300 border-gray-700/60',
  };
  return <span className={`rounded-full border px-2 py-0.5 text-xs font-bold ${colorMap[severity] || colorMap.INFO}`}>{severity || 'INFO'}</span>;
}

function FilterPill({ active, children, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
        active
          ? 'border-cyan-500 bg-cyan-500/20 text-cyan-200 shadow-lg shadow-cyan-950/30'
          : 'border-gray-700 bg-gray-900 text-gray-400 hover:border-gray-500 hover:text-gray-200'
      }`}
    >
      {children}
    </button>
  );
}

export default function FindingsList({ auditId }) {
  const [findings, setFindings] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState(null);
  const [severityFilter, setSeverityFilter] = useState(null);

  React.useEffect(() => {
    async function fetchFindings() {
      setLoading(true);
      try {
        const params = {};
        if (statusFilter) params.status = statusFilter;
        if (severityFilter) params.severity = severityFilter;
        const data = await findingsApi.list(auditId, params);
        setFindings(data.findings || []);
        setTotal(data.total || 0);
      } catch (error) {
        console.error('Failed to fetch findings:', error);
      } finally {
        setLoading(false);
      }
    }
    fetchFindings();
  }, [auditId, statusFilter, severityFilter]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-blue-400"></div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xl font-semibold">Findings <span className="text-sm text-gray-400">({total})</span></h3>
            <p className="mt-1 text-sm text-gray-500">Click a finding to open a dedicated report page.</p>
          </div>
          {(statusFilter || severityFilter) && (
            <button onClick={() => { setStatusFilter(null); setSeverityFilter(null); }} className="rounded bg-gray-800 px-3 py-2 text-sm hover:bg-gray-700">
              Clear filters
            </button>
          )}
        </div>

        <div className="vortex-panel rounded-xl p-3">
          <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">Status</div>
          <div className="flex flex-wrap gap-2">
            <FilterPill active={!statusFilter} onClick={() => setStatusFilter(null)}>All</FilterPill>
            {statuses.map((status) => <FilterPill key={status} active={statusFilter === status} onClick={() => setStatusFilter(status)}>{status}</FilterPill>)}
          </div>
          <div className="mb-2 mt-4 text-xs uppercase tracking-wide text-gray-500">Severity</div>
          <div className="flex flex-wrap gap-2">
            <FilterPill active={!severityFilter} onClick={() => setSeverityFilter(null)}>All</FilterPill>
            {severities.map((severity) => <FilterPill key={severity} active={severityFilter === severity} onClick={() => setSeverityFilter(severity)}>{severity}</FilterPill>)}
          </div>
        </div>
      </div>

      {findings.length === 0 ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-8 text-center text-gray-400">
          No findings match the current filters.
        </div>
      ) : (
        <div className="space-y-3">
          {findings.map((finding) => (
            <Link
              key={finding.id}
              to={`/audit/${auditId}/findings/${finding.id}`}
              className="block rounded-xl border border-gray-800 bg-gray-900 p-4 transition hover:-translate-y-0.5 hover:border-cyan-700/70 hover:bg-gray-800 hover:shadow-xl"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm font-bold text-cyan-300">{finding.id}</span>
                <StatusBadge status={finding.status} />
                <SeverityBadge severity={finding.severity} />
                {finding.confidence && <span className="rounded-full border border-purple-700/60 bg-purple-500/10 px-2 py-0.5 text-xs text-purple-300">{finding.confidence}</span>}
              </div>
              <div className="mt-2 font-semibold text-gray-100">{finding.title}</div>
              <div className="mt-1 flex flex-wrap gap-3 text-xs text-gray-500">
                <span>{finding.category || 'Uncategorized'}</span>
                {finding.file_path && <span className="truncate">{finding.file_path}</span>}
                {finding.has_evidence && <span className="text-green-300">evidence</span>}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
