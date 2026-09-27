import React, { useEffect, useState } from 'react';
import { useProject } from '../context/ProjectContext.js';
import { FeatureClarification } from './FeatureClarification.js';
import { FeatureInspectCard } from './FeatureCards.js';
import { openQuestionCount } from '../lib/workflow.js';

export const FeaturesView: React.FC = () => {
  const {
    features,
    documents,
    addAllApprovedToBoard,
    loadFeatureExtras,
    featureActivity,
    featureMarkdown,
    setActiveView,
    refreshFeatures,
  } = useProject();
  const [clarify, setClarify] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => { void refreshFeatures(); }, []);

  const approved = features.flatMap(f => f.tasks.filter(t => t.status === 'approved'));
  const openQs = features.reduce((n, f) => n + openQuestionCount(f), 0);

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-base font-bold text-stone-900 dark:text-stone-50 tracking-tight">Features</h2>
          <p className="text-xs text-stone-500 dark:text-stone-400 mt-0.5">
            Inspection of extracted features. Review and task generation happen in Chat.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setActiveView('chat')}
            className="px-3 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-xs font-semibold text-stone-700 dark:text-stone-200 cursor-pointer"
          >
            Open Chat
          </button>
          <button
            type="button"
            onClick={() => setClarify(true)}
            disabled={openQs === 0}
            className="px-3 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-xs font-semibold text-stone-700 dark:text-stone-200 cursor-pointer disabled:opacity-40"
          >
            Clarify{openQs > 0 ? ` (${openQs})` : ''}
          </button>
          <button
            type="button"
            onClick={async () => {
              setBusy(true);
              try { await addAllApprovedToBoard(); } finally { setBusy(false); }
            }}
            disabled={approved.length === 0 || busy}
            className="px-3 py-1.5 rounded-[var(--r-sm)] bg-[var(--accent)] text-white text-xs font-semibold cursor-pointer disabled:opacity-40"
          >
            Add all approved{approved.length > 0 ? ` (${approved.length})` : ''}
          </button>
        </div>
      </div>

      {clarify && (
        <FeatureClarification onClose={() => setClarify(false)} />
      )}

      {features.length === 0 && (
        <div className="p-8 border rounded-[var(--r-lg)] border-stone-200 dark:border-stone-800 text-center text-stone-400">
          <p className="text-sm font-semibold text-stone-700 dark:text-stone-200">No features yet.</p>
          <p className="text-xs mt-1">Upload a PDF, DOCX or Markdown file on Sources, or stay in Chat while extraction runs.</p>
          <div className="mt-3 flex items-center justify-center gap-3">
            <button type="button" onClick={() => setActiveView('chat')} className="text-xs font-semibold text-[var(--accent)] cursor-pointer">
              Open Chat
            </button>
            <button type="button" onClick={() => setActiveView('sources')} className="text-xs font-semibold text-stone-500 dark:text-stone-400 cursor-pointer">
              Go to Sources
            </button>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {features.map(f => (
          <FeatureInspectCard
            key={f.id}
            feature={f}
            activity={featureActivity[f.id] || []}
            markdown={featureMarkdown[f.documentId]}
            onLoadExtras={() => { void loadFeatureExtras(f.id, f.documentId); }}
          />
        ))}
      </div>

      {documents.some(d => d.status === 'analysing' || d.status === 'extracting') && (
        <p className="text-[11px] font-mono text-stone-400">Agents are still working on an upload…</p>
      )}
    </div>
  );
};
