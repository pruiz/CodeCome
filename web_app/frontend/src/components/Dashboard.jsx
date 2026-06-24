import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAudits } from '../hooks/useAudits';
import { auditsApi } from '../services/api';
import { formatSpainDateTime } from '../utils/dates';

function StatusBadge({ status }) {
  const colorMap = {
    'initializing': 'yellow',
    'ready': 'green',
    'phase_1_running': 'blue',
    'phase_2_running': 'blue',
    'phase_3_running': 'blue',
    'phase_4_running': 'blue',
    'phase_5_running': 'blue',
    'phase_6_running': 'blue',
    'phase_1_complete': 'green',
    'phase_2_complete': 'green',
    'phase_3_complete': 'green',
    'phase_4_complete': 'green',
    'phase_5_complete': 'green',
    'phase_6_complete': 'green',
    'completed': 'green',
    'paused': 'orange',
    'phase_1_failed': 'red',
    'phase_2_failed': 'red',
    'phase_3_failed': 'red',
    'phase_4_failed': 'red',
    'phase_5_failed': 'red',
    'phase_6_failed': 'red',
    'failed': 'red',
  };
  
  const color = colorMap[status] || 'gray';
  const bgMap = {
    'yellow': 'bg-yellow-500/20 text-yellow-300',
    'green': 'bg-green-500/20 text-green-300',
    'blue': 'bg-blue-500/20 text-blue-300',
    'orange': 'bg-orange-500/20 text-orange-300',
    'red': 'bg-red-500/20 text-red-300',
    'gray': 'bg-gray-500/20 text-gray-300',
  };
  
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-semibold ${bgMap[color]}`}>
      {status.replace(/_/g, ' ').replace(/-/g, ' ')}
    </span>
  );
}

function AuditCard({ audit, onDelete }) {
  const isRunning = audit.status.includes('_running');
  const canPause = isRunning;
  const canStart = !isRunning && audit.status !== 'completed';
  const canDelete = !isRunning;
  
  return (
    <div className="vortex-card rounded-xl p-5 transition-all hover:-translate-y-0.5 hover:shadow-2xl">
      <div className="flex items-start justify-between mb-3">
        <Link to={`/audit/${audit.id}`} className="text-lg font-semibold text-blue-400 hover:text-blue-300">
          {audit.name}
        </Link>
        <StatusBadge status={audit.status} />
      </div>
      
      <div className="mb-3">
        <div className="text-sm text-gray-400">
          Total Findings: <span className="text-white font-semibold">{audit.total_findings}</span>
        </div>
        <div className="mt-1 text-sm text-gray-400">
          Open Questions: <span className={audit.open_questions ? 'font-semibold text-amber-200' : 'font-semibold text-white'}>{audit.open_questions || 0}</span>
          <span className="mx-2 text-gray-700">/</span>
          Blocking: <span className={audit.blocking_questions ? 'font-semibold text-red-200' : 'font-semibold text-white'}>{audit.blocking_questions || 0}</span>
        </div>
        <div className="flex gap-2 mt-1">
          {audit.findings_by_status && (
            <>
              <span className="text-xs bg-yellow-500/20 text-yellow-300 px-2 py-0.5 rounded">
                Pending: {audit.findings_by_status.PENDING || 0}
              </span>
              <span className="text-xs bg-red-500/20 text-red-300 px-2 py-0.5 rounded">
                Confirmed: {audit.findings_by_status.CONFIRMED || 0}
              </span>
              <span className="text-xs bg-green-500/20 text-green-300 px-2 py-0.5 rounded">
                Exploited: {audit.findings_by_status.EXPLOITED || 0}
              </span>
            </>
          )}
        </div>
      </div>
      
      <div className="flex gap-2">
        {canStart && (
          <button
            onClick={() => auditsApi.start(audit.id).then(() => window.location.reload())}
            className="px-3 py-1 bg-green-600 hover:bg-green-500 text-white text-sm rounded"
          >
            {audit.status.includes('_failed') ? 'Retry / Continue' : 'Start'}
          </button>
        )}
        {canPause && (
          <button
            onClick={() => auditsApi.pause(audit.id).then(() => window.location.reload())}
            className="px-3 py-1 bg-yellow-600 hover:bg-yellow-500 text-white text-sm rounded"
          >
            Pause
          </button>
        )}
        {canDelete && (
          <button
            onClick={() => {
              if (window.confirm(`Delete audit "${audit.name}"? This cannot be undone.`)) {
                onDelete(audit.id);
              }
            }}
            className="px-3 py-1 bg-red-600 hover:bg-red-500 text-white text-sm rounded"
          >
            Delete
          </button>
        )}
      </div>
      
      <div className="mt-2 text-xs text-gray-500">
        Created: {formatSpainDateTime(audit.created_at)}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { audits, total, loading, refetch } = useAudits(5000);
  const [search, setSearch] = useState('');
  
  const handleDelete = async (id) => {
    await auditsApi.delete(id);
    refetch();
  };

  const normalizedSearch = search.trim().toLowerCase();
  const visibleAudits = normalizedSearch
    ? audits.filter((audit) => [audit.name, audit.id, audit.status, audit.source_location]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalizedSearch)))
    : audits;
  
  return (
    <div>
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h2 className="text-4xl font-bold">Audits</h2>
          <p className="mt-1 text-sm text-slate-400">CodeCome analysis jobs and worker execution state</p>
        </div>
        <Link
          to="/audit/create"
          className="rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500 px-4 py-3 font-semibold text-white shadow-lg shadow-blue-950/50 hover:shadow-xl"
        >
          + Create New Audit
        </Link>
      </div>

      <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
        <div className="vortex-stat-blue rounded-xl p-5 text-white">
          <div className="text-sm font-semibold text-white/80">Total Audits</div>
          <div className="mt-2 text-4xl font-bold">{normalizedSearch ? visibleAudits.length : total}</div>
          <div className="mt-1 text-xs text-white/70">{normalizedSearch ? 'Matching search' : 'Tracked in database'}</div>
        </div>
        <div className="vortex-stat-green rounded-xl p-5 text-white">
          <div className="text-sm font-semibold text-white/80">Completed</div>
          <div className="mt-2 text-4xl font-bold">{visibleAudits.filter((a) => a.status === 'completed').length}</div>
          <div className="mt-1 text-xs text-white/70">Visible finished reports</div>
        </div>
        <div className="vortex-stat-amber rounded-xl p-5 text-white">
          <div className="text-sm font-semibold text-white/80">Running</div>
          <div className="mt-2 text-4xl font-bold">{visibleAudits.filter((a) => a.status.includes('running')).length}</div>
          <div className="mt-1 text-xs text-white/70">Visible active phases</div>
        </div>
        <div className="vortex-stat-red rounded-xl p-5 text-white">
          <div className="text-sm font-semibold text-white/80">Findings</div>
          <div className="mt-2 text-4xl font-bold">{visibleAudits.reduce((sum, audit) => sum + (audit.total_findings || 0), 0)}</div>
          <div className="mt-1 text-xs text-white/70">Across visible audits</div>
        </div>
      </div>

      <div className="vortex-panel mb-6 rounded-xl p-4">
        <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">Search Audits</div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto]">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200"
            placeholder="Search by audit name, ID, status, or source..."
          />
          {search && <button onClick={() => setSearch('')} className="rounded-lg bg-gray-800 px-3 py-2 text-sm hover:bg-gray-700">Clear search</button>}
        </div>
      </div>
       
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
        </div>
      ) : audits.length === 0 ? (
        <div className="vortex-card rounded-xl p-8 text-center">
          <p className="text-gray-400 mb-4">No audits yet. Create your first audit to start a vulnerability research workflow.</p>
          <Link
            to="/audit/create"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-semibold"
          >
            Create New Audit
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {visibleAudits.map(audit => (
            <AuditCard key={audit.id} audit={audit} onDelete={handleDelete} />
          ))}
          {!visibleAudits.length && <div className="vortex-card rounded-xl p-8 text-center text-gray-500">No audits match the search.</div>}
        </div>
      )}
    </div>
  );
}
