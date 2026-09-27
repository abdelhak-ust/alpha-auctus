import React, { useMemo, useState } from 'react';
import { motion } from 'motion/react';
import {
  CheckCircle2, ArrowRight, FileCode2, BookMarked, FlaskConical, GitPullRequestArrow,
  Check, X, MessageSquarePlus, AlertTriangle, Link2, ShieldCheck
} from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';
import { buildReviews } from '../lib/delivery.js';
import { CoverageBadge } from './StatusBadges.js';
import { agentKindStyle } from '../lib/assignee.js';
import { Review, RequirementCoverage } from '../types.js';

// A code / requirement citation chip (dual citations, spec §4.13). Clicking a code
// citation would scroll the Diff tab to those lines; here it toasts to prove the wire.
const Cite: React.FC<{ label: string; kind: 'code' | 'req'; onClick?: () => void }> = ({ label, kind, onClick }) => (
  <button onClick={onClick}
    className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded font-mono text-[10px] cursor-pointer transition-colors ${kind === 'code'
      ? 'bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-300 hover:text-[var(--accent)]'
      : 'text-[var(--accent)] hover:underline'}`}>
    {kind === 'code' ? <FileCode2 className="w-2.5 h-2.5" /> : <BookMarked className="w-2.5 h-2.5" />}
    {label}
  </button>
);

function CoverageRow({ row, index, onAction }: { row: RequirementCoverage; index: number; onAction: (a: string, id: string) => void }) {
  const off = row.state === 'off-task';
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04, duration: 0.24, ease: [0.2, 0.8, 0.2, 1] }}
      className={`group p-3 border-b border-stone-150 dark:border-stone-850 last:border-b-0 ${row.lowConfidence ? 'bg-amber-50/40 dark:bg-amber-950/10' : ''}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5 min-w-0">
          <CoverageBadge state={row.state} className="mt-0.5 shrink-0" />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="font-mono text-[11px] text-stone-400 font-bold">{row.id}</span>
              <span className="text-[13px] font-medium text-stone-900 dark:text-stone-100">{row.requirement}</span>
            </div>
            {row.reason && <p className="text-[11px] text-stone-500 dark:text-stone-400 mt-0.5 leading-relaxed">{row.reason}</p>}
            {row.lowConfidence && (
              <p className="text-[10px] text-[var(--warning)] font-medium mt-0.5 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" /> possible — please check
              </p>
            )}
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              {row.codeCitation && <Cite kind="code" label={`${row.codeCitation.file}${row.codeCitation.line ? ':' + row.codeCitation.line : ''}`} onClick={() => onAction('diff', row.id)} />}
              {row.reqCitation && <Cite kind="req" label={row.reqCitation} onClick={() => onAction('req', row.id)} />}
              {off && row.suggestedHome && (
                <button onClick={() => onAction('link', row.id)} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium text-[var(--verdict-impact-txt)] bg-[var(--verdict-impact-bg)] cursor-pointer">
                  <Link2 className="w-2.5 h-2.5" /> belongs to {row.suggestedHome}?
                </button>
              )}
            </div>
          </div>
        </div>
        {/* Per-row actions (row-by-row confirmation, §4.13) */}
        <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <button title="Accept" onClick={() => onAction('accept', row.id)} className="p-1 rounded text-stone-400 hover:text-[var(--verdict-new-txt)] hover:bg-[var(--verdict-new-bg)] cursor-pointer"><Check className="w-3.5 h-3.5" /></button>
          <button title="Reject" onClick={() => onAction('reject', row.id)} className="p-1 rounded text-stone-400 hover:text-[var(--verdict-conf-txt)] hover:bg-[var(--verdict-conf-bg)] cursor-pointer"><X className="w-3.5 h-3.5" /></button>
          <button title="Comment" onClick={() => onAction('comment', row.id)} className="p-1 rounded text-stone-400 hover:text-[var(--accent)] hover:bg-[var(--accent-bg)] cursor-pointer"><MessageSquarePlus className="w-3.5 h-3.5" /></button>
        </div>
      </div>
    </motion.div>
  );
}

