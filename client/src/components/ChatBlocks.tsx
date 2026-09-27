import React, { useEffect, useRef, useState } from 'react';
import { Bot, Check, Loader2, MessageSquare, Pencil, X } from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';
import { FeatureStatusBadge, ReviewStatusBadge, TaskCard } from './FeatureCards.js';
import { BackendError, progressLabel } from '../lib/backend.js';
import {
  approvedBoardReady,
  canApproveFeature,
  openQuestionCount,
  openQuestions,
  reviewStatusOf,
} from '../lib/workflow.js';
import {
  ChatMessage,
  Feature,
  GenerationMode,
  GeneratedTask,
  MvpDocument,
} from '../types.js';

export function AiBubble({ children, cite }: { children: React.ReactNode; cite?: string }) {
  return (
    <div className="flex items-start gap-2.5">
      <span className="w-7 h-7 shrink-0 grid place-items-center rounded-full bg-[var(--accent-bg)] text-[var(--accent)] mt-0.5">
        <Bot className="w-4 h-4" />
      </span>
      <div className="space-y-1.5 min-w-0 flex-1">
        <div className="inline-block bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] px-3.5 py-2.5 text-sm text-stone-800 dark:text-stone-200 leading-relaxed">
          {children}
        </div>
        {cite && <div className="text-[10px] font-mono text-stone-400 pl-1">cited: {cite}</div>}
      </div>
    </div>
  );
}

export function PmBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex justify-end">
      <div className="inline-block max-w-[80%] bg-[var(--accent)] text-white rounded-[var(--r-md)] px-3.5 py-2.5 text-sm leading-relaxed">
        {children}
      </div>
    </div>
  );
}

export function HistoryMessage({ msg }: { msg: ChatMessage }) {
  if (msg.role === 'pm') return <PmBubble>{msg.text}</PmBubble>;
  const muted = msg.kind === 'decision' || msg.kind === 'progress';
  return (
    <AiBubble>
      <span className={muted ? 'text-stone-600 dark:text-stone-300' : undefined}>{msg.text}</span>
    </AiBubble>
  );
}

