import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Check, X, FileText, Bookmark, ArrowRightLeft } from 'lucide-react';
import { VerdictBadge } from './VerdictBadge.js';
import { IngestItem, Item, Candidate } from '../types.js';
import { useProject } from '../context/ProjectContext.js';

interface VerdictRowProps {
  item: IngestItem | Item;
  isIngest?: boolean; // If inside ingest queue or on the main backlog
}

export const VerdictRow: React.FC<VerdictRowProps> = ({ item, isIngest = false }) => {
  const { resolveVerdict, resolveIngestItem, setSelectedCardId, state } = useProject();
  const [expanded, setExpanded] = useState(false);

  const verdict = item.verdict;
  if (!verdict || verdict.type === 'net-new') return null;

  const handleAction = async (action: 'confirm' | 'dismiss' | 'supersede' | 'merge', targetId?: string) => {
    if (isIngest) {
      if (action === 'dismiss') {
        await resolveIngestItem(item.id.toString(), 'dismiss');
      } else {
        // Approve and move to Inbox
        await resolveIngestItem(item.id.toString(), 'approve');
      }
    } else {
      await resolveVerdict(item.id as number, action, targetId);
    }
  };

  const getCandidateTitle = (cand: Candidate) => {
    if (cand.type === 'decision') {
      const d = state?.decisions.find(dec => dec.id === parseInt(cand.id));
      return d ? d.title : cand.title;
    } else {
      const i = state?.items.find(it => it.id === parseInt(cand.id));
      return i ? i.title : cand.title;
    }
  };

  return (
    <div className={`p-4 border rounded-[var(--r-md)] transition-all ${verdict.type === 'conflict' ? 'border-red-200 dark:border-red-950 bg-red-50/20 dark:bg-red-950/5' : 'border-stone-200 dark:border-stone-800 bg-stone-50/40 dark:bg-stone-900/40'} hover:border-stone-400 dark:hover:border-stone-600`}>
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        {/* Left column: Title and descriptions */}
        <div className="flex-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="font-mono text-xs text-stone-400 dark:text-stone-500">
              {isIngest ? 'Draft' : `#${item.id}`}
            </span>
            <h3 className="text-[14px] font-semibold text-stone-900 dark:text-stone-100 leading-snug">
              {item.title}
            </h3>
            <VerdictBadge type={verdict.type} confidence={verdict.confidence} />
          </div>

          <p className="mt-1.5 text-xs text-stone-500 dark:text-stone-400 line-clamp-2 leading-relaxed">
            {item.description}
          </p>

          {('source' in item && item.source) && (
            <div className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-stone-400 dark:text-stone-500">
              <FileText className="w-3.5 h-3.5" />
              <span>Source: {(item as any).source.name}</span>
            </div>
          )}
        </div>

        {/* Right column: Immediate Triage options */}
        <div className="flex items-center gap-2 shrink-0 flex-wrap">
          {verdict.type === 'conflict' ? (
            <>
              <button
                onClick={() => handleAction('supersede', verdict.candidates[0]?.id)}
                className="px-3 py-1.5 rounded-[var(--r-sm)] bg-stone-900 dark:bg-stone-100 text-white dark:text-stone-900 text-xs font-medium hover:opacity-90 active:scale-95 transition-transform cursor-pointer"
              >
                Supersede Decision #{verdict.candidates[0]?.id}
              </button>
              <button
                onClick={() => handleAction('dismiss')}
                className="px-3 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-stone-600 dark:text-stone-300 text-xs font-medium hover:bg-stone-100 dark:hover:bg-stone-850 cursor-pointer"
              >
                Dismiss Conflict
              </button>
            </>
          ) : verdict.type === 'duplicate' ? (
            <>
              <button
                onClick={() => handleAction('merge', verdict.candidates[0]?.id)}
                className="px-3 py-1.5 rounded-[var(--r-sm)] bg-stone-900 dark:bg-stone-100 text-white dark:text-stone-900 text-xs font-medium hover:opacity-90 active:scale-95 transition-transform cursor-pointer"
              >
                Merge into #{verdict.candidates[0]?.id}
              </button>
              <button
                onClick={() => handleAction('dismiss')}
                className="px-3 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-stone-600 dark:text-stone-300 text-xs font-medium hover:bg-stone-100 dark:hover:bg-stone-850 cursor-pointer"
              >
                Keep Duplicate Task
              </button>
            </>
          ) : (
            <button
              onClick={() => handleAction('dismiss')}
              className="px-3 py-1.5 rounded-[var(--r-sm)] bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300 text-xs font-medium hover:bg-stone-200 dark:hover:bg-stone-700 cursor-pointer"
            >
              Acknowledge Impact
            </button>
          )}

          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1.5 rounded-[var(--r-sm)] text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 cursor-pointer"
            aria-label="Toggle matching details"
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Expandable Section: Matching memory candidates */}
      {expanded && (
        <div className="mt-4 pt-4 border-t border-stone-250 dark:border-stone-800 space-y-3.5">
          <div className="text-xs font-semibold uppercase tracking-wider text-stone-400 dark:text-stone-500 flex items-center gap-1.5">
            <ArrowRightLeft className="w-3.5 h-3.5" />
            <span>Overlapping Candidates detected in Memory ({verdict.candidates?.length || 0})</span>
          </div>

          <div className="space-y-2">
            {verdict.candidates?.map((cand, idx) => (
              <div
                key={idx}
                className="p-3 rounded bg-stone-100/40 dark:bg-stone-950/40 border border-stone-150 dark:border-stone-850/60 text-xs"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {cand.type === 'decision' ? (
                      <Bookmark className="w-3.5 h-3.5 text-amber-500" />
                    ) : (
                      <FileText className="w-3.5 h-3.5 text-violet-500" />
                    )}
                    <span className="font-semibold text-stone-700 dark:text-stone-300">
                      {cand.type === 'decision' ? 'Decision' : 'Card'} {cand.id} : {getCandidateTitle(cand)}
                    </span>
                  </div>
                  <span className="text-[10px] font-mono font-bold bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 px-1.5 py-0.5 rounded">
                    {cand.confidence}% Match
                  </span>
                </div>
                <p className="mt-1 text-stone-500 dark:text-stone-400 italic">
                  “{cand.reason}”
                </p>
              </div>
            ))}
          </div>

          {verdict.citation && (
            <div className="p-3 bg-stone-100 dark:bg-stone-900 border border-stone-200 dark:border-stone-800 text-stone-700 dark:text-stone-300 rounded text-xs leading-relaxed">
              <div className="flex items-center gap-2 font-semibold text-stone-700 dark:text-stone-300 mb-1">
                <span>Citation Anchor:</span>
                <span className="font-mono text-[10px] bg-stone-200 dark:bg-white/20 px-1 rounded">
                  {verdict.citation.id}
                </span>
                <span>{verdict.citation.title}</span>
              </div>
              <p className="font-mono text-[11px] text-stone-500 dark:text-stone-400">
                “{verdict.citation.snippet}”
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
