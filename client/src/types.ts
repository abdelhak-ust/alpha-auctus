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

// ── MVP v0 (plans/mvp-v0.md) — backend/ FastAPI under /api/projects/{projectId}/…
// Matching Pydantic schemas: backend/app/schemas/mvp.py (camelCase on the wire).
export type DocumentStatus = 'uploaded' | 'converting' | 'extracting' | 'analysing' | 'ready' | 'failed';
export interface DocumentProgress { step: string; done: number; total: number; }
export interface MvpDocument {
  id: string; projectId: string; filename: string; mimeType?: string; sizeBytes?: number;
  status: DocumentStatus; progress?: DocumentProgress; error?: string; duplicate?: boolean;
  featureCount: number; uploadedAt: string;
}
export interface SourceQuote {
  quote: string; verified: boolean; charStart?: number; charEnd?: number;
  origin?: 'document' | 'pm';
}
export interface CitedRequirement { text: string; quote?: string; }
export interface CitedCriterion { given: string; when: string; then: string; quote?: string; }
export interface FeatureDetails {
  description: string; userRoles: string[];
  functionalRequirements: CitedRequirement[];
  acceptanceCriteria: CitedCriterion[];
  constraints: string[]; dependencies: string[]; outOfScope: string[];
}
export type FeatureStatus = 'extracted' | 'analysed' | 'needs_clarification' | 'clarified' | 'planning' | 'tasks_ready';
export type FeatureReviewStatus = 'pending' | 'approved' | 'rejected';
export type GenerationMode = 'auto' | 'review_as_you_go';
export type ChatMessageKind = 'progress' | 'decision' | 'question' | 'text';
export type WorkflowStage = 'ingesting' | 'choose_feature_mode' | 'review_features' | 'choose_task_mode' | 'review_tasks' | 'publish';
export interface FeatureQuestion {
  id: string; featureId: string; question: string; why: string; targetField: string;
  isFollowUp: boolean; status: 'open' | 'answered' | 'skipped';
  answer?: string; answeredAt?: string; ordinal: number;
}
export type TaskStatus = 'draft' | 'approved' | 'on_board';
export type Estimate = 'S' | 'M' | 'L';
export interface GeneratedTask {
  id: string; featureId: string; title: string; description: string; area: string;
  priority: Priority; acceptanceCriteria: CitedCriterion[]; estimate: Estimate;
  tracesTo: string[]; subtasks: string[]; definitionOfDone: string[];
  reviewNotes?: string; status: TaskStatus;
  boardItemId?: number; ordinal: number;
}
export interface Feature {
  id: string; projectId: string; documentId: string; name: string; summary: string;
  details?: FeatureDetails; sourceQuotes: SourceQuote[]; status: FeatureStatus;
  reviewStatus: FeatureReviewStatus;
  position: number; questions: FeatureQuestion[]; tasks: GeneratedTask[];
  createdAt: string; updatedAt: string;
}
export interface FeaturePatch {
  reviewStatus?: FeatureReviewStatus;
  name?: string;
  summary?: string;
}
export interface ChatMessage {
  id: string; projectId: string; role: 'ai' | 'pm'; text: string;
  questionId?: string; featureId?: string; createdAt: string;
  kind?: ChatMessageKind;
}
export interface WorkflowState {
  history: ChatMessage[];
}
export interface AgentActivity {
  id: string; ts: string; graph: string; node: string; agent?: string; detail: string;
}
export interface ClarificationNext {
  questionId: string; featureId: string; featureName: string; question: string; why: string;
}
export interface ClarificationState {
  history: ChatMessage[]; next: ClarificationNext | null; remaining: number;
}
export interface ClarificationAnswerResponse {
  feature?: Feature; changes: string[]; next: ClarificationNext | null; remaining: number;
}

// Drawer Ask AI (plans/task-ask-ai.md) — cited answer scoped to one board card.
export interface AskCitation {
  id: string;
  type: 'item' | 'decision' | 'source';
  title: string;
  snippet?: string;
}
export interface AskTurn { role: 'user' | 'ai'; text: string }
export interface AskResponse { answer: string; citations: AskCitation[] }

// Author documents (POST /api/projects/{projectId}/author)
export type AuthorDocType = 'brd' | 'spec' | 'tree';
export type AuthorTimeFrame = '30' | '90' | '365';
export interface AuthorBoardItem {
  id: number;
  title: string;
  description: string;
  area: string;
  status: Status;
  createdAt: string;
  verdictType?: VerdictType;
}
export interface AuthorDecision {
  id: number;
  title: string;
  description: string;
  area: string;
}
export interface AuthorConflict {
  id: string;
  title: string;
}
export interface AuthorRequest {
  type: AuthorDocType;
  area: string;
  timeFrame: AuthorTimeFrame;
  boardItems: AuthorBoardItem[];
  decisions: AuthorDecision[];
}
export interface AuthorResponse {
  document: string;
  unresolvedConflictsCount: number;
  conflicts: AuthorConflict[];
  citations: AskCitation[];
}

// Trace impact graph (plans/trace-impact-graph.md)
export type ImpactNodeType = 'item' | 'area' | 'decision' | 'source';
export type ImpactEdgeType =
  | 'depends-on'
  | 'affects'
  | 'duplicate'
  | 'contradicts'
  | 'supersedes';

export interface ImpactNode {
  id: string;
  type: ImpactNodeType;
  label: string;
}

export interface ImpactEdge {
  id: string;
  source: string;
  target: string;
  type: ImpactEdgeType;
  label?: string;
}

export interface ImpactNeighbor {
  id: string;
  type: ImpactNodeType;
  label: string;
  edgeType: ImpactEdgeType;
}

export interface ImpactExplainRequest {
  nodeId: string;
  node: ImpactNode;
  neighbors: ImpactNeighbor[];
  verdictSnippet?: string;
}

export interface ImpactExplainResponse {
  headline: string;
  text: string;
  citations: AskCitation[];
}

export type ImpactExplain = ImpactExplainResponse;

// Trace / impact graph (plan: live Trace / impact graph). Client derives the
// graph; POST /impact/explain returns a cited summary of the selected subgraph.
export type ImpactNodeKind = 'item' | 'decision' | 'area' | 'source';
export type ImpactEdgeKind = 'affects' | 'depends-on' | 'contradicts' | 'supersedes' | 'duplicate';

export interface ImpactNodeSnapshot {
  id: string;
  type: ImpactNodeKind;
  label: string;
}

export interface ImpactNeighbor {
  id: string;
  type: ImpactNodeKind;
  label: string;
  edgeType: ImpactEdgeKind;
}

export interface ImpactExplainRequest {
  nodeId: string;
  node: ImpactNodeSnapshot;
  neighbors: ImpactNeighbor[];
  verdictSnippet?: string;
}

export interface ImpactExplainResponse {
  headline: string;
  text: string;
  citations: AskCitation[];
}
