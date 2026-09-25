import type { Agent, DBState, Decision, IngestItem, Item, WebSource } from '../src/types.js';

// A project owns its own board, memory, sources and ingest queue. The AI/data posture
// (apiConfig) and the agent catalog are workspace-level, shared across projects.
// This is the same shape the JSON store used, so read-only code (ask/author/verdict analysis)
// keeps consuming a plain snapshot and needs no changes.
export interface ProjectRecord {
  id: string;
  name: string;
  createdAt: string;
  items: Item[];
  decisions: Decision[];
  sources: WebSource[];
  ingestQueue: IngestItem[];
}

export type ApiConfig = DBState['apiConfig'];

// Everything the old client/data/database.json held.
export interface StoreShape {
  projects: ProjectRecord[];
  apiConfig: ApiConfig;
  agents: Agent[];
}