export function IngestProgressBlock({ documents }: { documents: MvpDocument[] }) {
  if (documents.length === 0) {
    return (
      <AiBubble>
        Waiting for your sources to land. I’ll start extracting as soon as a file is uploaded.
      </AiBubble>
    );
  }
  return (
    <div className="space-y-3">
      <AiBubble>I’m reading your sources now. Progress stays here — you don’t need to open Sources.</AiBubble>
      <div className="ml-9 space-y-2">
        {documents.map(doc => (
          <div key={doc.id} className="p-3 rounded-[var(--r-md)] border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-stone-800 dark:text-stone-100 truncate">{doc.filename}</span>
              <span className="text-[10px] font-mono text-stone-400 shrink-0 inline-flex items-center gap-1">
                {doc.status !== 'ready' && doc.status !== 'failed' && <Loader2 className="w-3 h-3 animate-spin" />}
                {doc.status === 'ready' && <Check className="w-3 h-3 text-[var(--verdict-new-txt)]" />}
                {progressLabel(doc)}
              </span>
            </div>
            {doc.progress && doc.progress.total > 0 && doc.status !== 'ready' && doc.status !== 'failed' && (
              <div className="mt-2 h-1.5 rounded-full bg-stone-200 dark:bg-stone-800 overflow-hidden">
                <div className="h-full bg-[var(--accent)]" style={{ width: `${Math.min(100, (doc.progress.done / doc.progress.total) * 100)}%` }} />
              </div>
            )}
            {doc.status === 'failed' && doc.error && (
              <p className="mt-1.5 text-[11px] text-[var(--verdict-conf-txt)]">{doc.error}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function GenerationModePicker({
  title,
  autoHint,
  reviewHint,
  onChoose,
}: {
  title: string;
  autoHint: string;
  reviewHint: string;
  onChoose: (mode: GenerationMode) => void;
}) {
  return (
    <div className="space-y-3">
      <AiBubble>{title}</AiBubble>
      <div className="ml-9 grid sm:grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => onChoose('auto')}
          className="text-left p-3 rounded-[var(--r-md)] border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950 hover:border-[var(--accent)] cursor-pointer"
        >
          <div className="text-sm font-semibold text-stone-800 dark:text-stone-100">Auto</div>
          <p className="mt-1 text-[11px] text-stone-500 dark:text-stone-400 leading-relaxed">{autoHint}</p>
        </button>
        <button
          type="button"
          onClick={() => onChoose('review_as_you_go')}
          className="text-left p-3 rounded-[var(--r-md)] border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950 hover:border-[var(--accent)] cursor-pointer"
        >
          <div className="text-sm font-semibold text-stone-800 dark:text-stone-100">Review as you go</div>
          <p className="mt-1 text-[11px] text-stone-500 dark:text-stone-400 leading-relaxed">{reviewHint}</p>
        </button>
      </div>
    </div>
  );
}

function FeatureQuestionPanel({ feature }: { feature: Feature }) {
  const { answerClarification, skipClarification, skipRemainingQuestions } = useProject();
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = openQuestions(feature);
  const next = open[0] ?? null;

  const run = async (fn: () => Promise<unknown>) => {
    setSending(true);
    setError(null);
    try {
      await fn();
      setInput('');
    } catch (e) {
      setError(e instanceof BackendError ? e.toDisplay() : 'Could not update the question.');
    } finally {
      setSending(false);
    }
  };

  if (open.length === 0) {
    return <p className="text-[11px] text-[var(--verdict-new-txt)]">No open questions — Approve is available.</p>;
  }

  return (
    <div className="space-y-2 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] p-3 bg-stone-50/50 dark:bg-stone-900/30">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-mono uppercase tracking-wider text-stone-400">
          {open.length} open question{open.length === 1 ? '' : 's'}
        </p>
        <button
          type="button"
          disabled={sending}
          onClick={() => run(() => skipRemainingQuestions(feature.id))}
          className="text-[11px] font-medium text-stone-500 hover:text-stone-800 dark:hover:text-stone-200 cursor-pointer disabled:opacity-40"
        >
          Skip remaining
        </button>
      </div>
      {next && (
        <p className="text-xs text-stone-600 dark:text-stone-300">
          <span className="font-medium">{next.question}</span>
          {next.why && <span className="block mt-0.5 text-stone-400">{next.why}</span>}
        </p>
      )}
      {error && <p role="alert" className="text-[11px] text-[var(--verdict-conf-txt)]">{error}</p>}
      <div className="flex items-end gap-2">
        <textarea
          rows={1}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              if (next && input.trim()) void run(() => answerClarification(next.id, input.trim()));
            }
          }}
          placeholder="Type your answer…"
          aria-label="Your answer"
          disabled={sending || !next}
          className="flex-1 resize-none bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)] px-3 py-2 text-sm text-stone-800 dark:text-stone-100 placeholder-stone-400 focus:outline-none focus:border-[var(--accent)] disabled:opacity-50"
        />
        <button
          type="button"
          disabled={!input.trim() || sending || !next}
          onClick={() => { if (next && input.trim()) void run(() => answerClarification(next.id, input.trim())); }}
          className="shrink-0 px-3 py-2 rounded-[var(--r-md)] border border-stone-200 dark:border-stone-800 text-xs font-semibold text-stone-600 dark:text-stone-300 cursor-pointer disabled:opacity-40"
        >
          Send
        </button>
        {next && (
          <button
            type="button"
            disabled={sending}
            onClick={() => { void run(() => skipClarification(next.id)); }}
            className="shrink-0 px-2 py-2 text-xs font-medium text-stone-500 cursor-pointer disabled:opacity-40"
          >
            Skip
          </button>
        )}
      </div>
    </div>
  );
}

export function ChatFeatureCard({
  feature,
  indexLabel,
}: {
  feature: Feature;
  indexLabel?: string;
}) {
  const { approveFeature, rejectFeature, updateFeature, skipRemainingQuestions } = useProject();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [contextOpen, setContextOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(feature.name);
  const [summary, setSummary] = useState(feature.summary);
  const openQs = openQuestionCount(feature);
  const review = reviewStatusOf(feature);
  const approvable = canApproveFeature(feature);

  useEffect(() => {
    setName(feature.name);
    setSummary(feature.summary);
  }, [feature.name, feature.summary]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr(e instanceof BackendError ? e.toDisplay() : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-stone-200 dark:border-stone-800 rounded-[var(--r-lg)] bg-white dark:bg-stone-950 p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          {indexLabel && <p className="text-[10px] font-mono uppercase tracking-wider text-stone-400">{indexLabel}</p>}
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">{feature.name}</h3>
            <FeatureStatusBadge status={feature.status} />
            <ReviewStatusBadge status={review} />
            {openQs > 0 && (
              <span className="text-[10px] font-mono text-amber-600 dark:text-amber-400">{openQs} open question{openQs === 1 ? '' : 's'}</span>
            )}
          </div>
          <p className="text-xs text-stone-500 dark:text-stone-400 leading-relaxed">{feature.summary}</p>
        </div>
      </div>

      {editing && (
        <div className="space-y-2">
          <label className="block text-[11px] font-semibold text-stone-500">
            Name
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              className="mt-1 w-full bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-sm)] px-2.5 py-1.5 text-sm text-stone-800 dark:text-stone-100 focus:outline-none focus:border-[var(--accent)]"
            />
          </label>
          <label className="block text-[11px] font-semibold text-stone-500">
            Summary
            <textarea
              value={summary}
              onChange={e => setSummary(e.target.value)}
              rows={3}
              className="mt-1 w-full bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-sm)] px-2.5 py-1.5 text-sm text-stone-800 dark:text-stone-100 focus:outline-none focus:border-[var(--accent)] resize-y"
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy || !name.trim()}
              onClick={() => run(async () => {
                await updateFeature(feature.id, { name: name.trim(), summary: summary.trim() });
                setEditing(false);
              })}
              className="px-2.5 py-1 rounded-[var(--r-sm)] text-[11px] font-semibold bg-stone-900 dark:bg-stone-100 text-white dark:text-stone-900 cursor-pointer disabled:opacity-40"
            >
              Save
            </button>
            <button type="button" onClick={() => setEditing(false)} className="px-2.5 py-1 text-[11px] text-stone-500 cursor-pointer">
              Cancel
            </button>
          </div>
        </div>
      )}

      {contextOpen && <FeatureQuestionPanel feature={feature} />}

      {review === 'pending' && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setContextOpen(v => !v)}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-[11px] font-medium text-stone-600 dark:text-stone-300 cursor-pointer"
          >
            <MessageSquare className="w-3.5 h-3.5" /> {contextOpen ? 'Hide context' : 'Add context'}
          </button>
          <button
            type="button"
            onClick={() => setEditing(v => !v)}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-[11px] font-medium text-stone-600 dark:text-stone-300 cursor-pointer"
          >
            <Pencil className="w-3.5 h-3.5" /> Edit
          </button>
          {openQs > 0 && (
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => skipRemainingQuestions(feature.id))}
              className="px-2.5 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-[11px] font-medium text-stone-600 dark:text-stone-300 cursor-pointer disabled:opacity-40"
            >
              Skip remaining questions
            </button>
          )}
          <button
            type="button"
            disabled={busy || !approvable}
            title={openQs > 0 ? 'Answer or skip open questions before approving' : undefined}
            onClick={() => run(() => approveFeature(feature.id))}
            className="px-2.5 py-1.5 rounded-[var(--r-sm)] bg-stone-900 dark:bg-stone-100 text-white dark:text-stone-900 text-[11px] font-semibold cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Approve
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => run(() => rejectFeature(feature.id))}
            className="px-2.5 py-1.5 rounded-[var(--r-sm)] text-[11px] font-medium text-[var(--verdict-conf-txt)] cursor-pointer disabled:opacity-40"
          >
            Reject
          </button>
        </div>
      )}

      {err && <p role="alert" className="text-[11px] text-[var(--verdict-conf-txt)]">{err}</p>}
      {review !== 'pending' && (
        <p className="text-[11px] text-stone-400">{review === 'approved' ? 'Approved for task generation.' : 'Rejected — excluded from tasks.'}</p>
      )}
    </div>
  );
}

