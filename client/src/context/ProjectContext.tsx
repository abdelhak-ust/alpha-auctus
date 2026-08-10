import React, { createContext, useContext, useState, useEffect } from 'react';
import { DBState, Item, Decision, VerdictType, WebSource, IngestItem, ProjectSummary, Priority, Status, Agent, AgentKind, NewProjectDraft, DraftSource, ClarificationTurn } from '../types.js';

type ViewName = 'board' | 'verdicts' | 'memory' | 'impact' | 'author' | 'sources' | 'deprecate' | 'settings' | 'projects';

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
  beginClarification: (draft: NewProjectDraft) => void;
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
  uploadDocument: (name: string, content: string) => Promise<void>;
  resolveIngestItem: (id: string, action: 'approve' | 'dismiss') => Promise<void>;
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
    // If there's no project to fall back to, keep the user on the projects list.
    if (!activeProjectId) setActiveView('projects');
  };

  const beginClarification = (draft: NewProjectDraft) => {
    setSetupDraft(draft);
    setSetupPhase('chat');
  };

  const finishSetupAndGenerate = async (answers: ClarificationTurn[]) => {
    const draft: NewProjectDraft = { ...setupDraft, answers };

    // 1. Create the project (setup flow owns navigation, so route:false).
    const proj = await createProject(draft.name.trim() || 'Untitled project', { route: false });

    // 2. Assemble everything the AI can actually read into one ingestion blob.
    //    Only text is real; video/image are represented by their filenames so
    //    they still influence extraction (real transcription/OCR is deferred).
    const textFiles = draft.sources.filter(s => s.content).map(s => `# ${s.name}\n${s.content}`);
    const media = draft.sources.filter(s => !s.content).map(s => `- ${s.kind}: ${s.name}`);
    const qa = draft.answers.map(t => `Q: ${t.question}\nA: ${t.answer}`);
    const assembled = [
      `Project: ${draft.name}`,
      `\n## Description\n${draft.description}`,
      draft.github ? `\n## GitHub\n${draft.github} (analysis deferred)` : '',
      media.length ? `\n## Media sources (pending ingest)\n${media.join('\n')}` : '',
      textFiles.length ? `\n## Uploaded documents\n${textFiles.join('\n\n')}` : '',
      qa.length ? `\n## Clarifications\n${qa.join('\n\n')}` : ''
    ].filter(Boolean).join('\n');

    // 3. Push through the existing ingestion + verdict pipeline (mock or live).
    try {
      await fetch('/api/sources/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fileName: `${draft.name} — setup brief`, fileContent: assembled, projectId: proj.id })
      });
    } catch (e) {
      console.error('Task generation upload failed', e);
    }

    // 4. Land in the verdict review queue (Sources view) to confirm generated tasks.
    setSetupPhase('idle');
    setSetupDraft(emptyDraft());
    await refreshState();
    await fetchProjects();
    setActiveView('sources');
    triggerToast(`Generated tasks for "${proj.name}". Review them before they hit the board.`);
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

  const uploadDocument = async (name: string, content: string) => {
    await fetch('/api/sources/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fileName: name, fileContent: content, projectId: activeProjectId })
    });
    await refreshState();
    triggerToast(`Uploaded and ingested ${name}`);
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

  const activeProject = projects.find(p => p.id === activeProjectId) || null;

  return (
    <ProjectContext.Provider value={{
      state,
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