function ReviewDetail({ review }: { review: Review }) {
  const { triggerToast, setActiveView } = useProject();
  const [tab, setTab] = useState<'matrix' | 'diff' | 'requirements' | 'tests'>('matrix');
  const style = agentKindStyle(review.agentKind);
  const AgentIcon = style.icon;

  const onAction = (a: string, id: string) => {
    if (a === 'diff') { setTab('diff'); return; }
    if (a === 'accept') triggerToast(`Accepted ${id}.`);
    else if (a === 'reject') triggerToast(`Rejected ${id} — sent back to the agent.`);
    else if (a === 'comment') triggerToast(`Comment added on ${id}.`);
    else if (a === 'link') triggerToast(`Linked off-task change to another task.`);
    else if (a === 'req') triggerToast(`Opened requirement source for ${id}.`);
  };

  const verdictMap = {
    'all-met': { label: 'ALL MET', cls: 'text-[var(--verdict-new-txt)] bg-[var(--verdict-new-bg)]' },
    'needs-work': { label: 'NEEDS WORK', cls: 'text-[var(--verdict-conf-txt)] bg-[var(--verdict-conf-bg)]' },
    'off-task': { label: 'OFF-TASK CHANGES', cls: 'text-[var(--verdict-impact-txt)] bg-[var(--verdict-impact-bg)]' },
  } as const;
  const v = verdictMap[review.overall];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-stone-200 dark:border-stone-850 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-xs text-stone-400 font-bold">#{review.itemId}</span>
          <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 truncate">{review.itemTitle}</h3>
          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ${style.tint}`}>
            <AgentIcon className="w-3 h-3" /> {review.agentName}
          </span>
          <span className="text-[10px] font-mono text-stone-400">run {review.runTime}</span>
        </div>
        <div className="text-[11px] font-semibold text-stone-600 dark:text-stone-300">
          {review.metCount} / {review.totalCount} met
          {review.unmetCount > 0 && <span className="text-[var(--verdict-conf-txt)]"> · {review.unmetCount} unmet</span>}
          {review.offTaskCount > 0 && <span className="text-[var(--verdict-impact-txt)]"> · {review.offTaskCount} off-task</span>}
        </div>
      </div>

      {/* Sub tabs */}
      <div className="px-4 border-b border-stone-200 dark:border-stone-850 flex items-end gap-1 text-xs">
        {([['matrix', 'Coverage'], ['diff', 'Diff'], ['requirements', 'Requirements'], ['tests', 'Tests']] as const).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`py-2 px-3 border-b-2 font-medium cursor-pointer transition-colors ${tab === k ? 'border-[var(--accent)] text-[var(--accent)]' : 'border-transparent text-stone-500 hover:text-stone-800 dark:hover:text-stone-300'}`}>
            {label}
          </button>
        ))}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {tab === 'matrix' && (
          <div>
            <div className="px-4 py-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-stone-400 border-b border-stone-150 dark:border-stone-850">
              <ShieldCheck className="w-3.5 h-3.5" /> Requirement coverage
              <span className="ml-auto normal-case tracking-normal font-normal text-stone-400">recommendation — confirm row by row</span>
            </div>
            {review.coverage.map((row, i) => <CoverageRow key={row.id + i} row={row} index={i} onAction={onAction} />)}
            {review.regressionNote && (
              <div className="m-3 p-2.5 rounded-[var(--r-md)] border border-amber-300 dark:border-amber-900 bg-amber-50/50 dark:bg-amber-950/20 text-[11px] text-amber-800 dark:text-amber-300 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> {review.regressionNote} · tests cover R1, R2 only
              </div>
            )}
          </div>
        )}

        {tab === 'diff' && (
          <div className="p-4 space-y-2 font-mono text-[11px]">
            <p className="text-stone-500 font-sans">Requirement-annotated diff — each hunk's gutter marks which requirement it serves; unmapped hunks are flagged off-task.</p>
            {review.coverage.slice(0, 3).map(row => (
              <div key={row.id} className="rounded-[var(--r-md)] border border-stone-200 dark:border-stone-850 overflow-hidden">
                <div className="px-2.5 py-1 bg-stone-50 dark:bg-stone-900 border-b border-stone-150 dark:border-stone-850 flex items-center justify-between">
                  <span className="text-stone-500">{row.codeCitation?.file}</span>
                  <span className="text-[9px]"><CoverageBadge state={row.state} /></span>
                </div>
                <pre className="p-2.5 text-stone-600 dark:text-stone-300 overflow-x-auto"><span className="text-[var(--verdict-new-txt)]">+  // {row.id}: {row.requirement}</span>{'\n'}   …implementation hunk…</pre>
              </div>
            ))}
          </div>
        )}

        {tab === 'requirements' && (
          <ul className="p-4 space-y-2 text-xs">
            {review.coverage.filter(c => c.state !== 'off-task').map(row => (
              <li key={row.id} className="flex items-center justify-between gap-2 p-2 rounded border border-stone-150 dark:border-stone-850">
                <span className="text-stone-700 dark:text-stone-200"><span className="font-mono text-stone-400">{row.id}</span> {row.requirement}</span>
                <CoverageBadge state={row.state} />
              </li>
            ))}
          </ul>
        )}

        {tab === 'tests' && (
          <ul className="p-4 space-y-2 text-xs">
            {review.coverage.filter(c => c.state !== 'off-task').map(row => (
              <li key={row.id} className="flex items-center justify-between gap-2 p-2 rounded border border-stone-150 dark:border-stone-850">
                <span className="text-stone-700 dark:text-stone-200"><span className="font-mono text-stone-400">{row.id}</span> {row.requirement}</span>
                <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${row.tested ? 'text-[var(--verdict-new-txt)]' : 'text-stone-400'}`}>
                  <FlaskConical className="w-3.5 h-3.5" /> {row.tested ? 'covered' : 'no test'}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Overall verdict + actions (AI never approves — the human does, §4.13 / principle #9) */}
      <div className="p-4 border-t border-stone-200 dark:border-stone-850 bg-stone-50/50 dark:bg-stone-900/40 flex items-center justify-between gap-3 flex-wrap">
        <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-[var(--r-sm)] text-[11px] font-bold tracking-wide ${v.cls}`}>{v.label}</span>
        <div className="flex items-center gap-2">
          <button onClick={() => triggerToast(`Requested changes on #${review.itemId} — scoped follow-up run queued.`)}
            className="px-3 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-[11px] font-semibold text-stone-700 dark:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-900 cursor-pointer">
            Request changes
          </button>
          <button onClick={() => { triggerToast(`Approved #${review.itemId} — moved to Delivery.`); setActiveView('delivery'); }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--r-sm)] bg-[var(--accent)] text-white text-[11px] font-semibold hover:opacity-95 cursor-pointer">
            <GitPullRequestArrow className="w-3.5 h-3.5" /> Approve → Delivery
          </button>
        </div>
      </div>
    </div>
  );
}

