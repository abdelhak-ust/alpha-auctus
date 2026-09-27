// Typed client for the ingestion endpoints served by backend/ (FastAPI).
// Contract: plans/ingestion.md §11.1 (frozen). The browser calls the backend
// directly — no Node proxy (plans/feature-pipeline-contract.md §8). Board data
// (items, decisions, projects, agents, settings) stays on client/server.ts.

import { IngestDocument, IngestItem, RegistryFeature } from '../types.js';

const env = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env;

export const BACKEND_URL: string = (env?.VITE_BACKEND_URL || 'http://localhost:8000').replace(/\/+$/, '');

const API = `${BACKEND_URL}/api`;

// v1 file types (plans/ingestion.md §9). Anything else is refused before upload.
export const INGEST_EXTENSIONS = ['pdf', 'docx', 'md', 'txt'] as const;
export const INGEST_ACCEPT = INGEST_EXTENSIONS.map(e => `.${e}`).join(',');

export const isIngestibleFile = (name: string): boolean =>
  (INGEST_EXTENSIONS as readonly string[]).includes((name.split('.').pop() || '').toLowerCase());

/** Ends a sentence with a period unless it already ends in . ! or ? */
export const withPeriod = (s: string): string => {
  const t = s.trim();
  return /[.!?]$/.test(t) ? t : `${t}.`;
};

/** Error shape from the backend: `{ detail: { problem, cause, fix } }` (ui_ux_design.md §7). */
export class BackendError extends Error {
  readonly problem: string;
  readonly cause: string;
  readonly fix: string;
  readonly status: number; // 0 = no response (network / CORS)

  constructor(problem: string, cause: string, fix: string, status: number) {
    super(`${problem} ${cause} ${fix}`);
    this.name = 'BackendError';
    this.problem = problem;
    this.cause = cause;
    this.fix = fix;
    this.status = status;
  }

  /** One-line "problem (cause). fix" rendering for inline errors / toasts. */
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
      "Couldn't reach the ingestion service",
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
    throw new BackendError('The ingestion service rejected the request', cause, 'Check the backend logs, then retry', res.status);
  }

  return (await res.json()) as T;
}

const enc = encodeURIComponent;

/** POST /projects/{projectId}/documents — 202 new, 200 + `duplicate: true` for a known hash. */
export function uploadIngestDocument(projectId: string, file: File): Promise<IngestDocument> {
  const form = new FormData();
  form.append('file', file, file.name);
  return request<IngestDocument>(`/projects/${enc(projectId)}/documents`, { method: 'POST', body: form });
}

/** GET /projects/{projectId}/documents */
export function listIngestDocuments(projectId: string): Promise<IngestDocument[]> {
  return request<IngestDocument[]>(`/projects/${enc(projectId)}/documents`);
}

/** GET /projects/{projectId}/documents/{documentId} */
export function getIngestDocument(projectId: string, documentId: string): Promise<IngestDocument> {
  return request<IngestDocument>(`/projects/${enc(projectId)}/documents/${enc(documentId)}`);
}

/** GET /projects/{projectId}/features */
export function listRegistryFeatures(projectId: string): Promise<RegistryFeature[]> {
  return request<RegistryFeature[]>(`/projects/${enc(projectId)}/features`);
}

/** GET /projects/{projectId}/review-queue */
export function getReviewQueue(projectId: string): Promise<IngestItem[]> {
  return request<IngestItem[]>(`/projects/${enc(projectId)}/review-queue`);
}

/** POST /projects/{projectId}/review-queue/{itemId}/resolve */
export function resolveReviewItem(projectId: string, itemId: string, action: 'approve' | 'dismiss'): Promise<{ ok: true }> {
  return request<{ ok: true }>(`/projects/${enc(projectId)}/review-queue/${enc(itemId)}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action })
  });
}

const TERMINAL = new Set(['done', 'failed']);

/**
 * Polls a document until it reaches `done` or `failed`. Resolves with the final
 * document; rejects with BackendError if the backend stops answering or the
 * timeout elapses (never silently gives up).
 */
export async function waitForIngestDocument(
  projectId: string,
  documentId: string,
  opts: { intervalMs?: number; timeoutMs?: number; onUpdate?: (d: IngestDocument) => void } = {}
): Promise<IngestDocument> {
  const interval = opts.intervalMs ?? 2000;
  const deadline = Date.now() + (opts.timeoutMs ?? 10 * 60 * 1000);
  for (;;) {
    const doc = await getIngestDocument(projectId, documentId);
    opts.onUpdate?.(doc);
    if (TERMINAL.has(doc.status)) return doc;
    if (Date.now() > deadline) {
      throw new BackendError(
        `Ingestion of ${doc.filename} is taking longer than expected`,
        `still "${doc.status}" after ${Math.round((opts.timeoutMs ?? 600000) / 60000)} min`,
        'Check the backend worker (arq) is running; the document keeps processing in the background',
        0
      );
    }
    await new Promise(r => setTimeout(r, interval));
  }
}
