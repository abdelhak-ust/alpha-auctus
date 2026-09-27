import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import { AskResponse, AskTurn, AuthorResponse, AuthorTimeFrame, DBState, Item, Decision, WebSource, MvpDocument, Feature, FeaturePatch, GeneratedTask, ClarificationState, ClarificationAnswerResponse, AgentActivity, ProjectSummary, Agent, AgentKind, NewProjectDraft, ClarificationTurn, ChatMessage, GenerationMode, VerdictDetail } from '../types.js';
import {
  BackendError, DOC_RUNNING, answerClarification as apiAnswer, askAboutItem, askProjectMemory, authorDocument, checkItemVerdict, generateTasks as apiGenerateTasks,
  getClarification, getDocumentMarkdown, getFeatureActivity, getWorkflow, isIngestibleFile, listDocuments,
  listFeatures, patchFeature as apiPatchFeature, patchTask, skipClarification as apiSkip,
  skipRemainingClarification as apiSkipRemaining, uploadDocument as apiUpload,
} from '../lib/backend.js';

type ViewName = 'board' | 'verdicts' | 'runs' | 'reviews' | 'delivery' | 'memory' | 'impact' | 'author' | 'sources' | 'features' | 'chat' | 'deprecate' | 'settings' | 'projects';

// Phases of the guided New Project takeover. 'idle' = normal app. Fake setup chat is skipped.
type SetupPhase = 'idle' | 'setup';

const genModeKey = (projectId: string, kind: 'feature' | 'task') => `nexus-gen-mode-${kind}-${projectId}`;

function readGenMode(projectId: string, kind: 'feature' | 'task'): GenerationMode | null {
  try {
    const v = sessionStorage.getItem(genModeKey(projectId, kind));
    if (v === 'auto' || v === 'review_as_you_go') return v;
  } catch { /* private mode / blocked storage */ }
  return null;
}

function writeGenMode(projectId: string, kind: 'feature' | 'task', mode: GenerationMode) {
  try { sessionStorage.setItem(genModeKey(projectId, kind), mode); } catch { /* ignore */ }
}

function withTaskDefaults(task: GeneratedTask): GeneratedTask {
  return {
    ...task,
    subtasks: task.subtasks ?? [],
    definitionOfDone: task.definitionOfDone ?? [],
    acceptanceCriteria: task.acceptanceCriteria ?? [],
  };
}

function withFeatureDefaults(feature: Feature): Feature {
  return {
    ...feature,
    reviewStatus: feature.reviewStatus ?? 'pending',
    tasks: (feature.tasks ?? []).map(withTaskDefaults),
  };
}

function composeBoardDescription(task: GeneratedTask): string {
  const subtasks = task.subtasks ?? [];
  const criteria = task.acceptanceCriteria ?? [];
  const done = task.definitionOfDone ?? [];
  const lines = [
    task.description?.trim() ?? '',
    '',
    '## Subtasks',
    ...subtasks.map(step => `- [ ] ${step}`),
    '',
    '## Acceptance criteria',
    ...criteria.map(ac => `Given ${ac.given} When ${ac.when} Then ${ac.then}`),
    '',
    '## Definition of done',
    ...done.map(item => `- ${item}`),
  ];
  return lines.join('\n').trim();
}

const emptyDraft = (): NewProjectDraft => ({ name: '', description: '', github: '', sources: [], answers: [] });

interface ProjectContextType {
  state: DBState | null;
  loading: boolean;
  theme: 'light' | 'dark';
  setTheme: (t: 'light' | 'dark') => void;

  // Projects
  projects: ProjectSummary[];
  activeProjectId: string | null;
  activeProject: ProjectSummary | null;
  loadingProjects: boolean;
  justCreatedProjectId: string | null;
  fetchProjects: () => Promise<ProjectSummary[]>;
  createProject: (name: string, opts?: { route?: boolean }) => Promise<ProjectSummary>;
  selectProject: (id: string) => void;
  deleteProject: (id: string) => Promise<void>;
  connectSource: (type: WebSource['type'], name: string) => Promise<void>;

  // Guided New Project flow — create + upload, then land on Chat (no fake Q&A).
  setupPhase: SetupPhase;
  setupDraft: NewProjectDraft;
  startNewProjectSetup: () => void;
  cancelSetup: () => void;
  completeProjectSetup: (draft: NewProjectDraft, files?: File[]) => Promise<void>;
  finishSetupAndGenerate: (answers: ClarificationTurn[]) => Promise<void>;