export const ReviewsView: React.FC = () => {
  const { state, setActiveView } = useProject();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const reviews = useMemo(() => buildReviews(state?.items || [], state?.agents || []), [state?.items, state?.agents]);
  const selected = reviews.find(r => r.id === selectedId) || reviews[0] || null;

  if (reviews.length === 0) {
    return (
      <div className="border border-dashed border-stone-250 dark:border-stone-800 rounded-[var(--r-lg)] p-12 text-center text-stone-400 max-w-2xl mx-auto mt-6">
        <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-3" />
        <h3 className="font-semibold text-stone-900 dark:text-stone-100 text-sm">Nothing to review yet</h3>
        <p className="text-xs text-stone-500 mt-1 max-w-sm mx-auto leading-relaxed">
          When an agent finishes a run, its implementation lands here and Alpha Auctus checks it against the task — per requirement, with citations. This is where you confirm the agent built what was actually asked.
        </p>
        <button onClick={() => setActiveView('runs')} className="mt-4 px-3 py-1.5 rounded-[var(--r-sm)] bg-[var(--accent)] text-white text-xs font-semibold cursor-pointer">See runs</button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-base font-bold text-stone-900 dark:text-stone-50 tracking-tight flex items-center gap-2">
            Reviews <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-[var(--accent-bg)] text-[var(--accent)] tracking-normal">requirement validation</span>
          </h2>
          <p className="text-xs text-stone-500 dark:text-stone-400">Did the agent build what was asked? Per-requirement coverage, cited to code and to the requirement.</p>
        </div>
        <span className="bg-[var(--accent-bg)] text-[var(--accent)] text-xs px-2.5 py-1 rounded-full font-bold">{reviews.filter(r => r.overall !== 'all-met').length} need review</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-4 items-start">
        {/* Reviews queue */}
        <div className="space-y-2">
          {reviews.map(review => {
            const active = selected?.id === review.id;
            const clean = review.overall === 'all-met';
            return (
              <button key={review.id} onClick={() => setSelectedId(review.id)}
                className={`w-full text-left p-3 rounded-[var(--r-md)] border transition-colors cursor-pointer ${active ? 'border-[var(--accent)] bg-[var(--accent-bg)]' : 'border-stone-200 dark:border-stone-850 bg-white dark:bg-stone-950 hover:border-stone-300 dark:hover:border-stone-700'}`}>
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="font-mono text-[11px] text-stone-400 font-bold">#{review.itemId}</span>
                  <span className={`text-[11px] font-bold ${clean ? 'text-[var(--verdict-new-txt)]' : 'text-[var(--verdict-conf-txt)]'}`}>{review.metCount}/{review.totalCount}</span>
                </div>
                <p className="text-[13px] font-semibold text-stone-900 dark:text-stone-100 leading-snug truncate">{review.itemTitle}</p>
                <div className="mt-1.5 flex items-center gap-1.5">
                  {review.unmetCount > 0 && <CoverageBadge state="unmet" />}
                  {review.coverage.some(c => c.state === 'partial') && <CoverageBadge state="partial" />}
                  {review.offTaskCount > 0 && <CoverageBadge state="off-task" />}
                  {clean && <CoverageBadge state="met" />}
                </div>
              </button>
            );
          })}
        </div>

        {/* Detail */}
        <div className="border border-stone-200 dark:border-stone-850 rounded-[var(--r-lg)] bg-white dark:bg-stone-950 min-h-[520px] overflow-hidden">
          {selected ? <ReviewDetail review={selected} /> : (
            <div className="h-full grid place-items-center text-xs text-stone-400 p-8">Select a review.</div>
          )}
        </div>
      </div>
    </div>
  );
};
