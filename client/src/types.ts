export type Priority = 'P0' | 'P1' | 'P2' | 'P3';
export type Status = 'inbox' | 'next' | 'in_progress' | 'done';

export type VerdictType = 'net-new' | 'duplicate' | 'conflict' | 'impact' | 'checking';

export interface Candidate {
  id: string; // e.g. '#142' or 'decision-4'
  type: 'item' | 'decision';
  title: string;
  reason: string;
  confidence: number;
}

export interface VerdictDetail {
  type: VerdictType;
  confidence: number;
  message: string;
  candidates: Candidate[];
  citation?: {
    id: string;
    type: 'item' | 'decision' | 'source';
    title: string;
    snippet: string;
  };
}

export interface WebSource {
  id: string;
  name: string;
  type: 'sheet' | 'transcript' | 'email' | 'ticket' | 'upload';
  status: 'synced' | 'syncing' | 'error' | 'needs_auth';
  lastSynced?: string;
  pendingCount: number;
}

export interface IngestItem {
  id: string;
  title: string;
  description: string;
  area: string;
  priority: Priority;
  sourceId: string;
  sourceSnippet: string;
  verdict: VerdictDetail;
}

export interface Item {
  id: number;
  title: string;
  description: string;
  status: Status;
  priority: Priority;
  assignee: string;
  area: string;
  created_at: string;
  source: {
    type: 'sheet' | 'call' | 'ticket' | 'email' | 'upload';
    name: string;
    snippet?: string;
  } | null;
  verdict: VerdictDetail | null;
}

export interface Decision {
  id: number;
  title: string;
  description: string;
  date: string;
  area: string;
  createdBy: string;
  sourceSnippet?: string;
}

export type AgentKind = 'design' | 'code' | 'qa' | 'docs' | 'test' | 'security' | 'custom';

export interface Agent {
  id: string;          // 'figma-ai' | 'custom-<ts>'
  name: string;        // 'Figma AI'
  kind: AgentKind;
  description?: string;
  builtin: boolean;
}

export interface ProjectSummary {
  id: string;
  name: string;
  createdAt: string;
  itemCount: number;
  decisionCount: number;
  sourceCount: number;
  pendingCount: number;
}

// Frontend-only draft captured by the guided New Project setup (§4.10). None of
// this touches the backend contract yet — description/github/media are used to
// drive task generation + the clarification chat, then discarded.
export type DraftSourceKind = 'file' | 'video' | 'image';

export interface DraftSource {
  name: string;
  kind: DraftSourceKind;
  size: number;
  content?: string;          // only text files are read client-side
  status: 'reading' | 'ready';
}

export interface ClarificationTurn {
  question: string;
  answer: string;
}

export interface NewProjectDraft {
  name: string;
  description: string;
  github: string;
  sources: DraftSource[];
  answers: ClarificationTurn[];
}

export interface DBState {
  items: Item[];
  decisions: Decision[];
  sources: WebSource[];
  ingestQueue: IngestItem[];
  agents: Agent[];
  apiConfig: {
    provider: 'managed' | 'byok';
    providerType: 'gemini' | 'anthropic';
    apiKey: string;
    region: string;
    embeddingsProvider: 'voyage' | 'gemini';
    embeddingsKey: string;
    noRetention: boolean;
    isolateTenant: boolean;
  };
}