  // Workspace-wide AI agent catalog
  createAgent: (name: string, kind?: AgentKind) => Promise<Agent>;
  deleteAgent: (id: string) => Promise<void>;

  addItem: (item: Partial<Item>) => Promise<Item>;
  updateItem: (id: number, fields: Partial<Item>) => Promise<Item>;
  deleteItem: (id: number) => Promise<void>;
  resolveVerdict: (id: number, action: 'confirm' | 'dismiss' | 'supersede' | 'merge', targetId?: string) => Promise<void>;
  addDecision: (dec: Partial<Decision>) => Promise<Decision>;
  updateConfig: (cfg: Partial<DBState['apiConfig']>) => Promise<void>;
  askQuestion: (q: string, itemId?: number, history?: AskTurn[]) => Promise<AskResponse>;
  generateDocument: (type: 'brd' | 'spec' | 'tree', area: string, timeFrame: string) => Promise<AuthorResponse>;
  getDeprecations: () => Promise<any[]>;
  uploadDocument: (file: File) => Promise<MvpDocument | null>;
  resolveIngestItem: (id: string, action: 'approve' | 'dismiss') => Promise<void>;
  documents: MvpDocument[];
  features: Feature[];
  clarification: ClarificationState | null;
  workflowHistory: ChatMessage[];
  featureActivity: Record<string, AgentActivity[]>;
  featureMarkdown: Record<string, string>;
  featureGenMode: GenerationMode | null;
  taskGenMode: GenerationMode | null;
  setFeatureGenMode: (mode: GenerationMode) => void;
  setTaskGenMode: (mode: GenerationMode) => void;
  refreshFeatures: () => Promise<void>;
  loadFeatureExtras: (featureId: string, documentId: string) => Promise<void>;
  answerClarification: (questionId: string, answer: string) => Promise<ClarificationAnswerResponse>;
  skipClarification: (questionId: string) => Promise<ClarificationAnswerResponse>;
  skipRemainingQuestions: (featureId: string) => Promise<ClarificationAnswerResponse>;
  updateFeature: (featureId: string, body: FeaturePatch) => Promise<Feature | null>;
  approveFeature: (featureId: string) => Promise<void>;
  rejectFeature: (featureId: string) => Promise<void>;
  generateFeatureTasks: (featureId: string) => Promise<void>;
  generateApprovedFeatureTasks: () => Promise<void>;
  approveTask: (taskId: string) => Promise<void>;
  approveAllDraftTasks: (featureId?: string) => Promise<void>;
  addTaskToBoard: (taskId: string) => Promise<void>;
  addAllApprovedToBoard: () => Promise<void>;
  selectedCardId: number | null;
  setSelectedCardId: (id: number | null) => void;
  activeView: ViewName;
  setActiveView: (view: ViewName) => void;
  refreshState: () => Promise<void>;
  triggerToast: (msg: string, undoAction?: () => void) => void;
  toast: { message: string; visible: boolean; undo?: () => void } | null;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export const ProjectProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<DBState | null>(null);
  const [loading, setLoading] = useState(true);
  const [theme, setThemeState] = useState<'light' | 'dark'>('light');
  const [selectedCardId, setSelectedCardId] = useState<number | null>(null);
  const [activeView, setActiveView] = useState<ViewName>('board');
  const [toast, setToast] = useState<{ message: string; visible: boolean; undo?: () => void } | null>(null);

  // Projects
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [justCreatedProjectId, setJustCreatedProjectId] = useState<string | null>(null);

  // Guided New Project takeover state
  const [setupPhase, setSetupPhase] = useState<SetupPhase>('idle');
  const [setupDraft, setSetupDraft] = useState<NewProjectDraft>(emptyDraft());
  // The File objects behind setupDraft.sources (DraftSource only carries metadata).
  const setupFilesRef = useRef<File[]>([]);

  const [documents, setDocuments] = useState<MvpDocument[]>([]);
  const [features, setFeatures] = useState<Feature[]>([]);
  const [clarification, setClarification] = useState<ClarificationState | null>(null);
  const [workflowHistory, setWorkflowHistory] = useState<ChatMessage[]>([]);
  const [featureActivity, setFeatureActivity] = useState<Record<string, AgentActivity[]>>({});
  const [featureMarkdown, setFeatureMarkdown] = useState<Record<string, string>>({});
  const [featureGenMode, setFeatureGenModeState] = useState<GenerationMode | null>(null);
  const [taskGenMode, setTaskGenModeState] = useState<GenerationMode | null>(null);

