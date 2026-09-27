import React, { useState } from 'react';
import { ChevronDown, ChevronRight, FileText, Loader2, Sparkles } from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';
import { CitationChip } from './CitationChip.js';
import { AgentActivity, Feature, FeatureReviewStatus, FeatureStatus, GeneratedTask, SourceQuote } from '../types.js';
import { BackendError } from '../lib/backend.js';
import { openQuestionCount, reviewStatusOf } from '../lib/workflow.js';

const STATUS_LABEL: Record<FeatureStatus, string> = {
  extracted: 'extracted',
  analysed: 'analysed',
  needs_clarification: 'needs clarification',
  clarified: 'clarified',
  planning: 'planning',
  tasks_ready: 'tasks ready',
};

export function FeatureStatusBadge({ status }: { status: FeatureStatus }) {
  const tint = status === 'needs_clarification'
    ? 'bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400'
    : status === 'tasks_ready'
      ? 'bg-[var(--verdict-new-bg)] text-[var(--verdict-new-txt)]'
      : status === 'planning'
        ? 'bg-[var(--accent-bg)] text-[var(--accent)]'
        : 'bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400';
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[var(--r-sm)] text-[10px] font-semibold uppercase tracking-[0.03em] ${tint}`}>
      {status === 'planning' && <Loader2 className="w-3 h-3 animate-spin" />}
      {STATUS_LABEL[status]}
    </span>
  );
}

const REVIEW_TINT: Record<FeatureReviewStatus, string> = {
  pending: 'bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400',
  approved: 'bg-[var(--verdict-new-bg)] text-[var(--verdict-new-txt)]',
  rejected: 'bg-[var(--verdict-conf-bg)] text-[var(--verdict-conf-txt)]',
};

export function ReviewStatusBadge({ status }: { status: FeatureReviewStatus }) {
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[var(--r-sm)] text-[10px] font-semibold uppercase tracking-[0.03em] ${REVIEW_TINT[status]}`}>
      {status}
    </span>
  );
}

export function QuoteCite({ quote }: { quote: SourceQuote }) {
  if (quote.origin === 'pm') {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-[var(--accent-bg)] text-[var(--accent)] text-[10px] font-mono">
        PM answer
        <span className="max-w-[220px] truncate">“{quote.quote}”</span>
      </span>
    );
  }
  if (!quote.verified) {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400 text-[10px] font-mono" title="This quote could not be found in the document">
        unverified
        <span className="max-w-[220px] truncate">“{quote.quote}”</span>
      </span>
    );
  }
  return (
    <CitationChip
      id="source"
      type="source"
      title="Source document"
      snippet={quote.quote}
    />
  );
}

function TaskSection({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-[11px] font-mono uppercase tracking-wider text-stone-400 mb-1">{title}</h4>
      {children}
    </div>
  );
}

