import React, { useEffect, useState } from 'react';
import { questionsApi } from '../services/api';
import { formatSpainDateTime } from '../utils/dates';

const statusStyles = {
  OPEN: 'border-amber-600/50 bg-amber-500/15 text-amber-200',
  ANSWERED: 'border-green-600/50 bg-green-500/15 text-green-200',
  AUTO_ANSWERED: 'border-cyan-600/50 bg-cyan-500/15 text-cyan-200',
  DISMISSED: 'border-gray-700 bg-gray-800 text-gray-300',
};

function QuestionCard({ question, onChanged }) {
  const [answer, setAnswer] = useState(question.answer || '');
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);

  const saveAnswer = async () => {
    setSaving(true);
    setMessage('');
    try {
      await questionsApi.answer(question.id, { answer, status: 'ANSWERED' });
      setMessage('Answer saved.');
      await onChanged?.();
    } catch (error) {
      setMessage(`Save failed: ${error.message}`);
    } finally {
      setSaving(false);
    }
  };

  const dismiss = async () => {
    setSaving(true);
    setMessage('');
    try {
      await questionsApi.dismiss(question.id);
      setMessage('Question dismissed.');
      await onChanged?.();
    } catch (error) {
      setMessage(`Dismiss failed: ${error.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-950/70 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-cyan-300">#{question.id}</span>
        <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${statusStyles[question.status] || statusStyles.OPEN}`}>{question.status}</span>
        {question.blocking && <span className="rounded-full border border-red-800 bg-red-500/15 px-2 py-0.5 text-xs text-red-200">blocking</span>}
        <span className="text-xs text-gray-500">{question.phase}</span>
        <span className="text-xs text-gray-500">{formatSpainDateTime(question.created_at)}</span>
      </div>
      <div className="mt-3 text-sm font-semibold text-gray-100">{question.question}</div>
      {question.context && <div className="mt-2 text-xs text-gray-400">{question.context}</div>}
      {question.status === 'OPEN' ? (
        <div className="mt-3 space-y-2">
          <textarea
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            className="h-28 w-full rounded border border-gray-800 bg-gray-900 px-3 py-2 text-sm text-gray-200"
            placeholder="Answer this question for future phases..."
          />
          <div className="flex gap-2">
            <button onClick={saveAnswer} disabled={saving || !answer.trim()} className="rounded bg-green-700 px-3 py-1.5 text-sm font-semibold hover:bg-green-600 disabled:cursor-not-allowed disabled:bg-gray-700">Save Answer</button>
            <button onClick={dismiss} disabled={saving} className="rounded bg-gray-800 px-3 py-1.5 text-sm hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60">Dismiss</button>
          </div>
        </div>
      ) : (
        <div className="mt-3 rounded border border-gray-800 bg-gray-900 p-3 text-sm text-gray-300">
          {question.answer || 'No answer recorded.'}
        </div>
      )}
      {message && <div className="mt-2 text-xs text-gray-400">{message}</div>}
    </div>
  );
}

export default function AuditQuestions({ auditId, phaseExecutionId = null }) {
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const data = await questionsApi.list({ audit_id: auditId, phase_execution_id: phaseExecutionId });
      setQuestions(data.questions || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [auditId, phaseExecutionId]);

  const openCount = questions.filter((question) => question.status === 'OPEN').length;
  const blockingCount = questions.filter((question) => question.status === 'OPEN' && question.blocking).length;

  return (
    <section className="vortex-card rounded-xl p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">Questions</h3>
          <p className="text-sm text-gray-500">User decisions captured from phase output.</p>
        </div>
        <div className="flex gap-2 text-xs">
          <span className="rounded-full bg-amber-500/15 px-2 py-1 text-amber-200">open {openCount}</span>
          <span className="rounded-full bg-red-500/15 px-2 py-1 text-red-200">blocking {blockingCount}</span>
          <button onClick={load} className="rounded bg-gray-800 px-3 py-1 text-gray-200 hover:bg-gray-700">Refresh</button>
        </div>
      </div>
      {loading ? <div className="text-gray-500">Loading questions...</div> : (
        <div className="space-y-3">
          {questions.map((question) => <QuestionCard key={question.id} question={question} onChanged={load} />)}
          {!questions.length && <div className="rounded border border-gray-800 bg-gray-950 p-6 text-center text-gray-500">No questions captured yet.</div>}
        </div>
      )}
    </section>
  );
}
