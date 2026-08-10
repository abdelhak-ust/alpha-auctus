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

// ── BUILD → VERIFY → DELIVER (spec §4.12–4.14) ────────────────────────────────
// These lifecycle stages are UI-ahead-of-architecture (see ui_ux_design.md §14):
// there is no backend for them yet, so the client derives them deterministically
// from the board's items via lib/delivery.ts. The shapes below are the contract
// those screens render against.

// §4.12 Runs — live agent execution
export type RunStatus = 'queued' | 'running' | 'blocked' | 'done' | 'failed' | 'stopped';
export type ACState = 'done' | 'in_progress' | 'not_started' | 'blocked';

export interface RunActivity {
  time: string;
  kind: 'read' | 'edit' | 'run' | 'note' | 'blocked';
  text: string;
}

export interface RunFile {
  path: string;
  change: 'M' | 'A' | 'D';
  added: number;
  removed: number;
}

export interface AcceptanceCriterion {
  id: string;      // 'AC1'
  label: string;
  state: ACState;
}

export interface Run {
  id: string;
  itemId: number;
  itemTitle: string;
  agentName: string;
  agentKind: AgentKind;
  status: RunStatus;
  progress: number;            // 0–100
  commands: number;
  activity: RunActivity[];
  files: RunFile[];
  criteria: AcceptanceCriterion[];
  selfAssessment: string;
  blockingQuestion?: string;   // present when status === 'blocked'
}

// §4.13 Requirement-validation review (the co-hero coverage matrix)
export type CoverageState = 'met' | 'partial' | 'unmet' | 'off-task' | 'unverifiable';

export interface RequirementCoverage {
  id: string;                  // 'R1'
  requirement: string;
  state: CoverageState;
  reason?: string;
  codeCitation?: { file: string; line?: number };
  reqCitation?: string;        // 'task AC #3' | 'PRD §4.2'
  suggestedHome?: string;      // for off-task rows: 'belongs to #98?'
  lowConfidence?: boolean;     // tinted --warning, excluded from bulk accept
  tested?: boolean;
}

export type ReviewVerdict = 'all-met' | 'needs-work' | 'off-task';

export interface Review {
  id: string;
  itemId: number;
  itemTitle: string;
  agentName: string;
  agentKind: AgentKind;
  runTime: string;
  coverage: RequirementCoverage[];
  metCount: number;
  unmetCount: number;
  offTaskCount: number;
  totalCount: number;
  overall: ReviewVerdict;
  regressionNote?: string;
}

// §4.14 Delivery — PR · CI/CD · deploy, with continuous requirement re-check
export type PRStatus = 'open' | 'merged' | 'deployed';
export type CheckState = 'passing' | 'failing' | 'running';

export interface Delivery {
  id: string;
  itemId: number;
  itemTitle: string;
  prNumber: number;
  status: PRStatus;
  ci: CheckState;
  build: CheckState;
  lint: CheckState;
  commits: number;
  files: number;
  reqMet: number;
  reqTotal: number;
  reqWas?: number;             // coverage at review time (delta shown, e.g. 5/7 → 7/7)
  fixedNotes?: { req: string; file: string }[];
  deployStaging?: string;
  deployProd?: 'live' | 'awaiting' | 'failed';
  ciFailCount?: number;
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
