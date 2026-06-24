import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link, NavLink } from 'react-router-dom';
import Dashboard from './components/Dashboard';
import AllFindings from './components/AllFindings';
import AuditCreator from './components/AuditCreator';
import AuditDetails from './components/AuditDetails';
import FindingDetails from './components/FindingDetails';
import PreviewAnalysis from './components/PreviewAnalysis';
import Workers from './components/Workers';
import WorkerDetails from './components/WorkerDetails';

function CodeComeLogo({ className = 'h-7 w-7' }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="none" aria-hidden="true">
      <path d="M12 18L32 7l20 11v27L32 57 12 45V18z" fill="url(#logoGradient)" />
      <path d="M23 24l-7 8 7 8M41 24l7 8-7 8M36 20L28 44" stroke="white" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      <defs>
        <linearGradient id="logoGradient" x1="10" y1="8" x2="54" y2="56" gradientUnits="userSpaceOnUse">
          <stop stopColor="#3b82f6" />
          <stop offset="1" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
    </svg>
  );
}

function Icon({ name, className = 'h-6 w-6' }) {
  const common = { className, fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', viewBox: '0 0 24 24', 'aria-hidden': true };
  if (name === 'plus') {
    return <svg {...common}><path d="M12 5v14M5 12h14" /></svg>;
  }
  if (name === 'audits') {
    return <svg {...common}><path d="M4 4h16v16H4z" /><path d="M8 9h8M8 13h5M8 17h8" /></svg>;
  }
  if (name === 'workers') {
    return <svg {...common}><rect x="3" y="4" width="18" height="6" rx="2" /><rect x="3" y="14" width="18" height="6" rx="2" /><path d="M7 7h.01M7 17h.01M11 7h6M11 17h6" /></svg>;
  }
  if (name === 'findings') {
    return <svg {...common}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5M11 8v3l2 2" /></svg>;
  }
  if (name === 'preview') {
    return <svg {...common}><path d="M4 5h16v14H4z" /><path d="M8 9h8M8 13h5M16 13l2 2-2 2" /></svg>;
  }
  return null;
}

function App() {
  const navLinkClass = ({ isActive }) =>
    `group/item flex items-center gap-4 rounded-lg px-3 py-3 text-sm font-semibold transition-colors ${
      isActive
        ? 'bg-slate-700 text-white shadow-lg shadow-black/30'
        : 'text-slate-300 hover:bg-slate-700/70 hover:text-white'
    }`;

  return (
    <BrowserRouter>
      <div className="min-h-screen text-slate-100">
        <aside className="group fixed inset-y-0 left-0 z-10 flex w-20 flex-col overflow-hidden border-r border-slate-800 bg-slate-900/95 px-3 py-5 shadow-2xl transition-all duration-300 hover:w-72">
          <Link to="/" className="mb-7 flex h-14 items-center gap-4 px-2">
            <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-400 text-xl font-black text-white shadow-lg shadow-blue-950/50">
              <CodeComeLogo />
            </div>
            <div className="min-w-0 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
              <div className="whitespace-nowrap text-xl font-bold text-white">CodeCome</div>
              <div className="mt-0.5 whitespace-nowrap text-[10px] uppercase tracking-[0.28em] text-slate-500">Control Plane</div>
            </div>
          </Link>

          <Link
            to="/audit/create"
            className="mb-5 flex items-center gap-4 rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500 px-3 py-3 text-sm font-bold text-white shadow-lg shadow-blue-950/50 transition hover:shadow-xl"
          >
            <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-white/15"><Icon name="plus" className="h-5 w-5" /></span>
            <span className="whitespace-nowrap opacity-0 transition-opacity duration-200 group-hover:opacity-100">New Audit</span>
          </Link>

          <nav className="space-y-2">
            <NavLink to="/" end className={navLinkClass}>
              <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center"><Icon name="audits" /></span>
              <span className="whitespace-nowrap opacity-0 transition-opacity duration-200 group-hover:opacity-100">Audits</span>
            </NavLink>
            <NavLink to="/workers" className={navLinkClass}>
              <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center"><Icon name="workers" /></span>
              <span className="whitespace-nowrap opacity-0 transition-opacity duration-200 group-hover:opacity-100">Workers</span>
            </NavLink>
            <NavLink to="/findings" className={navLinkClass}>
              <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center"><Icon name="findings" /></span>
              <span className="whitespace-nowrap opacity-0 transition-opacity duration-200 group-hover:opacity-100">Findings</span>
            </NavLink>
            <NavLink to="/preview" className={navLinkClass}>
              <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center"><Icon name="preview" /></span>
              <span className="whitespace-nowrap opacity-0 transition-opacity duration-200 group-hover:opacity-100">Preview Analysis</span>
            </NavLink>
          </nav>

          <div className="mt-8 rounded-xl border border-slate-800 bg-slate-950/80 p-4 text-xs text-slate-400 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
            <div className="font-semibold text-slate-300">Execution Model</div>
            <div className="mt-2">DBs in Docker. Scans on native workers.</div>
          </div>

          <div className="mt-auto whitespace-nowrap text-xs text-slate-600 opacity-0 transition-opacity duration-200 group-hover:opacity-100">CodeCome Web v1.0.0</div>
        </aside>

        <main className="ml-20 min-h-screen p-8 transition-all duration-300">
          <div className="mx-auto max-w-screen-2xl">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/findings" element={<AllFindings />} />
              <Route path="/preview" element={<PreviewAnalysis />} />
              <Route path="/workers" element={<Workers />} />
              <Route path="/workers/:id" element={<WorkerDetails />} />
              <Route path="/audit/create" element={<AuditCreator />} />
              <Route path="/audit/:id" element={<AuditDetails />} />
              <Route path="/audit/:auditId/findings/:findingId" element={<FindingDetails />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