  const triggerToast = (msg: string, undoAction?: () => void) => {
    setToast({ message: msg, visible: true, undo: undoAction });
    setTimeout(() => {
      setToast(prev => prev && prev.message === msg ? { ...prev, visible: false } : prev);
    }, 6000);
  };

  const showBackendError = (e: unknown, fallbackProblem: string) => {
    if (e instanceof BackendError) {
      triggerToast(e.toDisplay());
    } else {
      console.error(fallbackProblem, e);
      triggerToast(`${fallbackProblem} (unexpected client error). Retry, or check the browser console.`);
    }
  };

  const setTheme = (t: 'light' | 'dark') => {
    setThemeState(t);
    try {
      localStorage.setItem('dm-theme', t);
    } catch (e) {}
    const root = window.document.documentElement;
    if (t === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  };

  const refreshState = async () => {
    if (!activeProjectId) {
      setState(null);
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(`/api/state?projectId=${activeProjectId}`);
      const data = await res.json();
      setState(data);
    } catch (e) {
      console.error("Could not sync project state", e);
    } finally {
      setLoading(false);
    }
  };

  const fetchProjects = async (): Promise<ProjectSummary[]> => {
    setLoadingProjects(true);
    try {
      const res = await fetch('/api/projects');
      const data: ProjectSummary[] = await res.json();
      setProjects(data);
      return data;
    } catch (e) {
      console.error("Could not load projects", e);
      return [];
    } finally {
      setLoadingProjects(false);
    }
  };

  const selectProject = (id: string) => {
    setActiveProjectId(id);
    try { localStorage.setItem('nexus-active-project', id); } catch (e) {}
    setSelectedCardId(null);
    setActiveView('board');
  };

  const createProject = async (name: string, opts?: { route?: boolean }): Promise<ProjectSummary> => {
    const res = await fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    const proj: ProjectSummary = await res.json();
    await fetchProjects();
    setActiveProjectId(proj.id);
    try { localStorage.setItem('nexus-active-project', proj.id); } catch (e) {}
    setSelectedCardId(null);
    setJustCreatedProjectId(proj.id);
    // The guided setup flow controls its own routing/toast (route:false); the
    // legacy inline path defaults to landing on the sources setup step.
    if (opts?.route !== false) {
      setActiveView('sources');
      triggerToast(`Created project "${proj.name}". Start by connecting your sources.`);
    }
    return proj;
  };

  // ── Guided New Project flow (§4.10–4.11) ──────────────────────────────────
  const startNewProjectSetup = () => {
    setSetupDraft(emptyDraft());
    setSetupPhase('setup');
  };

  const cancelSetup = () => {
    setSetupPhase('idle');
    setSetupDraft(emptyDraft());
    setupFilesRef.current = [];
    // If there's no project to fall back to, keep the user on the projects list.
    if (!activeProjectId) setActiveView('projects');
  };

  const finishSetupAndGenerate = async (answers: ClarificationTurn[], draftOverride?: NewProjectDraft) => {
    const draft: NewProjectDraft = { ...(draftOverride || setupDraft), answers };

    // 1. Create the project (setup flow owns navigation, so route:false).
    const proj = await createProject(draft.name.trim() || 'Untitled project', { route: false });

    // 2. Assemble the setup brief (description, GitHub URL, media names) as a
    //    Markdown document so it enters the same ingestion pipeline as every
    //    other file. Video/image are listed by name only (transcription/OCR is out of v1).
    const media = draft.sources.filter(s => s.kind !== 'file').map(s => `- ${s.kind}: ${s.name}`);
    const qa = draft.answers.map(t => `Q: ${t.question}\nA: ${t.answer}`);
    const brief = [
      `# ${draft.name}`,
      `\n## Description\n${draft.description}`,
      draft.github ? `\n## GitHub\n${draft.github} (analysis deferred)` : '',
      media.length ? `\n## Media sources (not yet ingested)\n${media.join('\n')}` : '',
      qa.length ? `\n## Clarifications\n${qa.join('\n\n')}` : ''
    ].filter(Boolean).join('\n');
    const briefFile = new File([brief], `${(draft.name.trim() || 'Untitled project').replace(/[\\/:*?"<>|]+/g, '-')} — setup brief.md`, { type: 'text/markdown' });

    // 3. Land on Chat with ingest already running. Fake clarification Q&A is skipped.
    const docs = setupFilesRef.current.filter(f => isIngestibleFile(f.name));
    setupFilesRef.current = [];
    setSetupPhase('idle');
    setSetupDraft(emptyDraft());
    await refreshState();
    await fetchProjects();
    setActiveView('chat');
    triggerToast(`Created "${proj.name}". I'm reading your sources in Chat.`);

    // 4. Upload the brief + the project documents to backend/ through the same
    //    path as the Sources view; each one's outcome is toasted as it lands.
    void (async () => {
      for (const file of [briefFile, ...docs]) {
        await ingestFile(proj.id, file);
      }
    })();
  };

  const completeProjectSetup = async (draft: NewProjectDraft, files: File[] = []) => {
    setupFilesRef.current = files;
    setSetupDraft(draft);
    await finishSetupAndGenerate(draft.answers || [], draft);
  };

  const deleteProject = async (id: string): Promise<void> => {
    await fetch(`/api/projects/${id}`, { method: 'DELETE' });
    const list = await fetchProjects();
    if (activeProjectId === id) {
      if (list.length > 0) {
        selectProject(list[0].id);
      } else {
        setActiveProjectId(null);
        try { localStorage.removeItem('nexus-active-project'); } catch (e) {}
        setState(null);
        setActiveView('projects');
      }
    }
    triggerToast('Project deleted.');
  };

  const connectSource = async (type: WebSource['type'], name: string): Promise<void> => {
    if (!activeProjectId) return;
    await fetch('/api/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projectId: activeProjectId, type, name })
    });
    await refreshState();
    await fetchProjects();
    setJustCreatedProjectId(null);
    triggerToast(`Connected ${name}.`);
  };

