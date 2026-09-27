// Typed client for the MVP endpoints served by backend/ (FastAPI).
// Contract: plans/mvp-v0.md. The browser calls the backend directly — no Node proxy.
// Board data (items, decisions, projects, agents, settings) stays on client/server.ts.

import {
  AgentActivity,
  AskResponse,
  AskTurn,
  AuthorRequest,
  AuthorResponse,
  ClarificationAnswerResponse,
  ClarificationState,
  Feature,
  FeaturePatch,
  GeneratedTask,
  ImpactExplainRequest,
  ImpactExplainResponse,
  MvpDocument,
  Status,
  VerdictDetail,
  WorkflowState,
} from '../types.js';

const env = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env;

export const BACKEND_URL: string = (env?.VITE_BACKEND_URL || 'http://localhost:8000').replace(/\/+$/, '');

const API = `${BACKEND_URL}/api`;

export const INGEST_EXTENSIONS = ['pdf', 'docx', 'md'] as const;
export const INGEST_ACCEPT = INGEST_EXTENSIONS.map(e => `.${e}`).join(',');

export const isIngestibleFile = (name: string): boolean =>
  (INGEST_EXTENSIONS as readonly string[]).includes((name.split('.').pop() || '').toLowerCase());

export const withPeriod = (s: string): string => {
  const t = s.trim();
  return /[.!?]$/.test(t) ? t : `${t}.`;
};

export class BackendError extends Error {
  readonly problem: string;
  readonly cause: string;
  readonly fix: string;
  readonly status: number;

  constructor(problem: string, cause: string, fix: string, status: number) {
    super(`${problem} ${cause} ${fix}`);
    this.name = 'BackendError';
    this.problem = problem;
    this.cause = cause;
    this.fix = fix;
    this.status = status;
  }

  toDisplay(): string {
    const strip = (s: string) => s.trim().replace(/[.\s]+$/, '');
    return `${strip(this.problem)} (${strip(this.cause)}). ${strip(this.fix)}.`;
  }
}

const isStructuredDetail = (d: unknown): d is { problem: string; cause: string; fix: string } =>
  !!d && typeof d === 'object' &&
  typeof (d as any).problem === 'string' && typeof (d as any).cause === 'string' && typeof (d as any).fix === 'string';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, init);
  } catch {
    throw new BackendError(
      "Couldn't reach the backend",
      `no response from ${BACKEND_URL} — the backend isn't running, or it doesn't allow this origin (CORS)`,
      'Start the backend (cd backend && poetry run uvicorn app.main:app --port 8000) or check VITE_BACKEND_URL, then retry',
      0
    );
  }

  if (!res.ok) {
    let body: any = null;
    try { body = await res.json(); } catch { /* non-JSON error body */ }
    const detail = body?.detail;
    if (isStructuredDetail(detail)) {
      throw new BackendError(detail.problem, detail.cause, detail.fix, res.status);
    }
    const cause = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((d: any) => d?.msg).filter(Boolean).join('; ') || `HTTP ${res.status}`
        : `HTTP ${res.status} ${res.statusText}`.trim();
    throw new BackendError('The backend rejected the request', cause, 'Check the backend logs, then retry', res.status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

export function uploadDocument(projectId: string, file: File): Promise<MvpDocument> {
  const form = new FormData();
  form.append('file', file, file.name);
  return request<MvpDocument>(`/projects/${enc(projectId)}/documents`, { method: 'POST', body: form });
}

export function listDocuments(projectId: string): Promise<MvpDocument[]> {
  return request<MvpDocument[]>(`/projects/${enc(projectId)}/documents`);
}

export function getDocument(projectId: string, documentId: string): Promise<MvpDocument> {
  return request<MvpDocument>(`/projects/${enc(projectId)}/documents/${enc(documentId)}`);
}

export function getDocumentMarkdown(projectId: string, documentId: string): Promise<{ markdown: string }> {
  return request<{ markdown: string }>(`/projects/${enc(projectId)}/documents/${enc(documentId)}/markdown`);
}

export function listFeatures(projectId: string): Promise<Feature[]> {
  return request<Feature[]>(`/projects/${enc(projectId)}/features`);
}

export function getFeature(projectId: string, featureId: string): Promise<Feature> {
  return request<Feature>(`/projects/${enc(projectId)}/features/${enc(featureId)}`);
}

export function patchFeature(projectId: string, featureId: string, body: FeaturePatch): Promise<Feature> {
  return request<Feature>(`/projects/${enc(projectId)}/features/${enc(featureId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function getFeatureActivity(projectId: string, featureId: string): Promise<AgentActivity[]> {
  return request<AgentActivity[]>(`/projects/${enc(projectId)}/features/${enc(featureId)}/activity`);
}

export function getClarification(projectId: string): Promise<ClarificationState> {
  return request<ClarificationState>(`/projects/${enc(projectId)}/clarification`);
}

export function answerClarification(projectId: string, questionId: string, answer: string): Promise<ClarificationAnswerResponse> {
  return request<ClarificationAnswerResponse>(`/projects/${enc(projectId)}/clarification/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ questionId, answer }),
  });
}

