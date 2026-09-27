import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import { DBState, Item, Decision, VerdictType, WebSource, IngestItem, IngestDocument, ProjectSummary, Priority, Status, Agent, AgentKind, NewProjectDraft, DraftSource, ClarificationTurn } from '../types.js';
import { BackendError, getReviewQueue, isIngestibleFile, resolveReviewItem, uploadIngestDocument, waitForIngestDocument } from '../lib/backend.js';

type ViewName = 'board' | 'verdicts' | 'runs' | 'reviews' | 'delivery' | 'memory' | 'impact' | 'author' | 'sources' | 'deprecate' | 'settings' | 'projects';

// Phases of the guided New Project takeover (§4.10 → §4.11). 'idle' = normal app.
type SetupPhase = 'idle' | 'setup' | 'chat';

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

  // Guided New Project flow (§4.10–4.11)
  setupPhase: SetupPhase;
  setupDraft: NewProjectDraft;
  startNewProjectSetup: () => void;
  cancelSetup: () => void;
  beginClarification: (draft: NewProjectDraft, files?: File[]) => void;
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
  askQuestion: (q: string, activeItemId?: number) => Promise<{ answer: string; citations: any[] }>;
  generateDocument: (type: 'brd' | 'spec' | 'tree', area: string, timeFrame: string) => Promise<{ document: string; unresolvedConflictsCount: number; conflicts: any[] }>;
  getDeprecations: () => Promise<any[]>;
  /**
   * Sends a real file to backend/ (POST /projects/{id}/documents), then polls its
   * status in the background and toasts the outcome. Throws BackendError if the
   * upload itself fails, so the caller can show problem + cause + fix inline.
   */
  uploadDocument: (file: File) => Promise<IngestDocument | null>;
  resolveIngestItem: (id: string, action: 'approve' | 'dismiss') => Promise<void>;
  /** True when an ingest-queue item came from backend/'s review queue (not the Node store). */
  isBackendIngestItem: (id: string) => boolean;
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

  // Ingestion review queue served by backend/ (plans/ingestion.md §11.1). Merged
  // into state.ingestQueue below so the existing review UI renders both sources.
  const [backendQueue, setBackendQueue] = useState<IngestItem[]>([]);
  const backendQueueIds = useRef<Set<string>>(new Set());
  const backendDownNotified = useRef(false);
  const activeViewRef = useRef<ViewName>('board');
  activeViewRef.current = activeView;

  const triggerToast = (msg: string, undoAction?: () => void) => {
    setToast({ message: msg, visible: true, undo: undoAction });
    setTimeout(() => {
      setToast(prev => prev && prev.message === msg ? { ...prev, visible: false } : prev);
    }, 6000);
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

  const beginClarification = (draft: NewProjectDraft, files: File[] = []) => {
    setupFilesRef.current = files;
    setSetupDraft(draft);
    setSetupPhase('chat');
  };

  const finishSetupAndGenerate = async (answers: ClarificationTurn[]) => {
    const draft: NewProjectDraft = { ...setupDraft, answers };

    // 1. Create the project (setup flow owns navigation, so route:false).
    const proj = await createProject(draft.name.trim() || 'Untitled project', { route: false });

    // 2. Assemble the setup brief (description, GitHub URL, media names, chat
    //    answers) as a Markdown document so it enters the same ingestion
    //    pipeline as every other file. Video/image are listed by name only
    //    (transcription/OCR is out of v1).
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

    // 3. Land in the review queue (Sources view). Uploads continue in the
    //    background (§4.10) — the user doesn't wait on them.
    const docs = setupFilesRef.current.filter(f => isIngestibleFile(f.name));
    setupFilesRef.current = [];
    setSetupPhase('idle');
    setSetupDraft(emptyDraft());
    await refreshState();
    await fetchProjects();
    setActiveView('sources');
    triggerToast(`Created "${proj.name}". Sources are ingesting — extracted features land in the review queue.`);

    // 4. Upload the brief + the project documents to backend/ through the same
    //    path as the Sources view; each one's outcome is toasted as it lands.
    void (async () => {
      for (const file of [briefFile, ...docs]) {
        await ingestFile(proj.id, file);
      }
    })();
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
      return realItem;
    } catch (e) {
      // Revert optimistic insert
      refreshState();
      throw e;
    }
  };

  const updateItem = async (id: number, fields: Partial<Item>): Promise<Item> => {
    let oldItem: Item | undefined;
    if (state) {
      oldItem = state.items.find(i => i.id === id);
      setState({
        ...state,
        items: state.items.map(i => i.id === id ? { ...i, ...fields } : i)
      });
    }

    try {
      const res = await fetch(`/api/items/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...fields, projectId: activeProjectId })
      });
      const updated = await res.json();
      setState(prev => {
        if (!prev) return null;
        return {
          ...prev,
          items: prev.items.map(i => i.id === id ? updated : i)
        };
      });
      return updated;
    } catch (e) {
      // Revert
      if (oldItem && state) {
        setState({
          ...state,
          items: state.items.map(i => i.id === id ? oldItem! : i)
        });
      }
      throw e;
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

  const askQuestion = async (q: string, activeItemId?: number) => {
    const res = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q, activeItemId, projectId: activeProjectId })
    });
    return await res.json();
  };

  const generateDocument = async (type: 'brd' | 'spec' | 'tree', area: string, timeFrame: string) => {
    const res = await fetch('/api/author', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, area, timeFrame, projectId: activeProjectId })
    });
    return await res.json();
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

  // ── Ingestion (backend/, plans/ingestion.md §11.1) ───────────────────────
  const showBackendError = (e: unknown, fallbackProblem: string) => {
    if (e instanceof BackendError) {
      triggerToast(e.toDisplay());
    } else {
      console.error(fallbackProblem, e);
      triggerToast(`${fallbackProblem} (unexpected client error). Retry, or check the browser console.`);
    }
  };

  const fetchBackendQueue = async (projectId: string): Promise<boolean> => {
    try {
      const items = await getReviewQueue(projectId);
      backendQueueIds.current = new Set(items.map(i => String(i.id)));
      setBackendQueue(items);
      backendDownNotified.current = false;
      return true;
    } catch (e) {
      // Don't claim "all processed" for a queue we couldn't read: say so once,
      // where the queue is shown, instead of silently rendering it empty.
      if (!backendDownNotified.current && activeViewRef.current === 'sources') {
        backendDownNotified.current = true;
        if (e instanceof BackendError) {
          triggerToast(`Ingestion review queue unavailable: ${e.toDisplay()}`);
        }
      }
      return false;
    }
  };

  const causeOf = (d: IngestDocument) => (d.error || 'no cause reported by the backend').trim().replace(/[.\s]+$/, '');

  /** Upload one file, then poll it to done/failed in the background and toast the outcome. */
  const ingestFile = async (projectId: string, file: File, opts: { throwOnError?: boolean } = {}): Promise<IngestDocument | null> => {
    if (!isIngestibleFile(file.name)) {
      const err = new BackendError(`Can't ingest ${file.name}`, 'unsupported file type', 'Upload a PDF, DOCX, Markdown or TXT file', 415);
      if (opts.throwOnError) throw err;
      triggerToast(err.toDisplay());
      return null;
    }
    let doc: IngestDocument;
    try {
      doc = await uploadIngestDocument(projectId, file);
    } catch (e) {
      if (opts.throwOnError) throw e;
      showBackendError(e, `Couldn't upload ${file.name}`);
      return null;
    }

    // Branch on status first (plans/ingestion.md §11.3 retry semantics): a re-upload
    // of a failed doc is reset to pending (202) and must be followed, not called a duplicate.
    if (doc.status === 'failed') {
      triggerToast(`Couldn't ingest ${doc.filename} (${causeOf(doc)}). Fix the cause and upload it again.`);
      return doc;
    }
    if (doc.duplicate && (doc.status === 'done' || doc.status === 'consolidated')) {
      triggerToast(`${doc.filename} was already ingested — nothing new to extract.`);
      return doc;
    }
    triggerToast(doc.duplicate
      ? `${doc.filename} is already being ingested — following its progress…`
      : `Uploaded ${doc.filename} — ingesting…`);

    // Background: follow the document to a terminal status.
    void waitForIngestDocument(projectId, doc.id)
      .then(final => {
        if (final.status === 'done') {
          triggerToast(`Ingested ${final.filename} — ${final.featureCount} feature${final.featureCount === 1 ? '' : 's'} extracted.`);
        } else {
          triggerToast(`Couldn't ingest ${final.filename} (${causeOf(final)}). Fix the cause and upload it again.`);
        }
        fetchBackendQueue(projectId);
      })
      .catch(e => showBackendError(e, `Lost track of ${doc.filename}`));

    return doc;
  };

  const uploadDocument = async (file: File): Promise<IngestDocument | null> => {
    if (!activeProjectId) return null;
    return ingestFile(activeProjectId, file, { throwOnError: true });
  };

  const resolveIngestItem = async (id: string, action: 'approve' | 'dismiss') => {
    if (activeProjectId && backendQueueIds.current.has(id)) {
      try {
        await resolveReviewItem(activeProjectId, id, action);
      } catch (e) {
        showBackendError(e, `Couldn't ${action} the review item`);
        return;
      }
      backendQueueIds.current.delete(id);
      setBackendQueue(prev => prev.filter(i => String(i.id) !== id));
      await fetchBackendQueue(activeProjectId);
      triggerToast(action === 'approve' ? 'Approved ingestion item.' : 'Dismissed ingestion item.');
      return;
    }

    // Legacy items still produced by client/server.ts.
    await fetch('/api/ingest/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, action, projectId: activeProjectId })
    });
    await refreshState();
    triggerToast(action === 'approve' ? `Approved and moved to Board inbox.` : `Dismissed ingestion item.`);
  };

  // Poll the backend review queue alongside the Node state; back off while the
  // backend is unreachable so a stopped backend doesn't flood the console.
  useEffect(() => {
    backendQueueIds.current = new Set();
    setBackendQueue([]);
    backendDownNotified.current = false;
    if (!activeProjectId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      const ok = await fetchBackendQueue(activeProjectId);
      if (!cancelled) timer = setTimeout(tick, ok ? 4000 : 30000);
    };
    tick();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [activeProjectId]);

  // Retry immediately (and surface the error once) when the user opens Sources.
  useEffect(() => {
    if (activeView === 'sources' && activeProjectId) fetchBackendQueue(activeProjectId);
  }, [activeView]);

  const mergedState: DBState | null = state
    ? { ...state, ingestQueue: [...state.ingestQueue, ...backendQueue] }
    : null;

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
      beginClarification,
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
      isBackendIngestItem: (id: string) => backendQueueIds.current.has(id),
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
