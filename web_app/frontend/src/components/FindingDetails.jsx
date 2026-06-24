import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { findingsApi } from '../services/api';
import { formatSpainDateTime } from '../utils/dates';

const statuses = ['PENDING', 'CONFIRMED', 'EXPLOITED', 'REJECTED', 'DUPLICATE'];
const severities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const confidences = ['LOW', 'MEDIUM', 'HIGH', 'CONFIRMED'];

function Chip({ children, tone = 'gray' }) {
  const tones = {
    gray: 'border-gray-700 bg-gray-800 text-gray-300',
    red: 'border-red-700/60 bg-red-500/15 text-red-300',
    orange: 'border-orange-700/60 bg-orange-500/15 text-orange-300',
    yellow: 'border-yellow-700/60 bg-yellow-500/15 text-yellow-300',
    blue: 'border-blue-700/60 bg-blue-500/15 text-blue-300',
    green: 'border-green-700/60 bg-green-500/15 text-green-300',
    purple: 'border-purple-700/60 bg-purple-500/15 text-purple-300',
  };
  return <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${tones[tone] || tones.gray}`}>{children}</span>;
}

function severityTone(severity) {
  if (severity === 'CRITICAL') return 'red';
  if (severity === 'HIGH') return 'orange';
  if (severity === 'MEDIUM') return 'yellow';
  if (severity === 'LOW') return 'blue';
  return 'gray';
}

function formatDate(value) {
  return formatSpainDateTime(value);
}

function timelinePhaseStyle(label) {
  const styles = {
    Hypothesis: {
      card: 'border-cyan-700/50 bg-cyan-950/20 shadow-cyan-950/20',
      dot: 'bg-cyan-300 shadow-cyan-400/40',
      label: 'text-cyan-300',
      status: 'text-cyan-100',
    },
    'Counter-analysis': {
      card: 'border-purple-700/50 bg-purple-950/20 shadow-purple-950/20',
      dot: 'bg-purple-300 shadow-purple-400/40',
      label: 'text-purple-300',
      status: 'text-purple-100',
    },
    Validation: {
      card: 'border-amber-700/50 bg-amber-950/20 shadow-amber-950/20',
      dot: 'bg-amber-300 shadow-amber-400/40',
      label: 'text-amber-300',
      status: 'text-amber-100',
    },
    Exploitation: {
      card: 'border-rose-700/50 bg-rose-950/20 shadow-rose-950/20',
      dot: 'bg-rose-300 shadow-rose-400/40',
      label: 'text-rose-300',
      status: 'text-rose-100',
    },
  };
  return styles[label] || {
    card: 'border-gray-800 bg-gray-950',
    dot: 'bg-gray-500',
    label: 'text-gray-400',
    status: 'text-gray-100',
  };
}

function FindingTimeline({ finding, frontmatter }) {
  const validation = frontmatter.validation || {};
  const exploitation = frontmatter.exploitation || {};
  const createdAt = frontmatter.created_at || finding.created_at;
  const updatedAt = frontmatter.updated_at || finding.updated_at;
  const items = [
    { label: 'Hypothesis', status: finding.status || 'PENDING', time: createdAt, detail: 'Finding created' },
    { label: 'Counter-analysis', status: finding.confidence || 'PENDING', time: updatedAt, detail: 'Last review/update' },
    { label: 'Validation', status: validation.status || (finding.has_evidence ? 'EVIDENCE' : 'NOT_STARTED'), time: updatedAt, detail: validation.summary || validation.evidence_dir || 'No validation evidence yet' },
    { label: 'Exploitation', status: exploitation.status || (finding.has_exploit ? 'EXPLOITED' : 'NOT_STARTED'), time: updatedAt, detail: exploitation.summary || exploitation.artifacts_dir || 'No exploit artifacts yet' },
  ];

  return (
    <div className="mt-4 rounded-xl border border-gray-800 bg-gray-950/60 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-gray-100">Finding Timeline</div>
          <div className="text-xs text-gray-500">Lifecycle phases and associated timestamps</div>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        {items.map((item, index) => (
          <div key={item.label} className={`relative rounded-lg border p-3 shadow-lg ${timelinePhaseStyle(item.label).card}`}>
            {index < items.length - 1 && <div className="absolute left-full top-6 hidden h-px w-3 bg-gradient-to-r from-gray-600 to-transparent md:block" />}
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full shadow-lg ${timelinePhaseStyle(item.label).dot}`}></span>
              <div className={`text-xs font-semibold uppercase tracking-wide ${timelinePhaseStyle(item.label).label}`}>{item.label}</div>
            </div>
            <div className={`mt-2 text-sm font-semibold ${timelinePhaseStyle(item.label).status}`}>{item.status}</div>
            <div className="mt-1 text-xs text-gray-500">{formatDate(item.time)}</div>
            <div className="mt-2 max-h-9 overflow-hidden text-xs text-gray-400">{item.detail}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function markdownComponents() {
  return {
    h1: ({ children }) => <h1 className="mb-4 mt-8 text-3xl font-bold text-white first:mt-0">{children}</h1>,
    h2: ({ children }) => <h2 className="mb-3 mt-8 text-2xl font-bold text-white">{children}</h2>,
    h3: ({ children }) => <h3 className="mb-2 mt-6 text-xl font-semibold text-white">{children}</h3>,
    p: ({ children }) => <p className="mb-4 leading-7 text-gray-300">{children}</p>,
    ul: ({ children }) => <ul className="mb-4 list-disc space-y-1 pl-6 text-gray-300">{children}</ul>,
    ol: ({ children }) => <ol className="mb-4 list-decimal space-y-1 pl-6 text-gray-300">{children}</ol>,
    li: ({ children }) => <li>{children}</li>,
    code: ({ children }) => <code className="break-words rounded bg-gray-950 px-1.5 py-0.5 font-mono text-sm text-cyan-200">{children}</code>,
    pre: ({ children }) => <pre className="mb-4 max-w-full overflow-x-auto whitespace-pre-wrap break-words rounded-lg border border-gray-800 bg-gray-950 p-4 text-sm text-gray-200">{children}</pre>,
    blockquote: ({ children }) => <blockquote className="mb-4 border-l-4 border-cyan-700 pl-4 text-gray-400">{children}</blockquote>,
  };
}