export function skipClarification(projectId: string, questionId: string): Promise<ClarificationAnswerResponse> {
  return request<ClarificationAnswerResponse>(`/projects/${enc(projectId)}/clarification/skip`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ questionId }),
  });
}

export function skipRemainingClarification(projectId: string, featureId: string): Promise<ClarificationAnswerResponse> {
  return request<ClarificationAnswerResponse>(`/projects/${enc(projectId)}/clarification/skip-remaining`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ featureId }),
  });
}

export async function getWorkflow(projectId: string): Promise<WorkflowState> {
  try {
    return await request<WorkflowState>(`/projects/${enc(projectId)}/workflow`);
  } catch (e) {
    if (e instanceof BackendError && (e.status === 404 || e.status === 405)) {
      const clar = await getClarification(projectId);
      return { history: clar.history };
    }
    throw e;
  }
}

export function generateTasks(projectId: string, featureId: string): Promise<Feature> {
  return request<Feature>(`/projects/${enc(projectId)}/features/${enc(featureId)}/tasks/generate`, { method: 'POST' });
}

export function patchTask(
  projectId: string,
  taskId: string,
  body: { status?: GeneratedTask['status']; title?: string; description?: string; priority?: GeneratedTask['priority']; boardItemId?: number }
): Promise<GeneratedTask> {
  return request<GeneratedTask>(`/projects/${enc(projectId)}/tasks/${enc(taskId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function askAboutItem(
  projectId: string,
  body: {
    query: string;
    boardItemId: number;
    item: { title: string; description: string; area: string; priority: string };
    history: AskTurn[];
  },
): Promise<AskResponse> {
  return request<AskResponse>(`/projects/${enc(projectId)}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function askProjectMemory(
  projectId: string,
  body: {
    query: string;
    history?: AskTurn[];
    boardItems: { id: number; title: string; description: string; area: string; status: Status }[];
  },
): Promise<AskResponse> {
  return request<AskResponse>(`/projects/${enc(projectId)}/memory/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function explainImpact(
  projectId: string,
  body: ImpactExplainRequest,
): Promise<ImpactExplainResponse> {
  return request<ImpactExplainResponse>(`/projects/${enc(projectId)}/impact/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function authorDocument(
  projectId: string,
  body: AuthorRequest,
): Promise<AuthorResponse> {
  return request<AuthorResponse>(`/projects/${enc(projectId)}/author`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function checkItemVerdict(
  projectId: string,
  item: { id: number; title: string; description: string; area: string },
  boardItems: { id: number; title: string; description: string; area: string; status: Status }[],
): Promise<VerdictDetail> {
  return request<VerdictDetail>(`/projects/${enc(projectId)}/verdicts/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item, boardItems }),
  });
}

export const DOC_RUNNING = new Set(['uploaded', 'converting', 'extracting', 'analysing']);

export function progressLabel(doc: MvpDocument): string {
  const p = doc.progress;
  const step = p?.step || doc.status;
  const done = p?.done ?? 0;
  const total = p?.total ?? 0;
  if (step === 'extracting' && total) return `Extractor: chunk ${done}/${total}`;
  if (step === 'analysing' && total) return `Analyst: ${done}/${total} features`;
  if (step === 'converting') return 'Converting to Markdown…';
  if (step === 'ready') return `${doc.featureCount} feature${doc.featureCount === 1 ? '' : 's'}`;
  if (step === 'failed') return 'Failed';
  return step;
}
