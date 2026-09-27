import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useProject } from '../context/ProjectContext.js';
import {
  AiBubble,
  ChatFeatureCard,
  ChatFooterLinks,
  FeatureTaskReview,
  GenerationModePicker,
  HistoryMessage,
  IngestProgressBlock,
  PmBubble,
  ReadyTasksTable,
  ReviewAllPanel,
  TaskProgressList,
} from './ChatBlocks.js';
import {
  approvedBoardReady,
  approvedFeatures,
  canApproveFeature,
  deriveWorkflowStage,
  inferFeatureMode,
  inferTaskMode,
  ingestRunning,
  nonRejected,
  pendingReview,
  reviewStatusOf,
} from '../lib/workflow.js';
import { ChatMessage, GenerationMode } from '../types.js';

export const ProjectChat: React.FC = () => {
  const {
    documents,
    features,
    workflowHistory,
    featureGenMode,
    taskGenMode,
    setFeatureGenMode,
    setTaskGenMode,
    refreshFeatures,
    activeProjectId,
    generateFeatureTasks,
    generateApprovedFeatureTasks,
    approveAllDraftTasks,
    addAllApprovedToBoard,
    approveFeature,
  } = useProject();

  const [reviewAll, setReviewAll] = useState(false);
  const [localLog, setLocalLog] = useState<ChatMessage[]>([]);
  const [adding, setAdding] = useState(false);
  const [addedCount, setAddedCount] = useState(0);
  const logRef = useRef<HTMLDivElement>(null);
  const kickedTaskGen = useRef<Set<string>>(new Set());
  const announcedIngest = useRef(false);

  const featureMode = inferFeatureMode(features, featureGenMode);
  const taskMode = inferTaskMode(features, taskGenMode);
  const stage = deriveWorkflowStage({ documents, features, featureMode, taskMode });

  useEffect(() => { void refreshFeatures(); }, [activeProjectId]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' });
  }, [workflowHistory, localLog, stage, features, documents]);

  const pushLocal = (text: string, role: ChatMessage['role'] = 'ai', kind: ChatMessage['kind'] = 'text') => {
    setLocalLog(prev => [...prev, {
      id: `local-${Date.now()}-${prev.length}`,
      projectId: '',
      role,
      text,
      createdAt: new Date().toString(),
      kind,
    }]);
  };

  useEffect(() => {
    if (announcedIngest.current) return;
    if (ingestRunning(documents) || (documents.length === 0 && features.length === 0)) return;
    if (features.length === 0 && documents.every(d => d.status === 'failed')) {
      announcedIngest.current = true;
      pushLocal("I couldn't extract features from these files. Open Sources to retry, or stay here.", 'ai', 'progress');
      return;
    }
    if (features.length > 0 && !ingestRunning(documents)) {
      announcedIngest.current = true;
      pushLocal(`I identified ${features.length} feature${features.length === 1 ? '' : 's'}.`, 'ai', 'progress');
    }
  }, [documents, features]);

  const chooseFeatureMode = (mode: GenerationMode) => {
    setFeatureGenMode(mode);
    pushLocal(mode === 'auto' ? 'Auto — show every feature.' : 'Review as you go — one feature at a time.', 'pm', 'decision');
  };

  const chooseTaskMode = (mode: GenerationMode) => {
    setTaskGenMode(mode);
    pushLocal(mode === 'auto' ? 'Auto — generate tasks for every approved feature.' : 'Review as you go — generate one feature at a time.', 'pm', 'decision');
  };

  const reviewable = nonRejected(features);
  const pending = pendingReview(features);
  const approved = approvedFeatures(features);
  const currentFeature = pending[0];
  const featureOrdinal = currentFeature
    ? reviewable.findIndex(f => f.id === currentFeature.id) + 1
    : 0;

  const currentTaskFeature = useMemo(() => {
    return approved.find(f =>
      f.status === 'planning' ||
      f.tasks.length === 0 ||
      f.tasks.some(t => t.status === 'draft')
    ) ?? null;
  }, [approved]);

  useEffect(() => {
    if (stage !== 'review_tasks') return;
    if (taskMode === 'auto') {
      const due = approved.filter(f => f.tasks.length === 0 && f.status !== 'planning' && !kickedTaskGen.current.has(f.id));
      if (due.length === 0) return;
      due.forEach(f => kickedTaskGen.current.add(f.id));
      void generateApprovedFeatureTasks();
      return;
    }
    if (taskMode === 'review_as_you_go' && currentTaskFeature && currentTaskFeature.tasks.length === 0 && currentTaskFeature.status !== 'planning') {
      if (kickedTaskGen.current.has(currentTaskFeature.id)) return;
      kickedTaskGen.current.add(currentTaskFeature.id);
      void generateFeatureTasks(currentTaskFeature.id);
    }
  }, [stage, taskMode, approved, currentTaskFeature, generateApprovedFeatureTasks, generateFeatureTasks]);

  const approveUnblocked = async () => {
    const ready = pending.filter(canApproveFeature);
    for (const f of ready) await approveFeature(f.id);
    if (ready.length) pushLocal(`Approved ${ready.length} feature${ready.length === 1 ? '' : 's'} with no open questions.`, 'pm', 'decision');
  };

  const history = useMemo(() => {
    const seen = new Set(workflowHistory.map(m => m.text));
    return [...workflowHistory, ...localLog.filter(m => !seen.has(m.text))];
  }, [workflowHistory, localLog]);

  const readyTasks = approvedBoardReady(features);
  const allApprovedCount = approved.length;

  return (
    <div className="h-full min-h-0 flex-1 flex flex-col max-w-[720px] mx-auto w-full">
      <div ref={logRef} aria-live="polite" className="flex-1 min-h-0 overflow-y-auto space-y-5 pb-6">
        {history.map(m => <HistoryMessage key={m.id} msg={m} />)}

        {stage === 'ingesting' && <IngestProgressBlock documents={documents} />}

        {stage === 'choose_feature_mode' && features.length > 0 && (
          <GenerationModePicker
            title={`I identified ${features.length} feature${features.length === 1 ? '' : 's'}. How should I present them for review?`}
            autoHint="Show every feature now. Approve only those with no open questions; the rest stay listed as blocked."
            reviewHint="One feature at a time. Next is gated on Approve or Reject. Review all stays available."
            onChoose={chooseFeatureMode}
          />
        )}

        {stage === 'choose_feature_mode' && features.length === 0 && !ingestRunning(documents) && (
          <AiBubble>
            I didn’t find any features in these documents. Open Sources to upload another file, or stay here.
          </AiBubble>
        )}

        {stage === 'review_features' && featureMode === 'auto' && (
          <div className="space-y-3">
            <AiBubble>
              Review the features below. Approve is disabled while a feature still has open questions — answer or skip them first.
            </AiBubble>
            {reviewable.map(f => <ChatFeatureCard key={f.id} feature={f} />)}
            <div className="flex flex-wrap gap-2 ml-9">
              <button
                type="button"
                onClick={() => setReviewAll(true)}
                className="px-3 py-1.5 rounded-[var(--r-sm)] border border-stone-200 dark:border-stone-800 text-xs font-semibold text-stone-700 dark:text-stone-200 cursor-pointer"
              >
                Review all
              </button>
              <button
                type="button"
                disabled={pending.filter(canApproveFeature).length === 0}
                onClick={() => { void approveUnblocked(); }}
                className="px-3 py-1.5 rounded-[var(--r-sm)] bg-stone-900 dark:bg-stone-100 text-white dark:text-stone-900 text-xs font-semibold cursor-pointer disabled:opacity-40"
              >
                Approve unblocked
              </button>
            </div>
          </div>
        )}

        {stage === 'review_features' && pending.length === 0 && reviewable.length === 0 && (
          <AiBubble>
            All features were rejected, so there’s nothing to turn into tasks. Open Sources to add another document.
          </AiBubble>
        )}

        {stage === 'review_features' && featureMode === 'review_as_you_go' && currentFeature && (
          <div className="space-y-3">
            <AiBubble>
              Feature {featureOrdinal} of {reviewable.length}. Approve stays off until every open question is answered or skipped.
            </AiBubble>
            <ChatFeatureCard
              feature={currentFeature}
              indexLabel={`Feature ${featureOrdinal} of ${reviewable.length}`}
            />
            <button
              type="button"
              onClick={() => setReviewAll(true)}
              className="ml-9 text-xs font-semibold text-stone-600 dark:text-stone-300 cursor-pointer"
            >
              Review all
            </button>
          </div>
        )}

        {stage === 'choose_task_mode' && (
          <GenerationModePicker
            title={`Great. I’ve got ${allApprovedCount} approved feature${allApprovedCount === 1 ? '' : 's'}. How should I generate tasks?`}
            autoHint="Generate tasks for every approved feature and show a live list as they land."
            reviewHint="Generate one feature, then review those tasks before the next."
            onChoose={chooseTaskMode}
          />
        )}

        {stage === 'review_tasks' && taskMode === 'auto' && (
          <div className="space-y-3">
            <AiBubble>Generating tasks for each approved feature.</AiBubble>
            <TaskProgressList features={approved} />
            {approved.some(f => f.tasks.length > 0) && (
              <div className="space-y-4">
                {approved.filter(f => f.tasks.length > 0).map(f => (
                  <FeatureTaskReview key={f.id} feature={f} hideBoard />
                ))}
                {approved.some(f => f.tasks.some(t => t.status === 'draft')) && (
                  <button
                    type="button"
                    onClick={() => { void approveAllDraftTasks(); }}
                    className="px-3 py-1.5 rounded-[var(--r-sm)] bg-stone-900 dark:bg-stone-100 text-white dark:text-stone-900 text-xs font-semibold cursor-pointer"
                  >
                    Approve all drafts
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {stage === 'review_tasks' && taskMode === 'review_as_you_go' && currentTaskFeature && (
          <div className="space-y-3">
            {currentTaskFeature.status === 'planning' || currentTaskFeature.tasks.length === 0 ? (
              <AiBubble>Generating tasks for “{currentTaskFeature.name}”…</AiBubble>
            ) : (
              <>
                <AiBubble>
                  I’ve generated {currentTaskFeature.tasks.length} task{currentTaskFeature.tasks.length === 1 ? '' : 's'} for “{currentTaskFeature.name}”.
                </AiBubble>
                <FeatureTaskReview feature={currentTaskFeature} hideBoard />
              </>
            )}
            <TaskProgressList features={approved} />
          </div>
        )}

        {stage === 'publish' && (
          <div className="space-y-3">
            <AiBubble>
              {addedCount > 0
                ? `${addedCount} task${addedCount === 1 ? '' : 's'} added to the board.`
                : 'Approved tasks are ready. Add them to the board when you are.'}
            </AiBubble>
            {readyTasks.length > 0 && (
              <ReadyTasksTable
                tasks={readyTasks}
                adding={adding}
                onAdd={async () => {
                  setAdding(true);
                  try {
                    const n = readyTasks.length;
                    await addAllApprovedToBoard();
                    setAddedCount(n);
                    pushLocal(`Added ${n} task${n === 1 ? '' : 's'} to the board.`, 'pm', 'decision');
                  } finally {
                    setAdding(false);
                  }
                }}
              />
            )}
            {addedCount > 0 && readyTasks.length === 0 && (
              <PmBubble>Open Board to see them in inbox.</PmBubble>
            )}
          </div>
        )}
      </div>

      <div className="pt-3 border-t border-stone-200/60 dark:border-stone-850/60 shrink-0">
        <ChatFooterLinks onReviewAll={() => setReviewAll(true)} />
      </div>

      {reviewAll && (
        <ReviewAllPanel features={features.filter(f => reviewStatusOf(f) !== 'rejected')} onClose={() => setReviewAll(false)} />
      )}
    </div>
  );
};
