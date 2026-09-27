import React, { useMemo, useState } from 'react';
import {
  GitPullRequest, GitMerge, Rocket, ExternalLink, ArrowRight, CheckCircle2,
  ShieldCheck, FileCode2
} from 'lucide-react';
import { useProject } from '../context/ProjectContext.js';
import { buildDeliveries } from '../lib/delivery.js';
import { CheckPill } from './StatusBadges.js';
import { Delivery, PRStatus } from '../types.js';

type DeliveryFilter = 'all' | 'open' | 'merged';

const statusChip = (status: PRStatus) => {
  if (status === 'open') return <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--accent)]"><GitPullRequest className="w-3.5 h-3.5" /> open</span>;
  if (status === 'merged') return <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-violet-600 dark:text-violet-300"><GitMerge className="w-3.5 h-3.5" /> merged</span>;
  return <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--verdict-new-txt)]"><Rocket className="w-3.5 h-3.5" /> deployed</span>;
};

function PRDetail({ d }: { d: Delivery }) {
  const { triggerToast } = useProject();
  const covClean = d.reqMet === d.reqTotal;
  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-stone-200 dark:border-stone-850 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-xs text-stone-400 font-bold">PR #{d.prNumber}</span>
          <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 truncate">{d.itemTitle} <span className="text-stone-400 font-normal">(#{d.itemId})</span></h3>
        </div>
        <button onClick={() => triggerToast('Opening in GitHub…')} className="inline-flex items-center gap-1 px-2 py-1 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-[11px] font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-900 cursor-pointer">
          <ExternalLink className="w-3.5 h-3.5" /> Open in GH
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Meta + checks */}
        <div className="flex items-center gap-4 flex-wrap text-[11px] text-stone-500">
          <span>{d.commits} commits</span>
          <span>{d.files} files</span>
          <span className="flex items-center gap-3">Checks: <CheckPill label="CI" state={d.ci} /> <CheckPill label="build" state={d.build} /> <CheckPill label="lint" state={d.lint} /></span>
        </div>

        {/* Requirement re-check — the thing no other tool shows (§4.14) */}
        <div className="rounded-[var(--r-md)] border border-stone-200 dark:border-stone-850 overflow-hidden">
          <div className="px-3 py-2 bg-stone-50 dark:bg-stone-900 border-b border-stone-150 dark:border-stone-850 flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-[var(--accent)]" />
            <span className="text-[11px] font-semibold text-stone-700 dark:text-stone-200">Requirement re-check (live)</span>
            <span className={`ml-auto text-[11px] font-bold ${covClean ? 'text-[var(--verdict-new-txt)]' : 'text-amber-600 dark:text-amber-400'}`}>
              {d.reqMet}/{d.reqTotal} met {covClean && '✓'}
              {d.reqWas !== undefined && <span className="text-stone-400 font-normal"> (was {d.reqWas}/{d.reqTotal} at review)</span>}
            </span>
          </div>
          <div className="p-3 space-y-1.5">
            {d.fixedNotes ? d.fixedNotes.map((n, i) => (
              <div key={i} className="flex items-center justify-between gap-2 text-[11px]">
                <span className="text-stone-600 dark:text-stone-300"><CheckCircle2 className="w-3 h-3 inline text-[var(--verdict-new-txt)] mr-1" />{n.req}</span>
                <span className="inline-flex items-center gap-1 font-mono text-[10px] text-stone-500"><FileCode2 className="w-2.5 h-2.5" />{n.file}</span>
              </div>
            )) : (
              <p className="text-[11px] text-stone-500">Coverage re-runs on every push, so “does it still match the task” is answered continuously.</p>
            )}
          </div>
        </div>

        {/* Deploy status */}
        <div className="rounded-[var(--r-md)] border border-stone-200 dark:border-stone-850 p-3 text-[11px] text-stone-600 dark:text-stone-300 flex items-center gap-4 flex-wrap">
          <span className="font-semibold text-stone-500 uppercase tracking-wider text-[10px]">Deploy</span>
          {d.deployStaging && <span className="inline-flex items-center gap-1">staging <CheckCircle2 className="w-3 h-3 text-[var(--verdict-new-txt)]" /> {d.deployStaging}</span>}
          {d.deployProd === 'live' && <span className="inline-flex items-center gap-1">prod <Rocket className="w-3 h-3 text-[var(--verdict-new-txt)]" /> live</span>}
          {d.deployProd === 'awaiting' && <span className="text-amber-600 dark:text-amber-400">prod — awaiting approval</span>}
          {!d.deployStaging && <span className="text-stone-400">not deployed yet</span>}
        </div>
      </div>

      {/* Human is the final approver (principle #9) */}
      <div className="p-4 border-t border-stone-200 dark:border-stone-850 bg-stone-50/50 dark:bg-stone-900/40 flex items-center justify-end gap-2 flex-wrap">
        {d.status === 'open' && (
          <button onClick={() => triggerToast(`Merge #${d.prNumber}? (confirm) — merge is one-way.`)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--r-sm)] bg-[var(--accent)] text-white text-[11px] font-semibold hover:opacity-95 cursor-pointer">
            <GitMerge className="w-3.5 h-3.5" /> Approve &amp; merge
          </button>
        )}
        {d.deployProd === 'awaiting' && (
          <button onClick={() => triggerToast(`Approve prod deploy for #${d.prNumber}? (confirm)`)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--r-sm)] bg-[var(--accent)] text-white text-[11px] font-semibold hover:opacity-95 cursor-pointer">
            <Rocket className="w-3.5 h-3.5" /> Approve deploy → prod
          </button>
        )}
        <button onClick={() => triggerToast('Comment added.')} className="px-3 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-[11px] font-semibold text-stone-700 dark:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-900 cursor-pointer">Comment</button>
      </div>
    </div>
  );
}