export default function FindingDetails() {
  const { auditId, findingId } = useParams();
  const [finding, setFinding] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reviewForm, setReviewForm] = useState({ status: 'PENDING', severity: 'INFO', confidence: 'LOW', category: '', reviewer_note: '' });
  const [savingReview, setSavingReview] = useState(false);
  const [reviewMessage, setReviewMessage] = useState('');

  const loadFinding = () => {
    setLoading(true);
    setError('');
    findingsApi.get(findingId, auditId)
      .then((data) => {
        setFinding(data);
        setReviewForm({
          status: data.status || 'PENDING',
          severity: data.severity || 'INFO',
          confidence: data.confidence || 'LOW',
          category: data.category || '',
          reviewer_note: '',
        });
      })
      .catch((err) => setError(err.message || 'Failed to load finding'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadFinding();
  }, [auditId, findingId]);

  const saveReview = async () => {
    setSavingReview(true);
    setReviewMessage('');
    try {
      const updated = await findingsApi.update(findingId, auditId, reviewForm);
      setFinding(updated);
      setReviewForm({ ...reviewForm, reviewer_note: '' });
      setReviewMessage('Finding review metadata saved.');
    } catch (err) {
      setReviewMessage(`Save failed: ${err.message}`);
    } finally {
      setSavingReview(false);
    }
  };

  if (loading) return <div className="text-gray-400">Loading finding...</div>;
  if (error) return <div className="rounded bg-red-500/20 p-4 text-red-300">{error}</div>;
  if (!finding) return <div className="text-gray-400">Finding not found.</div>;

  const fm = finding.frontmatter || {};
  const files = fm.files || [];
  const cwes = fm.cwe || [];
  const entryPoints = fm.entry_points || [];
  const symbols = fm.symbols || [];

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/audit/${auditId}`} className="text-sm text-cyan-300 hover:text-cyan-200">Back to audit</Link>
        <div className="mt-3 vortex-card rounded-xl p-6">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm font-bold text-cyan-300">{finding.id}</span>
            <Chip tone="yellow">{finding.status}</Chip>
            <Chip tone={severityTone(finding.severity)}>{finding.severity || 'INFO'}</Chip>
            <Chip tone="purple">{finding.confidence || 'UNKNOWN'}</Chip>
            {finding.category && <Chip>{finding.category}</Chip>}
          </div>
          <h1 className="mt-4 break-words text-3xl font-bold text-white">{finding.title}</h1>
          <div className="mt-4 grid grid-cols-1 gap-3 text-sm md:grid-cols-2 lg:grid-cols-4">
            <div className="rounded bg-gray-950/70 p-3"><div className="text-xs text-gray-500">CWE</div><div className="mt-1 text-gray-200">{cwes.length ? cwes.join(', ') : '-'}</div></div>
            <div className="rounded bg-gray-950/70 p-3"><div className="text-xs text-gray-500">Evidence</div><div className="mt-1 text-gray-200">{finding.has_evidence ? 'Yes' : 'No'}</div></div>
            <div className="rounded bg-gray-950/70 p-3"><div className="text-xs text-gray-500">Exploit</div><div className="mt-1 text-gray-200">{finding.has_exploit ? 'Yes' : 'No'}</div></div>
            <div className="rounded bg-gray-950/70 p-3"><div className="text-xs text-gray-500">Primary File</div><div className="mt-1 break-all text-gray-200">{finding.file_path || '-'}</div></div>
          </div>
          <FindingTimeline finding={finding} frontmatter={fm} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <aside className="space-y-4 lg:col-span-1">
          <div className="vortex-card rounded-xl p-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-semibold">Manual Review</h2>
              <button onClick={saveReview} disabled={savingReview} className="rounded bg-blue-600 px-3 py-1.5 text-xs font-semibold hover:bg-blue-500 disabled:bg-gray-700">
                {savingReview ? 'Saving...' : 'Save'}
              </button>
            </div>
            {reviewMessage && <div className="mt-3 rounded bg-gray-950/70 px-3 py-2 text-xs text-gray-300">{reviewMessage}</div>}
            <div className="mt-3 space-y-3 text-sm">
              <div>
                <label htmlFor="finding-status" className="mb-1 block text-xs text-gray-500">Status</label>
                <select id="finding-status" value={reviewForm.status} onChange={(e) => setReviewForm({ ...reviewForm, status: e.target.value })} className="w-full rounded border border-gray-800 bg-gray-950 px-3 py-2">
                  {statuses.map((status) => <option key={status} value={status}>{status}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="finding-severity" className="mb-1 block text-xs text-gray-500">Severity</label>
                <select id="finding-severity" value={reviewForm.severity} onChange={(e) => setReviewForm({ ...reviewForm, severity: e.target.value })} className="w-full rounded border border-gray-800 bg-gray-950 px-3 py-2">
                  {severities.map((severity) => <option key={severity} value={severity}>{severity}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="finding-confidence" className="mb-1 block text-xs text-gray-500">Confidence</label>
                <select id="finding-confidence" value={reviewForm.confidence} onChange={(e) => setReviewForm({ ...reviewForm, confidence: e.target.value })} className="w-full rounded border border-gray-800 bg-gray-950 px-3 py-2">
                  {confidences.map((confidence) => <option key={confidence} value={confidence}>{confidence}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="finding-category" className="mb-1 block text-xs text-gray-500">Category</label>
                <input id="finding-category" value={reviewForm.category} onChange={(e) => setReviewForm({ ...reviewForm, category: e.target.value })} className="w-full rounded border border-gray-800 bg-gray-950 px-3 py-2" />
              </div>
              <div>
                <label htmlFor="finding-reviewer-note" className="mb-1 block text-xs text-gray-500">Reviewer Note</label>
                <textarea id="finding-reviewer-note" value={reviewForm.reviewer_note} onChange={(e) => setReviewForm({ ...reviewForm, reviewer_note: e.target.value })} className="h-24 w-full rounded border border-gray-800 bg-gray-950 px-3 py-2" placeholder="Why this status changed..." />
              </div>
            </div>
          </div>
          <div className="vortex-card rounded-xl p-4">
            <h2 className="font-semibold">Important Context</h2>
            <div className="mt-3 space-y-3 text-sm">
              <div><div className="text-xs text-gray-500">Entry points</div><div className="mt-1 break-words text-gray-300">{entryPoints.length ? entryPoints.join(', ') : '-'}</div></div>
              <div><div className="text-xs text-gray-500">Symbols</div><div className="mt-1 break-words text-gray-300">{symbols.length ? symbols.slice(0, 8).join(', ') : '-'}</div></div>
              <div><div className="text-xs text-gray-500">Trust boundary</div><div className="mt-1 break-words text-gray-300">{fm.trust_boundary || '-'}</div></div>
            </div>
          </div>
          <div className="vortex-card rounded-xl p-4">
            <h2 className="font-semibold">Files</h2>
            <div className="mt-3 space-y-2">
              {files.length ? files.map((file) => <div key={file} className="break-all rounded bg-gray-950/70 px-3 py-2 font-mono text-xs text-gray-300">{file}</div>) : <div className="text-sm text-gray-500">No files listed</div>}
            </div>
          </div>
        </aside>

        <article className="vortex-card min-w-0 rounded-xl p-6 lg:col-span-2">
          <ReactMarkdown components={markdownComponents()}>{finding.content || 'No content.'}</ReactMarkdown>
        </article>
      </div>
    </div>
  );
}