export function TaskCard({
  task,
  onApprove,
  onBoard,
  hideBoard,
}: {
  task: GeneratedTask;
  onApprove: () => void;
  onBoard?: () => void;
  hideBoard?: boolean;
}) {
  const subtasks = task.subtasks ?? [];
  const criteria = task.acceptanceCriteria ?? [];
  const done = task.definitionOfDone ?? [];
  return (
    <div className="p-3 rounded-[var(--r-md)] border border-stone-200 dark:border-stone-800 bg-stone-50/40 dark:bg-stone-900/30 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[13px] font-semibold text-stone-800 dark:text-stone-100">{task.title}</span>
        <span className="text-[10px] font-mono text-stone-400">{task.priority} · {task.estimate} · {task.status}</span>
      </div>
      {task.description && (
        <p className="text-xs text-stone-500 dark:text-stone-400 leading-relaxed whitespace-pre-wrap">{task.description}</p>
      )}
      <TaskSection title="Subtasks">
        {subtasks.length > 0 && (
          <ul className="text-[11px] text-stone-500 dark:text-stone-400 space-y-0.5">
            {subtasks.map((step, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <span
                  aria-hidden
                  className="mt-0.5 inline-block w-3 h-3 shrink-0 rounded-[2px] border border-stone-300 dark:border-stone-600 bg-white dark:bg-stone-900"
                />
                <span>{step}</span>
              </li>
            ))}
          </ul>
        )}
      </TaskSection>
      <TaskSection title="Acceptance criteria">
        {criteria.length > 0 && (
          <ul className="text-[11px] text-stone-500 dark:text-stone-400 space-y-0.5">
            {criteria.map((ac, i) => (
              <li key={i}>Given {ac.given} When {ac.when} Then {ac.then}</li>
            ))}
          </ul>
        )}
      </TaskSection>
      <TaskSection title="Definition of done">
        {done.length > 0 && (
          <ul className="text-[11px] text-stone-500 dark:text-stone-400 space-y-0.5 list-disc pl-4">
            {done.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        )}
      </TaskSection>
      {task.tracesTo.length > 0 && (
        <p className="text-[10px] font-mono text-stone-400">traces to: {task.tracesTo.join(' · ')}</p>
      )}
      {task.reviewNotes && (
        <p className="text-[11px] text-amber-700 dark:text-amber-400">Reviewer: {task.reviewNotes}</p>
      )}
      <div className="flex gap-2 pt-1">
        {task.status === 'draft' && (
          <button type="button" onClick={onApprove} className="px-2.5 py-1 rounded-[var(--r-sm)] text-[11px] font-medium bg-stone-900 dark:bg-stone-100 text-white dark:text-stone-900 cursor-pointer">
            Approve
          </button>
        )}
        {!hideBoard && task.status === 'approved' && onBoard && (
          <button type="button" onClick={onBoard} className="px-2.5 py-1 rounded-[var(--r-sm)] text-[11px] font-medium bg-[var(--accent)] text-white cursor-pointer">
            Add to board
          </button>
        )}
        {task.status === 'on_board' && (
          <span className="text-[11px] text-[var(--verdict-new-txt)]">On board #{task.boardItemId}</span>
        )}
      </div>
    </div>
  );
}

export function FeatureInspectCard({
  feature,
  activity,
  markdown,
  onLoadExtras,
}: {
  feature: Feature;
  activity: AgentActivity[];
  markdown?: string;
  onLoadExtras: () => void;
}) {
  const {
    generateFeatureTasks,
    approveTask,
    addTaskToBoard,
  } = useProject();
  const [open, setOpen] = useState(false);
  const [showMd, setShowMd] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const openQs = openQuestionCount(feature);
  const review = reviewStatusOf(feature);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next) onLoadExtras();
  };

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
    <div className="border border-stone-200 dark:border-stone-800 rounded-[var(--r-lg)] bg-white dark:bg-stone-950">
      <button
        type="button"
        onClick={toggle}
        className="w-full text-left p-4 flex items-start gap-3 cursor-pointer"
        aria-expanded={open}
      >
        {open ? <ChevronDown className="w-4 h-4 mt-0.5 text-stone-400" /> : <ChevronRight className="w-4 h-4 mt-0.5 text-stone-400" />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">{feature.name}</h3>
            <FeatureStatusBadge status={feature.status} />
            <ReviewStatusBadge status={review} />
            {openQs > 0 && (
              <span className="text-[10px] font-mono text-amber-600 dark:text-amber-400">{openQs} open question{openQs === 1 ? '' : 's'}</span>
            )}
            {feature.tasks.length > 0 && (
              <span className="text-[10px] font-mono text-stone-400">{feature.tasks.length} task{feature.tasks.length === 1 ? '' : 's'}</span>
            )}
          </div>
          <p className="mt-1 text-xs text-stone-500 dark:text-stone-400 leading-relaxed">{feature.summary}</p>
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-stone-100 dark:border-stone-850">
          {feature.details && (
            <div className="pt-3 space-y-2 text-xs text-stone-600 dark:text-stone-300">
              {feature.details.description && <p>{feature.details.description}</p>}
              {feature.details.functionalRequirements.map((r, i) => (
                <div key={i} className="flex flex-wrap items-baseline gap-2">
                  <span>{r.text}</span>
                  {r.quote && <QuoteCite quote={{ quote: r.quote, verified: feature.sourceQuotes.some(q => q.quote === r.quote && q.verified), origin: feature.sourceQuotes.find(q => q.quote === r.quote)?.origin }} />}
                </div>
              ))}
              {feature.sourceQuotes.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {feature.sourceQuotes.map((q, i) => <QuoteCite key={i} quote={q} />)}
                </div>
              )}
            </div>
          )}

          {feature.questions.length > 0 && (
            <div>
              <h4 className="text-[11px] font-mono uppercase tracking-wider text-stone-400 mb-1.5">Questions</h4>
              <ul className="space-y-1 text-xs">
                {feature.questions.map(q => (
                  <li key={q.id} className="text-stone-600 dark:text-stone-300">
                    <span className="font-medium">{q.question}</span>
                    <span className="ml-2 text-[10px] font-mono text-stone-400">{q.status}</span>
                    {q.answer && <span className="block text-stone-500 pl-2">→ {q.answer}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || feature.status === 'planning'}
              onClick={() => run(() => generateFeatureTasks(feature.id))}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--r-sm)] bg-[var(--accent)] text-white text-xs font-semibold cursor-pointer disabled:opacity-40"
            >
              {feature.status === 'planning' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              Generate tasks
            </button>
            <button
              type="button"
              onClick={() => { setShowMd(!showMd); onLoadExtras(); }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-xs font-medium text-stone-600 dark:text-stone-300 cursor-pointer"
            >
              <FileText className="w-3.5 h-3.5" /> {showMd ? 'Hide source' : 'View source Markdown'}
            </button>
          </div>

          {showMd && markdown && (
            <pre className="text-[11px] font-mono text-stone-500 dark:text-stone-400 bg-stone-50 dark:bg-stone-900 rounded-[var(--r-md)] p-3 max-h-64 overflow-auto whitespace-pre-wrap">{markdown}</pre>
          )}

          {activity.length > 0 && (
            <div>
              <h4 className="text-[11px] font-mono uppercase tracking-wider text-stone-400 mb-1.5">Agent activity</h4>
              <ol className="space-y-1">
                {activity.map(a => (
                  <li key={a.id} className="text-[11px] text-stone-500 dark:text-stone-400">
                    <span className="font-semibold text-stone-700 dark:text-stone-300">{a.agent || a.node}</span>
                    {' — '}{a.detail}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {feature.tasks.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-[11px] font-mono uppercase tracking-wider text-stone-400">Tasks</h4>
              {feature.tasks.map(t => (
                <TaskCard
                  key={t.id}
                  task={t}
                  onApprove={() => run(() => approveTask(t.id))}
                  onBoard={() => run(() => addTaskToBoard(t.id))}
                />
              ))}
            </div>
          )}

          {err && <p role="alert" className="text-[11px] text-[var(--verdict-conf-txt)]">{err}</p>}
          {busy && <p className="text-[11px] text-stone-400">Working…</p>}
        </div>
      )}
    </div>
  );
}
