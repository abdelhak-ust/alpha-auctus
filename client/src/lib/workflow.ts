import { DOC_RUNNING } from './backend.js';
import {
  Feature,
  FeatureReviewStatus,
  GenerationMode,
  MvpDocument,
  WorkflowStage,
} from '../types.js';

export function reviewStatusOf(feature: Feature): FeatureReviewStatus {
  return feature.reviewStatus ?? 'pending';
}

export function openQuestions(feature: Feature) {
  return feature.questions.filter(q => q.status === 'open');
}

export function openQuestionCount(feature: Feature): number {
  return openQuestions(feature).length;
}

export function canApproveFeature(feature: Feature): boolean {
  return openQuestionCount(feature) === 0 && reviewStatusOf(feature) !== 'approved';
}

export function nonRejected(features: Feature[]): Feature[] {
  return features.filter(f => reviewStatusOf(f) !== 'rejected').sort((a, b) => a.position - b.position);
}

export function pendingReview(features: Feature[]): Feature[] {
  return nonRejected(features).filter(f => reviewStatusOf(f) === 'pending');
}

export function approvedFeatures(features: Feature[]): Feature[] {
  return features.filter(f => reviewStatusOf(f) === 'approved').sort((a, b) => a.position - b.position);
}

export function draftTasksOf(features: Feature[]) {
  return features.flatMap(f => f.tasks.filter(t => t.status === 'draft').map(t => ({ feature: f, task: t })));
}

export function approvedBoardReady(features: Feature[]) {
  return features.flatMap(f => f.tasks.filter(t => t.status === 'approved').map(t => ({ feature: f, task: t })));
}

export function onBoardCount(features: Feature[]): number {
  return features.reduce((n, f) => n + f.tasks.filter(t => t.status === 'on_board').length, 0);
}

export function ingestRunning(documents: MvpDocument[]): boolean {
  return documents.some(d => DOC_RUNNING.has(d.status));
}

export function inferFeatureMode(features: Feature[], stored: GenerationMode | null): GenerationMode | null {
  if (stored) return stored;
  if (features.some(f => reviewStatusOf(f) !== 'pending')) return 'auto';
  return null;
}

export function inferTaskMode(features: Feature[], stored: GenerationMode | null): GenerationMode | null {
  if (stored) return stored;
  if (features.some(f => f.tasks.length > 0 || f.status === 'planning' || f.status === 'tasks_ready')) return 'auto';
  return null;
}

export function deriveWorkflowStage(opts: {
  documents: MvpDocument[];
  features: Feature[];
  featureMode: GenerationMode | null;
  taskMode: GenerationMode | null;
}): WorkflowStage {
  const { documents, features, featureMode, taskMode } = opts;
  const running = ingestRunning(documents);
  const reviewable = nonRejected(features);
  const approved = approvedFeatures(features);

  // Stay on ingest until documents finish — review-as-you-go is presentation
  // gating after extraction, not a pause of document_graph. If the user already
  // chose a mode, keep them in review even if a later upload is running.
  if (!featureMode && (running || features.length === 0)) return 'ingesting';

  if (!featureMode) return 'choose_feature_mode';

  const allReviewed = reviewable.length > 0 && reviewable.every(f => reviewStatusOf(f) === 'approved');
  if (!allReviewed) return 'review_features';

  if (!taskMode) return 'choose_task_mode';

  const stillGenerating = approved.some(f => f.status === 'planning' || (f.tasks.length === 0 && f.status !== 'tasks_ready'));
  const hasDrafts = approved.some(f => f.tasks.some(t => t.status === 'draft'));
  if (stillGenerating || hasDrafts) return 'review_tasks';

  return 'publish';
}

export interface StepperStep {
  id: 'sources' | 'features' | 'tasks' | 'board';
  label: string;
  view: 'sources' | 'features' | 'board';
  state: 'done' | 'current' | 'todo';
}

export function workflowSteps(documents: MvpDocument[], features: Feature[]): StepperStep[] {
  const sourcesDone = documents.some(d => d.status === 'ready');
  const featuresDone = features.some(f => reviewStatusOf(f) === 'approved');
  const tasksDone = features.some(f => f.tasks.some(t => t.status === 'approved' || t.status === 'on_board'));
  const boardDone = features.some(f => f.tasks.some(t => t.status === 'on_board'));

  const flags = [sourcesDone, featuresDone, tasksDone, boardDone];
  const firstOpen = flags.findIndex(v => !v);

  const raw: Array<Omit<StepperStep, 'state'>> = [
    { id: 'sources', label: 'Sources', view: 'sources' },
    { id: 'features', label: 'Features', view: 'features' },
    { id: 'tasks', label: 'Tasks', view: 'features' },
    { id: 'board', label: 'Board', view: 'board' },
  ];

  return raw.map((step, i) => ({
    ...step,
    state: flags[i] ? 'done' : i === firstOpen ? 'current' : 'todo',
  }));
}