export function ReviewAllPanel({
  features,
  onClose,
}: {
  features: Feature[];
  onClose: () => void;
}) {
  const { approveFeature, rejectFeature, updateFeature } = useProject();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editSummary, setEditSummary] = useState('');
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panelRef.current?.focus();
  }, []);

  const pending = features.filter(f => reviewStatusOf(f) === 'pending');
  const unblocked = pending.filter(canApproveFeature);

  const toggle = (id: string, allowed: boolean) => {
    if (!allowed) return;
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const approveSelected = async () => {
    setBusy(true);
    try {
      for (const id of selected) {
        const f = features.find(x => x.id === id);
        if (f && canApproveFeature(f)) await approveFeature(id);
      }
      setSelected(new Set());
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-stone-900/30 dark:bg-black/50" onClick={onClose}>
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-label="Review all features"
        onClick={e => e.stopPropagation()}
        className="w-full max-w-md h-full bg-[var(--bg-app)] border-l border-stone-200 dark:border-stone-800 overflow-y-auto p-5 space-y-4"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-stone-900 dark:text-stone-100">Review all features</h2>
            <p className="text-[11px] text-stone-500 mt-0.5">Features with open questions stay blocked until you answer or skip them.</p>
          </div>
          <button type="button" onClick={onClose} className="p-1 rounded-[var(--r-sm)] text-stone-400 hover:text-stone-700 cursor-pointer" aria-label="Close review panel">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy || selected.size === 0}
            onClick={() => { void approveSelected(); }}
            className="px-3 py-1.5 rounded-[var(--r-sm)] bg-stone-900 dark:bg-stone-100 text-white dark:text-stone-900 text-[11px] font-semibold cursor-pointer disabled:opacity-40"
          >
            Approve selected{selected.size > 0 ? ` (${selected.size})` : ''}
          </button>
          <button
            type="button"
            disabled={busy || unblocked.length === 0}
            onClick={() => setSelected(new Set(unblocked.map(f => f.id)))}
            className="px-3 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-[11px] font-medium text-stone-600 dark:text-stone-300 cursor-pointer disabled:opacity-40"
          >
            Select unblocked
          </button>
        </div>

        <ul className="space-y-3">
          {features.map(f => {
            const openQs = openQuestionCount(f);
            const review = reviewStatusOf(f);
            const allowed = canApproveFeature(f);
            return (
              <li key={f.id} className="p-3 rounded-[var(--r-md)] border border-stone-200 dark:border-stone-800 space-y-2">
                <label className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={selected.has(f.id)}
                    disabled={!allowed}
                    onChange={() => toggle(f.id, allowed)}
                    className="mt-1"
                    aria-label={`Select ${f.name}`}
                  />
                  <span className="min-w-0">
                    <span className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-stone-800 dark:text-stone-100">{f.name}</span>
                      <ReviewStatusBadge status={review} />
                      {openQs > 0 && <span className="text-[10px] font-mono text-amber-600">{openQs} open</span>}
                    </span>
                    <span className="block text-[11px] text-stone-500 mt-0.5">{f.summary}</span>
                  </span>
                </label>
                {review === 'pending' && (
                  <div className="flex flex-wrap gap-2 pl-6">
                    <button
                      type="button"
                      disabled={busy || !allowed}
                      onClick={() => { void approveFeature(f.id); }}
                      className="text-[11px] font-semibold text-stone-700 dark:text-stone-200 cursor-pointer disabled:opacity-40"
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      onClick={() => { setEditingId(f.id); setEditName(f.name); setEditSummary(f.summary); }}
                      className="text-[11px] font-medium text-stone-600 dark:text-stone-300 cursor-pointer"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => { void rejectFeature(f.id); }}
                      className="text-[11px] font-medium text-[var(--verdict-conf-txt)] cursor-pointer"
                    >
                      Reject
                    </button>
                  </div>
                )}
                {editingId === f.id && (
                  <div className="pl-6 space-y-2">
                    <input
                      value={editName}
                      onChange={e => setEditName(e.target.value)}
                      aria-label={`Rename ${f.name}`}
                      className="w-full bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-sm)] px-2 py-1.5 text-xs focus:outline-none focus:border-[var(--accent)]"
                    />
                    <textarea
                      value={editSummary}
                      onChange={e => setEditSummary(e.target.value)}
                      aria-label={`Summary for ${f.name}`}
                      rows={2}
                      className="w-full bg-white dark:bg-stone-950 border border-stone-200 dark:border-stone-800 rounded-[var(--r-sm)] px-2 py-1.5 text-xs focus:outline-none focus:border-[var(--accent)] resize-y"
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={busy || !editName.trim()}
                        onClick={async () => {
                          setBusy(true);
                          try {
                            await updateFeature(f.id, { name: editName.trim(), summary: editSummary.trim() });
                            setEditingId(null);
                          } finally {
                            setBusy(false);
                          }
                        }}
                        className="text-[11px] font-semibold text-stone-700 dark:text-stone-200 cursor-pointer disabled:opacity-40"
                      >
                        Save
                      </button>
                      <button type="button" onClick={() => setEditingId(null)} className="text-[11px] text-stone-400 cursor-pointer">
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

export function TaskProgressList({ features }: { features: Feature[] }) {
  return (
    <ul className="ml-9 space-y-1.5">
      {features.map(f => {
        const ready = f.status === 'tasks_ready' || f.tasks.length > 0;
        const planning = f.status === 'planning';
        return (
          <li key={f.id} className="flex items-center gap-2 text-xs text-stone-600 dark:text-stone-300">
            {planning && <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--accent)]" />}
            {ready && !planning && <Check className="w-3.5 h-3.5 text-[var(--verdict-new-txt)]" />}
            {!ready && !planning && <span className="w-3.5 h-3.5 rounded-full border border-stone-300 dark:border-stone-700" />}
            <span className="font-medium">{f.name}</span>
            <span className="text-[10px] font-mono text-stone-400">
              {ready ? `${f.tasks.length} task${f.tasks.length === 1 ? '' : 's'}` : planning ? 'generating…' : 'waiting'}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function FeatureTaskReview({
  feature,
  hideBoard,
}: {
  feature: Feature;
  hideBoard?: boolean;
}) {
  const { approveTask, addTaskToBoard, approveAllDraftTasks } = useProject();
  const drafts = feature.tasks.filter(t => t.status === 'draft').length;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-stone-800 dark:text-stone-100">{feature.name}</h3>
        {drafts > 0 && (
          <button
            type="button"
            onClick={() => { void approveAllDraftTasks(feature.id); }}
            className="px-2.5 py-1 rounded-[var(--r-sm)] bg-stone-900 dark:bg-stone-100 text-white dark:text-stone-900 text-[11px] font-semibold cursor-pointer"
          >
            Approve all {drafts}
          </button>
        )}
      </div>
      {feature.tasks.map(t => (
        <TaskCard
          key={t.id}
          task={t}
          hideBoard={hideBoard}
          onApprove={() => { void approveTask(t.id); }}
          onBoard={() => { void addTaskToBoard(t.id); }}
        />
      ))}
    </div>
  );
}

export function ReadyTasksTable({
  tasks,
  onAdd,
  adding,
}: {
  tasks: Array<{ feature: Feature; task: GeneratedTask }>;
  onAdd: () => void;
  adding?: boolean;
}) {
  const n = tasks.length;
  if (n === 0) {
    return <p className="text-xs text-stone-400">No approved tasks waiting for the board.</p>;
  }
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto border border-stone-200 dark:border-stone-800 rounded-[var(--r-md)]">
        <table className="w-full text-left text-xs">
          <thead className="bg-stone-50 dark:bg-stone-900 text-[10px] font-mono uppercase tracking-wider text-stone-400">
            <tr>
              <th className="px-3 py-2 font-medium">Task</th>
              <th className="px-3 py-2 font-medium">Feature</th>
              <th className="px-3 py-2 font-medium">Priority</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map(({ feature, task }) => (
              <tr key={task.id} className="border-t border-stone-100 dark:border-stone-850">
                <td className="px-3 py-2 text-stone-800 dark:text-stone-100">{task.title}</td>
                <td className="px-3 py-2 text-stone-500">{feature.name}</td>
                <td className="px-3 py-2 font-mono text-stone-400">{task.priority}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        disabled={adding}
        onClick={onAdd}
        className="px-3 py-2 rounded-[var(--r-md)] bg-[var(--accent)] text-white text-sm font-semibold cursor-pointer disabled:opacity-40"
      >
        {adding ? 'Adding…' : `Add ${n} task${n === 1 ? '' : 's'} to board`}
      </button>
    </div>
  );
}

export function ChatFooterLinks({ onReviewAll }: { onReviewAll: () => void }) {
  const { setActiveView, features } = useProject();
  const ready = approvedBoardReady(features).length;
  return (
    <div className="flex flex-wrap gap-3 text-[11px]">
      <button type="button" onClick={onReviewAll} className="font-semibold text-stone-600 dark:text-stone-300 cursor-pointer">
        Review all features
      </button>
      <button type="button" onClick={() => setActiveView('sources')} className="font-semibold text-stone-600 dark:text-stone-300 cursor-pointer">
        Open Sources
      </button>
      <button type="button" onClick={() => setActiveView('board')} className="font-semibold text-stone-600 dark:text-stone-300 cursor-pointer">
        Open Board{ready > 0 ? ` (${ready} ready)` : ''}
      </button>
    </div>
  );
}