export const DeliveryView: React.FC = () => {
  const { state, setActiveView } = useProject();
  const [filter, setFilter] = useState<DeliveryFilter>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const deliveries = useMemo(() => buildDeliveries(state?.items || [], state?.agents || []), [state?.items, state?.agents]);

  const filtered = deliveries.filter(d => filter === 'all' ? true : filter === 'open' ? d.status === 'open' : d.status !== 'open');
  const selected = deliveries.find(d => d.id === selectedId) || filtered[0] || null;

  if (deliveries.length === 0) {
    return (
      <div className="border border-dashed border-stone-250 dark:border-stone-800 rounded-[var(--r-lg)] p-12 text-center text-stone-400 max-w-2xl mx-auto mt-6">
        <Rocket className="w-8 h-8 text-stone-300 mx-auto mb-3" />
        <h3 className="font-semibold text-stone-900 dark:text-stone-100 text-sm">No deliveries yet</h3>
        <p className="text-xs text-stone-500 mt-1 max-w-sm mx-auto leading-relaxed">
          Once a review is approved, the change moves through the delivery pipeline — PR, CI/CD, deploy — and Alpha Auctus keeps re-checking coverage against the task as it goes.
        </p>
        <button onClick={() => setActiveView('reviews')} className="mt-4 px-3 py-1.5 rounded-[var(--r-sm)] bg-[var(--accent)] text-white text-xs font-semibold cursor-pointer">Go to reviews</button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-base font-bold text-stone-900 dark:text-stone-50 tracking-tight">Delivery</h2>
          <p className="text-xs text-stone-500 dark:text-stone-400">PR · CI/CD · deploy — with requirement coverage re-checked on every push.</p>
        </div>
        <div className="flex items-center gap-1 text-xs">
          {(['all', 'open', 'merged'] as DeliveryFilter[]).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-2.5 py-1 rounded-[var(--r-sm)] capitalize font-medium cursor-pointer transition-colors ${filter === f ? 'bg-[var(--accent-bg)] text-[var(--accent)]' : 'text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-900'}`}>{f}</button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-4 items-start">
        <div className="space-y-2">
          {filtered.map(d => {
            const active = selected?.id === d.id;
            const covClean = d.reqMet === d.reqTotal;
            return (
              <button key={d.id} onClick={() => setSelectedId(d.id)}
                className={`w-full text-left p-3 rounded-[var(--r-md)] border transition-colors cursor-pointer ${active ? 'border-[var(--accent)] bg-[var(--accent-bg)]' : 'border-stone-200 dark:border-stone-850 bg-white dark:bg-stone-950 hover:border-stone-300 dark:hover:border-stone-700'}`}>
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="font-mono text-[11px] text-stone-400 font-bold">#{d.itemId} · PR #{d.prNumber}</span>
                  {statusChip(d.status)}
                </div>
                <p className="text-[13px] font-semibold text-stone-900 dark:text-stone-100 leading-snug truncate">{d.itemTitle}</p>
                <div className="mt-1.5 flex items-center gap-3 text-[10px]">
                  <CheckPill label="CI" state={d.ci} />
                  <span className={`font-semibold ${covClean ? 'text-[var(--verdict-new-txt)]' : 'text-amber-600 dark:text-amber-400'}`}>
                    reqs {d.reqWas !== undefined ? `${d.reqWas}/${d.reqTotal}→${d.reqMet}/${d.reqTotal}` : `${d.reqMet}/${d.reqTotal}`}
                  </span>
                </div>
              </button>
            );
          })}
        </div>

        <div className="border border-stone-200 dark:border-stone-850 rounded-[var(--r-lg)] bg-white dark:bg-stone-950 min-h-[520px] overflow-hidden">
          {selected ? <PRDetail d={selected} /> : <div className="h-full grid place-items-center text-xs text-stone-400 p-8">Select a PR.</div>}
        </div>
      </div>
    </div>
  );
};