  const createAgent = async (name: string, kind: AgentKind = 'custom'): Promise<Agent> => {
    const res = await fetch('/api/agents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, kind })
    });
    const agent: Agent = await res.json();
    setState(prev => prev ? { ...prev, agents: [...prev.agents, agent] } : prev);
    triggerToast(`Added agent "${agent.name}".`);
    return agent;
  };

  const deleteAgent = async (id: string): Promise<void> => {
    await fetch(`/api/agents/${id}`, { method: 'DELETE' });
    setState(prev => prev ? { ...prev, agents: prev.agents.filter(a => a.id !== id) } : prev);
    triggerToast('Agent removed.');
  };

  // Boot: theme + project list, then pick an active project.
  useEffect(() => {
    // Light is the default; only an explicit saved choice flips to dark.
    let resolvedTheme: 'light' | 'dark' = 'light';
    try {
      const saved = localStorage.getItem('dm-theme');
      if (saved === 'light' || saved === 'dark') {
        resolvedTheme = saved;
      }
    } catch (e) {}
    setTheme(resolvedTheme);

    (async () => {
      const list = await fetchProjects();
      let saved: string | null = null;
      try { saved = localStorage.getItem('nexus-active-project'); } catch (e) {}
      if (saved && list.find(p => p.id === saved)) {
        setActiveProjectId(saved);
      } else if (list.length > 0) {
        setActiveProjectId(list[0].id);
      } else {
        // First run, no projects yet → drop straight into guided New Project setup.
        setActiveView('projects');
        setSetupPhase('setup');
        setLoading(false);
      }
    })();
  }, []);

  // Poll the active project's state (catches background verdict completions).
  useEffect(() => {
    if (!activeProjectId) {
      setState(null);
      return;
    }
    setLoading(true);
    refreshState();
    const timer = setInterval(refreshState, 4000);
    return () => clearInterval(timer);
  }, [activeProjectId]);

  const quietNetNew = (): VerdictDetail => ({
    type: 'net-new',
    confidence: 100,
    message: 'Net-new — nothing like this yet',
    candidates: [],
  });

  const otherBoardItems = (excludeId: number) =>
    (state?.items ?? [])
      .filter(i => i.id !== excludeId)
      .map(i => ({
        id: i.id,
        title: i.title,
        description: i.description,
        area: i.area,
        status: i.status,
      }));

  const saveItem = async (id: number, fields: Partial<Item>): Promise<Item> => {
    let oldItem: Item | undefined;
    setState(prev => {
      if (!prev) return null;
      oldItem = prev.items.find(i => i.id === id);
      return {
        ...prev,
        items: prev.items.map(i => i.id === id ? { ...i, ...fields } : i),
      };
    });

    try {
      const res = await fetch(`/api/items/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...fields, projectId: activeProjectId }),
      });
      const updated = await res.json();
      setState(prev => {
        if (!prev) return null;
        return { ...prev, items: prev.items.map(i => i.id === id ? updated : i) };
      });
      return updated;
    } catch (e) {
      if (oldItem) {
        setState(prev => {
          if (!prev) return null;
          return { ...prev, items: prev.items.map(i => i.id === id ? oldItem! : i) };
        });
      }
      throw e;
    }
  };

  const applyVerdictCheck = async (item: Item): Promise<Item> => {
    if (!activeProjectId) return item;
    let verdict: VerdictDetail;
    try {
      verdict = await checkItemVerdict(
        activeProjectId,
        { id: item.id, title: item.title, description: item.description, area: item.area },
        otherBoardItems(item.id),
      );
    } catch (e) {
      showBackendError(e, "Couldn't check this card against the board");
      verdict = quietNetNew();
    }
    return saveItem(item.id, { verdict });
  };

  const addItem = async (itemFields: Partial<Item>): Promise<Item> => {
    // Optimistic UI insert to make it "spreadsheet-fast"
    const tempId = Date.now();
    const tempItem: Item = {
      id: tempId,
      title: itemFields.title || "Untitled",
      description: itemFields.description || "",
      status: itemFields.status || "inbox",
      priority: itemFields.priority || "P2",
      assignee: itemFields.assignee || "AM",
      area: itemFields.area || "general",
      created_at: new Date().toISOString(),
      source: null,
      verdict: {
        type: 'checking',
        confidence: 100,
        message: 'Checking backlog and Decisions in memory...',
        candidates: []
      }
    };

    if (state) {
      setState({
        ...state,
        items: [...state.items, tempItem]
      });
    }

    try {
      const res = await fetch('/api/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...itemFields, projectId: activeProjectId })
      });
      const realItem = await res.json();
      // Replace optimistic placeholder with real result
      setState(prev => {
        if (!prev) return null;
        return {
          ...prev,
          items: prev.items.map(i => i.id === tempId ? realItem : i)
        };
      });
      triggerToast(`Added card "${realItem.title.slice(0, 20)}..."`);
      try {
        await applyVerdictCheck(realItem);
      } catch (e) {
        showBackendError(e, "Couldn't save the verdict");
      }
      return realItem;
    } catch (e) {
      // Revert optimistic insert
      refreshState();
      throw e;
    }
  };

  const updateItem = async (id: number, fields: Partial<Item>): Promise<Item> => {
    const current = state?.items.find(i => i.id === id);
    const titleChanged = fields.title !== undefined && fields.title !== current?.title;
    const descriptionChanged = fields.description !== undefined && fields.description !== current?.description;
    const needsRecheck = titleChanged || descriptionChanged;
    const payload = needsRecheck
      ? {
          ...fields,
          verdict: {
            type: 'checking' as const,
            confidence: 100,
            message: 'Re-checking decisions...',
            candidates: [],
          },
        }
      : fields;

    const updated = await saveItem(id, payload);
    if (!needsRecheck) return updated;
    try {
      return await applyVerdictCheck(updated);
    } catch (e) {
      showBackendError(e, "Couldn't save the verdict");
      return updated;
    }
  };

  const deleteItem = async (id: number): Promise<void> => {
    let deleted: Item | undefined;
    if (state) {
      deleted = state.items.find(i => i.id === id);
      setState({
        ...state,
        items: state.items.filter(i => i.id !== id)
      });
    }

    try {
      await fetch(`/api/items/${id}?projectId=${activeProjectId}`, { method: 'DELETE' });
      triggerToast(`Archived Card #${id}.`, () => {
        // Undo function: re-insert deleted card
        if (deleted) {
          addItem(deleted);
        }
      });
    } catch (e) {
      refreshState();
      throw e;
    }
  };

  const resolveVerdict = async (id: number, action: 'confirm' | 'dismiss' | 'supersede' | 'merge', targetId?: string): Promise<void> => {
    try {
      const res = await fetch(`/api/items/${id}/verdict/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, targetId, projectId: activeProjectId })
      });
      await res.json();
      await refreshState();
      triggerToast(`Verdict resolved: ${action}`);
    } catch (e) {
      console.error(e);
    }
  };

  const addDecision = async (decFields: Partial<Decision>): Promise<Decision> => {
    try {
      const res = await fetch('/api/decisions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...decFields, projectId: activeProjectId })
      });
      const created = await res.json();
      await refreshState();
      triggerToast(`Created Decision #${created.id}`);
      return created;
    } catch (e) {
      refreshState();
      throw e;
    }
  };

  const updateConfig = async (cfg: Partial<DBState['apiConfig']>) => {
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg)
      });
      const data = await res.json();
      if (data.success && state) {
        setState({ ...state, apiConfig: data.apiConfig });
      }
      triggerToast("Config applied.");
    } catch (e) {
      console.error(e);
    }
  };

  const askQuestion = async (q: string, itemId?: number, history: AskTurn[] = []): Promise<AskResponse> => {
    if (!activeProjectId) {
      throw new BackendError('No project', 'none selected', 'Open a project', 0);
    }
    if (itemId != null) {
      const item = state?.items.find(i => i.id === itemId);
      return askAboutItem(activeProjectId, {
        query: q,
        boardItemId: itemId,
        item: {
          title: item?.title ?? '',
          description: item?.description ?? '',
          area: item?.area ?? '',
          priority: item?.priority ?? 'P2',
        },
        history,
      });
    }
    return askProjectMemory(activeProjectId, {
      query: q,
      history,
      boardItems: (state?.items ?? []).map(i => ({
        id: i.id,
        title: i.title,
        description: i.description,
        area: i.area,
        status: i.status,
      })),
    });
  };

  const generateDocument = async (type: 'brd' | 'spec' | 'tree', area: string, timeFrame: string) => {
    if (!activeProjectId) {
      throw new BackendError('No project', 'none selected', 'Open a project', 0);
    }
    return authorDocument(activeProjectId, {
      type,
      area,
      timeFrame: timeFrame as AuthorTimeFrame,
      boardItems: (state?.items ?? []).map(i => ({
        id: i.id,
        title: i.title,
        description: i.description,
        area: i.area,
        status: i.status,
        createdAt: i.created_at,
        ...(i.verdict?.type ? { verdictType: i.verdict.type } : {}),
      })),
      decisions: (state?.decisions ?? []).map(d => ({
        id: d.id,
        title: d.title,
        description: d.description,
        area: d.area,
      })),
    });
  };

  const getDeprecations = async () => {
    const res = await fetch('/api/deprecate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projectId: activeProjectId })
    });
    const data = await res.json();
    return data.suggestions;
  };

  const refreshMvp = async (projectId: string) => {
    try {
      const [docs, feats] = await Promise.all([listDocuments(projectId), listFeatures(projectId)]);
      setDocuments(docs);
      setFeatures(feats.map(withFeatureDefaults));
      return docs;
    } catch (e) {
      if (e instanceof BackendError && e.status === 0) return [];
      throw e;
    }
  };

  const refreshFeatures = async () => {
    if (!activeProjectId) return;
    try {
      const [feats, clar, wf] = await Promise.all([
        listFeatures(activeProjectId),
        getClarification(activeProjectId).catch(() => null),
        getWorkflow(activeProjectId).catch(() => null),
      ]);
      setFeatures(feats.map(withFeatureDefaults));
      if (clar) setClarification(clar);
      if (wf) setWorkflowHistory(wf.history);
      else if (clar) setWorkflowHistory(clar.history);
    } catch (e) {
      showBackendError(e, "Couldn't load features");
    }
  };

  const setFeatureGenMode = (mode: GenerationMode) => {
    setFeatureGenModeState(mode);
    if (activeProjectId) writeGenMode(activeProjectId, 'feature', mode);
  };

  const setTaskGenMode = (mode: GenerationMode) => {
    setTaskGenModeState(mode);
    if (activeProjectId) writeGenMode(activeProjectId, 'task', mode);
  };

  const loadFeatureExtras = async (featureId: string, documentId: string) => {
    if (!activeProjectId) return;
    try {
      const [activity, md] = await Promise.all([
        getFeatureActivity(activeProjectId, featureId),
        featureMarkdown[documentId]
          ? Promise.resolve(null)
          : getDocumentMarkdown(activeProjectId, documentId).catch(() => null),
      ]);
      setFeatureActivity(prev => ({ ...prev, [featureId]: activity }));
      if (md) setFeatureMarkdown(prev => ({ ...prev, [documentId]: md.markdown }));
    } catch { /* extras are optional for the card */ }
  };

  const ingestFile = async (projectId: string, file: File, opts: { throwOnError?: boolean } = {}): Promise<MvpDocument | null> => {
    if (!isIngestibleFile(file.name)) {
      const err = new BackendError(`Can't ingest ${file.name}`, 'unsupported file type', 'Upload a PDF, DOCX or Markdown file', 415);
      if (opts.throwOnError) throw err;
      triggerToast(err.toDisplay());
      return null;
    }
    let doc: MvpDocument;
    try {
      doc = await apiUpload(projectId, file);
    } catch (e) {
      if (opts.throwOnError) throw e;
      showBackendError(e, `Couldn't upload ${file.name}`);
      return null;
    }
    if (doc.status === 'failed') {
      triggerToast(`Couldn't extract ${doc.filename} (${(doc.error || 'no cause').trim()}). Fix and retry.`);
      await refreshMvp(projectId);
      return doc;
    }
    if (doc.duplicate && doc.status === 'ready') {
      triggerToast(`${doc.filename} was already extracted — nothing new.`);
      await refreshMvp(projectId);
      return doc;
    }
    triggerToast(doc.duplicate ? `${doc.filename} is already processing…` : `Uploaded ${doc.filename} — extracting…`);
    await refreshMvp(projectId);
    return doc;
  };

  const uploadDocument = async (file: File): Promise<MvpDocument | null> => {
    if (!activeProjectId) return null;
    return ingestFile(activeProjectId, file, { throwOnError: true });
  };

  const resolveIngestItem = async (id: string, action: 'approve' | 'dismiss') => {
    await fetch('/api/ingest/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, action, projectId: activeProjectId })
    });
    await refreshState();
    triggerToast(action === 'approve' ? `Approved and moved to Board inbox.` : `Dismissed ingestion item.`);
  };

  const answerClarificationFn = async (questionId: string, answer: string) => {
    if (!activeProjectId) throw new BackendError('No project', 'none selected', 'Open a project', 0);
    const res = await apiAnswer(activeProjectId, questionId, answer);
    await refreshFeatures();
    return res;
  };

  const skipClarificationFn = async (questionId: string) => {
    if (!activeProjectId) throw new BackendError('No project', 'none selected', 'Open a project', 0);
    const res = await apiSkip(activeProjectId, questionId);
    await refreshFeatures();
    return res;
  };

  const skipRemainingFn = async (featureId: string) => {
    if (!activeProjectId) throw new BackendError('No project', 'none selected', 'Open a project', 0);
    const res = await apiSkipRemaining(activeProjectId, featureId);
    await refreshFeatures();
    return res;
  };

  const updateFeature = async (featureId: string, body: FeaturePatch): Promise<Feature | null> => {
    if (!activeProjectId) return null;
    try {
      const updated = await apiPatchFeature(activeProjectId, featureId, body);
      await refreshFeatures();
      return updated;
    } catch (e) {
      if (e instanceof BackendError && e.status === 409) {
        triggerToast('Approve is blocked until every open question is answered or skipped.');
      } else {
        showBackendError(e, "Couldn't update the feature");
      }
      throw e;
    }
  };

  const approveFeature = async (featureId: string) => {
    await updateFeature(featureId, { reviewStatus: 'approved' });
    const name = features.find(f => f.id === featureId)?.name || 'feature';
    triggerToast(`Approved “${name}”.`);
  };

  const rejectFeature = async (featureId: string) => {
    await updateFeature(featureId, { reviewStatus: 'rejected' });
    const name = features.find(f => f.id === featureId)?.name || 'feature';
    triggerToast(`Rejected “${name}” — it won't get tasks.`);
  };

  const generateFeatureTasks = async (featureId: string) => {
    if (!activeProjectId) return;
    await apiGenerateTasks(activeProjectId, featureId);
    triggerToast('Generating tasks…');
    await refreshFeatures();
  };

  const generateApprovedFeatureTasks = async () => {
    if (!activeProjectId) return;
    const ready = features.filter(f =>
      (f.reviewStatus ?? 'pending') === 'approved' && f.tasks.length === 0 && f.status !== 'planning'
    );
    for (const f of ready) {
      await apiGenerateTasks(activeProjectId, f.id);
    }
    if (ready.length) {
      triggerToast(`Generating tasks for ${ready.length} feature${ready.length === 1 ? '' : 's'}…`);
      await refreshFeatures();
    }
  };

  const approveTask = async (taskId: string) => {
    if (!activeProjectId) return;
    await patchTask(activeProjectId, taskId, { status: 'approved' });
    await refreshFeatures();
  };

  const approveAllDraftTasks = async (featureId?: string) => {
    if (!activeProjectId) return;
    const drafts = features
      .filter(f => !featureId || f.id === featureId)
      .flatMap(f => f.tasks.filter(t => t.status === 'draft'));
    for (const t of drafts) {
      await patchTask(activeProjectId, t.id, { status: 'approved' });
    }
    await refreshFeatures();
    if (drafts.length) triggerToast(`Approved ${drafts.length} task${drafts.length === 1 ? '' : 's'}.`);
  };

  const publishTask = async (projectId: string, task: GeneratedTask, feature: Feature) => {
    const item = await addItem({
      title: task.title,
      description: composeBoardDescription(task),
      priority: task.priority,
      area: task.area,
      status: 'inbox',
      source: { type: 'upload', name: documents.find(d => d.id === feature.documentId)?.filename || 'document', snippet: feature.name },
    });
    await patchTask(projectId, task.id, { status: 'on_board', boardItemId: item.id });
  };

  const addTaskToBoard = async (taskId: string) => {
    if (!activeProjectId) return;
    const feature = features.find(f => f.tasks.some(t => t.id === taskId));
    const task = feature?.tasks.find(t => t.id === taskId);
    if (!feature || !task) return;
    await publishTask(activeProjectId, task, feature);
    await refreshFeatures();
    triggerToast(`Added “${task.title}” to the board.`);
  };

  const addAllApprovedToBoard = async () => {
    if (!activeProjectId) return;
    const approved = features.flatMap(f => f.tasks.filter(t => t.status === 'approved').map(t => ({ t, f })));
    for (const { t, f } of approved) {
      await publishTask(activeProjectId, t, f);
    }
    await refreshFeatures();
    triggerToast(approved.length ? `Added ${approved.length} card${approved.length === 1 ? '' : 's'} to the board.` : 'No approved tasks to add.');
  };

  // Poll documents/features only while something is running.
  useEffect(() => {
    setDocuments([]);
    setFeatures([]);
    setClarification(null);
    setWorkflowHistory([]);
    setFeatureActivity({});
    setFeatureMarkdown({});
    if (!activeProjectId) {
      setFeatureGenModeState(null);
      setTaskGenModeState(null);
      return;
    }
    setFeatureGenModeState(readGenMode(activeProjectId, 'feature'));
    setTaskGenModeState(readGenMode(activeProjectId, 'task'));
    let cancelled = false;
    const tick = async () => {
      try {
        const docs = await refreshMvp(activeProjectId);
        const running = docs.some(d => DOC_RUNNING.has(d.status)) || features.some(f => f.status === 'planning');
        if (!cancelled && running) timer = setTimeout(tick, 2000);
      } catch { /* backend down — don't loop hard */ }
    };
    let timer: ReturnType<typeof setTimeout>;
    void tick();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [activeProjectId]);

  useEffect(() => {
    if (!activeProjectId) return;
    const running = documents.some(d => DOC_RUNNING.has(d.status)) || features.some(f => f.status === 'planning');
    if (!running) return;
    const timer = setTimeout(() => { void refreshMvp(activeProjectId); }, 2000);
    return () => clearTimeout(timer);
  }, [activeProjectId, documents, features]);

  const mergedState: DBState | null = state;

  const activeProject = projects.find(p => p.id === activeProjectId) || null;

  return (
    <ProjectContext.Provider value={{
      state: mergedState,
      loading,
      theme,
      setTheme,
      projects,
      activeProjectId,
      activeProject,
      loadingProjects,
      justCreatedProjectId,
      fetchProjects,
      createProject,
      selectProject,
      deleteProject,
      connectSource,
      setupPhase,
      setupDraft,
      startNewProjectSetup,
      cancelSetup,
      completeProjectSetup,
      finishSetupAndGenerate,
      createAgent,
      deleteAgent,
      addItem,
      updateItem,
      deleteItem,
      resolveVerdict,
      addDecision,
      updateConfig,
      askQuestion,
      generateDocument,
      getDeprecations,
      uploadDocument,
      resolveIngestItem,
      documents,
      features,
      clarification,
      workflowHistory,
      featureActivity,
      featureMarkdown,
      featureGenMode,
      taskGenMode,
      setFeatureGenMode,
      setTaskGenMode,
      refreshFeatures,
      loadFeatureExtras,
      answerClarification: answerClarificationFn,
      skipClarification: skipClarificationFn,
      skipRemainingQuestions: skipRemainingFn,
      updateFeature,
      approveFeature,
      rejectFeature,
      generateFeatureTasks,
      generateApprovedFeatureTasks,
      approveTask,
      approveAllDraftTasks,
      addTaskToBoard,
      addAllApprovedToBoard,
      selectedCardId,
      setSelectedCardId,
      activeView,
      setActiveView,
      refreshState,
      triggerToast,
      toast
    }}>
      {children}
    </ProjectContext.Provider>
  );
};

export const useProject = () => {
  const context = useContext(ProjectContext);
  if (!context) {
    throw new Error("useProject must be used inside ProjectProvider");
  }
  return context;
};
