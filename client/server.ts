import express from 'express';
import path from 'path';
import fs from 'fs';
import { createServer as createViteServer } from 'vite';
import { GoogleGenAI } from '@google/genai';
import { DBState, Item, Decision, VerdictDetail, IngestItem, WebSource, Priority, Status, Agent } from './src/types.js';

const app = express();
const PORT = 3000;

app.use(express.json());

const DB_DIR = path.join(process.cwd(), 'data');
const DB_FILE = path.join(DB_DIR, 'database.json');

// A project owns its own board, memory, sources and ingest queue. The AI/data
// posture (apiConfig) is a workspace-level setting shared across projects.
interface ProjectRecord {
  id: string;
  name: string;
  createdAt: string;
  items: Item[];
  decisions: Decision[];
  sources: WebSource[];
  ingestQueue: IngestItem[];
}

interface Store {
  projects: ProjectRecord[];
  apiConfig: DBState['apiConfig'];
  agents: Agent[];
}

// Workspace-wide catalog of assignable AI agents, shared across all projects.
const defaultAgents: Agent[] = [
  { id: 'figma-ai', name: 'Figma AI', kind: 'design', description: 'Creates Figma designs and mockups.', builtin: true },
  { id: 'github-copilot', name: 'GitHub Copilot', kind: 'code', description: 'Implements and reviews code.', builtin: true },
  { id: 'frontend-dev', name: 'Frontend Dev Agent', kind: 'code', description: 'Builds UI and frontend features.', builtin: true },
  { id: 'backend-dev', name: 'Backend Dev Agent', kind: 'code', description: 'Builds APIs and backend services.', builtin: true },
  { id: 'qa-tester', name: 'QA Tester Agent', kind: 'qa', description: 'Exploratory testing and bug triage.', builtin: true },
  { id: 'docs-writer', name: 'Docs Writer Agent', kind: 'docs', description: 'Writes and updates documentation.', builtin: true },
  { id: 'unit-test-gen', name: 'Unit Test Generator Agent', kind: 'test', description: 'Generates unit tests for code.', builtin: true },
  { id: 'security-compliance', name: 'Security & Compliance Agent', kind: 'security', description: 'Reviews security and compliance.', builtin: true }
];

const defaultApiConfig: DBState['apiConfig'] = {
  provider: 'managed',
  providerType: 'gemini',
  apiKey: '',
  region: 'us-central1',
  embeddingsProvider: 'gemini',
  embeddingsKey: '',
  noRetention: true,
  isolateTenant: true
};

// The pre-seeded backlog/memory that ships as the first ("Core Platform") project.
function seedSlice(): Pick<ProjectRecord, 'items' | 'decisions' | 'sources' | 'ingestQueue'> {
  return {
    items: [
      {
        id: 71,
        title: "Billing Authorization Security Block",
        description: "Integrate role-based authorization parameters within the core subscription and checkout invoice controllers. Validate tier-based features on both client-side and server-side.",
        status: "in_progress",
        priority: "P1",
        assignee: "AM",
        area: "auth",
        created_at: "2026-05-15T10:00:00Z",
        source: { type: "ticket", name: "JIRA-402", snippet: "Implement backend RBAC for invoice controllers." },
        verdict: null
      },
      {
        id: 88,
        title: "High-volume CSV Export Reporter",
        description: "Asynchronous backend reporting systems that stream large export data directly into structured storage and return secure expirable download URLs. Replaces old synchronous server-blocking CSV dumps.",
        status: "done",
        priority: "P1",
        assignee: "JD",
        area: "reporting",
        created_at: "2026-05-20T11:00:00Z",
        source: { type: "sheet", name: "Product Backlog Sync", snippet: "Row #88: Asynchronous background worker report generator." },
        verdict: {
          type: "net-new",
          confidence: 100,
          message: "Net-new — nothing like this yet",
          candidates: []
        }
      },
      {
        id: 120,
        title: "Post-Login Deep-Linking Redirect Flow",
        description: "Sequence router deep-linking and state recovery redirect flags once standard login validation completes successfully. Currently breaks if enterprise clients land with deep nested subroutes directly.",
        status: "inbox",
        priority: "P2",
        assignee: "AM",
        area: "auth",
        created_at: "2026-05-28T09:30:00Z",
        source: { type: "email", name: "Enterprise Workspace HelpDesk", snippet: "Deep linking redirects after nested subdomain logins fail intermittently." },
        verdict: {
          type: "impact",
          confidence: 85,
          message: "Touches the same authentication flow as Billing Authorization Security Block (#71). Ensure route protection structures are dry.",
          candidates: [
            { id: "71", type: "item", title: "Billing Authorization Security Block", reason: "Both modify global auth validation parameters.", confidence: 85 }
          ],
          citation: {
            id: "71",
            type: "item",
            title: "Billing Authorization Security Block",
            snippet: "Integrate role-based authorization parameters within core controllers."
          }
        }
      },
      {
        id: 95,
        title: "Export Billing Details directly to CSV file button",
        description: "Add a button directly on the invoice overview tab to trigger export logs into a CSV download. Needs to compile billing summaries.",
        status: "next",
        priority: "P2",
        assignee: "JD",
        area: "reporting",
        created_at: "2026-05-25T14:45:00Z",
        source: { type: "sheet", name: "Product Backlog Sync", snippet: "Row #95: Export raw tables to file outputs." },
        verdict: {
          type: "duplicate",
          confidence: 91,
          message: "Duplicate of existing card High-volume CSV Export Reporter (#88)",
          candidates: [
            { id: "88", type: "item", title: "High-volume CSV Export Reporter", reason: "Duplicates the CSV export workers and mechanisms already made in #88.", confidence: 91 }
          ],
          citation: {
            id: "88",
            type: "item",
            title: "High-volume CSV Export Reporter",
            snippet: "Asynchronous backend reporting systems that stream large export data..."
          }
        }
      }
    ],
    decisions: [
      {
        id: 4,
        title: "Rely on customer IdP instead of building built-in custom SSO",
        description: "In the 2026-03 Architecture call we decided to rely heavily on the customer's enterprise Identity Provider (IdP) via single sign-on redirect workflows instead of creating our own database-backed custom SSO models, minimizing credential management overhead and securing data flows.",
        date: "2026-03-14",
        area: "auth",
        createdBy: "AM"
      },
      {
        id: 9,
        title: "Enforce multi-factor auth (MFA) as absolute default",
        description: "To meet regulatory governance structures and compliance objectives, Multi-Factor Authentication (MFA) must be enforced statically for all high-privilege executive and administrator panels.",
        date: "2026-04-10",
        area: "auth",
        createdBy: "AM"
      },
      {
        id: 12,
        title: "Consolidate reporting CSV outputs on server side",
        description: "We decide to use a unified asynchronous exporter for CSV reports instead of spawning individual client-side scraping scripts, ensuring security limits.",
        date: "2026-05-12",
        area: "reporting",
        createdBy: "JD"
      }
    ],
    sources: [
      { id: "src-sheet", name: "Google Backlog Sync Sheet", type: "sheet", status: "synced", lastSynced: "2 minutes ago", pendingCount: 0 },
      { id: "src-transcript", name: "🎙 Arch Call Transcripts", type: "transcript", status: "synced", lastSynced: "30 minutes ago", pendingCount: 3 },
      { id: "src-email", name: "✉ Customer Feedback Inbox", type: "email", status: "synced", lastSynced: "1 hour ago", pendingCount: 4 },
      { id: "src-ticket", name: "Jira Syncing Endpoint", type: "ticket", status: "needs_auth", pendingCount: 0 }
    ],
    ingestQueue: [
      {
        id: "ingest-1",
        title: "Add custom enterprise database-level auth system for custom SSO logins",
        description: "Develop custom internal password hashes and token providers supporting on-premise custom SSO login methods directly in database tables.",
        area: "auth",
        priority: "P1",
        sourceId: "src-transcript",
        sourceSnippet: "We need custom SSO that can connect direct credentials from database tables, bypass direct IdPs if customer doesn't have an outer identity portal.",
        verdict: {
          type: "conflict",
          confidence: 82,
          message: "Conflicts with architectural Decision #4 (Rely on customer IdP instead of building built-in custom SSO)",
          candidates: [
            {
              id: "4",
              type: "decision",
              title: "Rely on customer IdP instead of building built-in custom SSO",
              reason: "Directly contradicts the decision to rely strictly on the customer's IdP to avoid creating a database SSO repository.",
              confidence: 82
            }
          ],
          citation: {
            id: "4",
            type: "decision",
            title: "Rely on customer IdP instead of building built-in custom SSO",
            snippet: "decided to rely heavily on the customer's enterprise Identity Provider ... instead of creating our own database-backed custom SSO model"
          }
        }
      },
      {
        id: "ingest-2",
        title: "Synchronous client-side report download wizard",
        description: "Create a visual wizard allowing immediate client-side table rendering and direct browser CSV compilations.",
        area: "reporting",
        priority: "P2",
        sourceId: "src-email",
        sourceSnippet: "Please add standard browser-side scraping download button for current table results directly.",
        verdict: {
          type: "conflict",
          confidence: 89,
          message: "Conflicts with architectural Decision #12 (Consolidate reporting CSV outputs on server side)",
          candidates: [
            {
              id: "12",
              type: "decision",
              title: "Consolidate reporting CSV outputs on server side",
              reason: "Directly violates the decision to utilize asynchronous server workers over browser-based scraper dumps.",
              confidence: 89
            }
          ],
          citation: {
            id: "12",
            type: "decision",
            title: "Consolidate reporting CSV outputs on server side",
            snippet: "unified asynchronous exporter for CSV reports instead of spawning individual client-side scraping scripts"
          }
        }
      }
    ]
  };
}

function initializeStore(): Store {
  if (!fs.existsSync(DB_DIR)) {
    fs.mkdirSync(DB_DIR, { recursive: true });
  }

  const freshStore = (): Store => ({
    projects: [
      {
        id: 'proj-core',
        name: 'Core Platform',
        createdAt: '2026-03-01T00:00:00Z',
        ...seedSlice()
      }
    ],
    apiConfig: { ...defaultApiConfig },
    agents: defaultAgents.map(a => ({ ...a }))
  });

  if (!fs.existsSync(DB_FILE)) {
    const store = freshStore();
    fs.writeFileSync(DB_FILE, JSON.stringify(store, null, 2), 'utf-8');
    return store;
  }

  try {
    const raw = fs.readFileSync(DB_FILE, 'utf-8');
    const parsed = JSON.parse(raw);

    // New (multi-project) format.
    if (parsed && Array.isArray(parsed.projects)) {
      return {
        apiConfig: { ...defaultApiConfig, ...parsed.apiConfig },
        agents: Array.isArray(parsed.agents) && parsed.agents.length ? parsed.agents : defaultAgents.map(a => ({ ...a })),
        projects: parsed.projects
      };
    }

    // Legacy single-DBState format → migrate into one project.
    if (parsed && Array.isArray(parsed.items)) {
      return {
        apiConfig: { ...defaultApiConfig, ...parsed.apiConfig },
        agents: Array.isArray(parsed.agents) && parsed.agents.length ? parsed.agents : defaultAgents.map(a => ({ ...a })),
        projects: [
          {
            id: 'proj-core',
            name: 'Core Platform',
            createdAt: '2026-03-01T00:00:00Z',
            items: parsed.items || [],
            decisions: parsed.decisions || [],
            sources: parsed.sources || [],
            ingestQueue: parsed.ingestQueue || []
          }
        ]
      };
    }

    return freshStore();
  } catch (e) {
    console.warn("Could not read DB file, returning defaults", e);
    return freshStore();
  }
}

let store = initializeStore();

function saveStore() {
  try {
    fs.writeFileSync(DB_FILE, JSON.stringify(store, null, 2), 'utf-8');
  } catch (e) {
    console.error("Error writing DB", e);
  }
}

// Resolve the project a request targets (query param for GET/DELETE, body for
// POST/PUT). Falls back to the first project so older callers keep working.
function resolveProject(req: express.Request): ProjectRecord | undefined {
  const pid = (req.query.projectId as string) || (req.body && req.body.projectId);
  if (pid) return store.projects.find(p => p.id === pid);
  return store.projects[0];
}

function buildState(proj: ProjectRecord): DBState {
  return {
    items: proj.items,
    decisions: proj.decisions,
    sources: proj.sources,
    ingestQueue: proj.ingestQueue,
    agents: store.agents,
    apiConfig: store.apiConfig
  };
}

// Helpers for invoking Gemini
function getGeminiClient() {
  let key = process.env.GEMINI_API_KEY;
  if (store.apiConfig.provider === 'byok' && store.apiConfig.apiKey) {
    key = store.apiConfig.apiKey;
  }
  if (!key) return null;
  return new GoogleGenAI({
    apiKey: key,
    httpOptions: {
      headers: {
        'User-Agent': 'aistudio-build'
      }
    }
  });
}

// Project endpoints
app.get('/api/projects', (req, res) => {
  res.json(store.projects.map(p => ({
    id: p.id,
    name: p.name,
    createdAt: p.createdAt,
    itemCount: p.items.length,
    decisionCount: p.decisions.length,
    sourceCount: p.sources.length,
    pendingCount: p.ingestQueue.length
  })));
});

app.post('/api/projects', (req, res) => {
  const name = (req.body.name || '').trim() || 'Untitled project';
  const proj: ProjectRecord = {
    id: 'proj-' + Date.now(),
    name,
    createdAt: new Date().toISOString(),
    items: [],
    decisions: [],
    sources: [],
    ingestQueue: []
  };
  store.projects.push(proj);
  saveStore();
  res.json({ id: proj.id, name: proj.name, createdAt: proj.createdAt, itemCount: 0, decisionCount: 0, sourceCount: 0, pendingCount: 0 });
});

app.delete('/api/projects/:id', (req, res) => {
  const idx = store.projects.findIndex(p => p.id === req.params.id);
  if (idx === -1) return res.status(404).json({ error: "Project not found" });
  store.projects.splice(idx, 1);
  saveStore();
  res.json({ success: true });
});

// Workspace-wide AI agent catalog (shared across projects).
app.post('/api/agents', (req, res) => {
  const name = (req.body.name || '').trim();
  if (!name) return res.status(400).json({ error: "Agent name required" });
  const validKinds = ['design', 'code', 'qa', 'docs', 'test', 'security', 'custom'];
  const kind = validKinds.includes(req.body.kind) ? req.body.kind : 'custom';
  const agent: Agent = {
    id: 'custom-' + Date.now(),
    name,
    kind,
    builtin: false
  };
  store.agents.push(agent);
  saveStore();
  res.json(agent);
});

app.delete('/api/agents/:id', (req, res) => {
  const agent = store.agents.find(a => a.id === req.params.id);
  if (!agent) return res.status(404).json({ error: "Agent not found" });
  if (agent.builtin) return res.status(400).json({ error: "Built-in agents cannot be removed" });
  store.agents = store.agents.filter(a => a.id !== req.params.id);
  saveStore();
  res.json({ success: true });
});

// Connect a source to a project (used by the new-project sources setup step).
app.post('/api/sources', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const { type, name } = req.body as { type: WebSource['type']; name?: string };
  const src: WebSource = {
    id: 'src-' + Date.now(),
    name: name || 'Connected source',
    type: type || 'upload',
    status: 'synced',
    lastSynced: 'just now',
    pendingCount: 0
  };
  proj.sources.push(src);
  saveStore();
  res.json(src);
});

// REST APIs
app.get('/api/state', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });
  res.json(buildState(proj));
});

app.post('/api/config', (req, res) => {
  const { projectId, ...cfg } = req.body || {};
  store.apiConfig = { ...store.apiConfig, ...cfg };
  saveStore();
  res.json({ success: true, apiConfig: store.apiConfig });
});

// Helper for fuzzy match / rules check fallback when API key is missing.
// Project-aware so it never cites memory that doesn't exist in the project.
function mockAnalysis(proj: ProjectRecord, title: string, description: string): VerdictDetail {
  const normTitle = title.toLowerCase();
  const normDesc = description.toLowerCase();
  const blob = normTitle + ' ' + normDesc;

  // Conflict: custom SSO/credential work vs an IdP/SSO decision.
  if (blob.includes('sso') || blob.includes('single sign') || blob.includes('credential') || blob.includes('password')) {
    const dec = proj.decisions.find(d => /idp|sso|sign-on|sign on|credential/i.test(d.title + ' ' + d.description));
    if (dec) {
      return {
        type: 'conflict',
        confidence: 88,
        message: `Conflicts with Decision #${dec.id} (${dec.title})`,
        candidates: [
          {
            id: String(dec.id),
            type: 'decision',
            title: dec.title,
            reason: "Decision mandates relying on the customer's identity provider instead of an in-house credential store.",
            confidence: 88
          }
        ],
        citation: { id: String(dec.id), type: 'decision', title: dec.title, snippet: dec.description.slice(0, 180) }
      };
    }
  }

  // Duplicate: CSV/export work vs an existing export item.
  if (normTitle.includes('csv') || normDesc.includes('csv') || normTitle.includes('export')) {
    const it = proj.items.find(i => /csv|export/i.test(i.title));
    if (it) {
      return {
        type: 'duplicate',
        confidence: 91,
        message: `Looks like a duplicate of #${it.id} (${it.title})`,
        candidates: [
          {
            id: String(it.id),
            type: 'item',
            title: it.title,
            reason: 'Covers the same export flow already captured in this item.',
            confidence: 91
          }
        ],
        citation: { id: String(it.id), type: 'item', title: it.title, snippet: it.description.slice(0, 180) }
      };
    }
  }

  // Impact: billing/auth work vs an existing item in the same area.
  if (normTitle.includes('billing') || normTitle.includes('checkout') || normTitle.includes('auth') || normDesc.includes('billing')) {
    const it = proj.items.find(i => i.area === 'auth' || /auth|billing|checkout/i.test(i.title));
    if (it) {
      return {
        type: 'impact',
        confidence: 84,
        message: `Touches the same area as #${it.id} (${it.title})`,
        candidates: [
          {
            id: String(it.id),
            type: 'item',
            title: it.title,
            reason: 'Shares the billing/auth controllers and security configuration.',
            confidence: 84
          }
        ],
        citation: { id: String(it.id), type: 'item', title: it.title, snippet: it.description.slice(0, 180) }
      };
    }
  }

  // Otherwise, net-new!
  return {
    type: 'net-new',
    confidence: 100,
    message: "Net-new — nothing like this yet",
    candidates: []
  };
}

// Trigger analysis via live Gemini or fallback helper
async function performVerdictAnalysis(proj: ProjectRecord, title: string, description: string): Promise<VerdictDetail> {
  const client = getGeminiClient();
  if (!client) {
    // Graceful fallback simulation
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve(mockAnalysis(proj, title, description));
      }, 1500);
    });
  }

  try {
    const existingDecisions = proj.decisions.map(d => `Decision #${d.id}: "${d.title}" - Description: ${d.description} (Area: ${d.area})`).join('\n');
    const existingItems = proj.items.map(i => `Item #${i.id}: "${i.title}" - Description: ${i.description} (Area: ${i.area}, Status: ${i.status})`).join('\n');

    const prompt = `
You are the "Decision Memory Layer" core AI. Your job is to check a newly proposed backlog item or feature request against existing decisions and backlog items in other columns of a development planning environment.

Determined categories:
1. "duplicate" - The item is almost identical in scope and requirements to an existing card or decision (>=80% similarity).
2. "conflict" - The item directly contradicts or violates an agreed past architectural decision or backlog constraints.
3. "impact" - The item operates in the same functional or logical boundaries as an existing card or decisions (dependencies, risk overlap) without violating them.
4. "net-new" - No duplicate, conflict, or high impact. Clean land.

Proposed New Item:
Title: "${title}"
Description: "${description}"

Current Memory Context:
--- Existing Past Decisions ---
${existingDecisions}

--- Existing Active Board Backlog Items ---
${existingItems}

Format your output STRICTLY as a JSON object, matching the precise TypeScript interface with no leading or trailing markdown markers (no \`\`\`json blocks, just the raw braces).
Schema:
{
  "type": "duplicate" | "conflict" | "impact" | "net-new",
  "confidence": <number, 0 to 100 representing certainty percentage>,
  "message": "<A human-clear literal notification detailing the duplicate, conflict or dependency context>",
  "candidates": [
    {
      "id": "<string represent matching id, eg. '4' or '88'>",
      "type": "item" | "decision",
      "title": "<title of candidate matched>",
      "reason": "<one sentence describing why it matches>",
      "confidence": <number>
    }
  ],
  "citation": {
    "id": "<string ID matching>",
    "type": "item" | "decision" | "source",
    "title": "<matching title>",
    "snippet": "<exact quoted sentence from match that is contradicting, duplicating, or impacting>"
  }
}
`;

    const response = await client.models.generateContent({
      model: 'gemini-3.5-flash',
      contents: prompt,
      config: {
        responseMimeType: 'application/json'
      }
    });

    const parsed = JSON.parse(response.text || '{}');
    if (parsed && parsed.type) {
      return parsed;
    }
    return mockAnalysis(proj, title, description);
  } catch (error) {
    console.error("AI context run error, returning mockup solver:", error);
    return mockAnalysis(proj, title, description);
  }
}

// Items endpoints
app.post('/api/items', async (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const { title, description, status, priority, assignee, area, source } = req.body;
  const newId = proj.items.length > 0 ? Math.max(...proj.items.map(i => i.id)) + 1 : 100;

  const newItem: Item = {
    id: newId,
    title: title || "Untitled Item",
    description: description || "",
    status: status || "inbox",
    priority: priority || "P2",
    assignee: assignee || "AM",
    area: area || "general",
    created_at: new Date().toISOString(),
    source: source || null,
    verdict: {
      type: 'checking',
      confidence: 100,
      message: 'Checking against past decisions...',
      candidates: []
    }
  };

  proj.items.push(newItem);
  saveStore();

  // Async trigger to compile check status
  performVerdictAnalysis(proj, newItem.title, newItem.description).then((analyzedVerdict) => {
    const itemIndex = proj.items.findIndex(i => i.id === newId);
    if (itemIndex > -1) {
      proj.items[itemIndex].verdict = analyzedVerdict;
      saveStore();
    }
  });

  res.json(newItem);
});

app.put('/api/items/:id', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const itemId = parseInt(req.params.id);
  const foundIdx = proj.items.findIndex(i => i.id === itemId);

  if (foundIdx === -1) {
    return res.status(404).json({ error: "Item not found" });
  }

  const prevItem = proj.items[foundIdx];
  const updatedItem = { ...prevItem, ...req.body };
  delete (updatedItem as any).projectId;

  // If title or description changed, re-analyse background verdict
  if (req.body.title !== undefined && req.body.title !== prevItem.title ||
      req.body.description !== undefined && req.body.description !== prevItem.description) {
    updatedItem.verdict = {
      type: 'checking',
      confidence: 100,
      message: 'Re-checking decisions...',
      candidates: []
    };
    performVerdictAnalysis(proj, updatedItem.title, updatedItem.description).then((analyzedVerdict) => {
      const index = proj.items.findIndex(i => i.id === itemId);
      if (index > -1) {
        proj.items[index].verdict = analyzedVerdict;
        saveStore();
      }
    });
  }

  proj.items[foundIdx] = updatedItem;
  saveStore();
  res.json(updatedItem);
});

app.delete('/api/items/:id', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const itemId = parseInt(req.params.id);
  const removeIndex = proj.items.findIndex(i => i.id === itemId);
  if (removeIndex > -1) {
    proj.items.splice(removeIndex, 1);
    saveStore();
    res.json({ success: true });
  } else {
    res.status(404).json({ error: "Item not found" });
  }
});

app.post('/api/items/:id/verdict/resolve', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const itemId = parseInt(req.params.id);
  const action = req.body.action; // 'dismiss' | 'merge' | 'supersede' | 'confirm'
  const index = proj.items.findIndex(i => i.id === itemId);

  if (index === -1) {
    return res.status(404).json({ error: "Item not found" });
  }

  const item = proj.items[index];

  if (action === 'dismiss') {
    // Mark as clean or cleared
    item.verdict = {
      type: 'net-new',
      confidence: 100,
      message: "Dismissed conflict. Backlog item approved by user.",
      candidates: []
    };
  } else if (action === 'merge') {
    // Delete item or change status/merge details
    const targetMergeId = req.body.targetId;
    if (targetMergeId) {
      proj.items.splice(index, 1);
    }
  } else if (action === 'supersede') {
    // De-couple decision or create a superseded note inside database decisions
    const decId = parseInt(req.body.targetId);
    if (!isNaN(decId)) {
      const decIdx = proj.decisions.findIndex(d => d.id === decId);
      if (decIdx > -1) {
        // Create an update/link noting it is superseded
        proj.decisions[decIdx].description += `\n[SUPERSEDED BY ITEM #${item.id} ON ${new Date().toLocaleDateString()}]`;
      }
    }
    item.verdict = {
      type: 'net-new',
      confidence: 100,
      message: `Superseded Decision #${req.body.targetId}. Net-new validated.`,
      candidates: []
    };
  } else if (action === 'confirm') {
    // Kept as flagged for historical lock
    if (item.verdict) {
      item.verdict.message = "Confirmed conflict. Backlog item remains flagged for rework.";
    }
  }

  saveStore();
  res.json({ success: true, item: proj.items[index] || null });
});

// Decisions endpoints
app.post('/api/decisions', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const { title, description, area, createdBy } = req.body;
  const newId = proj.decisions.length > 0 ? Math.max(...proj.decisions.map(d => d.id)) + 1 : 1;

  const newDecision: Decision = {
    id: newId,
    title: title || "New Decision",
    description: description || "",
    area: area || "general",
    createdBy: createdBy || "AM",
    date: new Date().toISOString().split('T')[0]
  };

  proj.decisions.push(newDecision);
  saveStore();
  res.json(newDecision);
});

// Conversational Ask Memory endpoint
app.post('/api/ask', async (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const { query, activeItemId } = req.body;
  const client = getGeminiClient();

  const mockAnswers: Record<string, string> = {
    "why did we decide against building sso": `We decided against building custom built-in SSO in the **2026-03 architecture call** (documented in [decision #4](#decision-4)) to avoid the systemic security risk and overhead of credential ownership, encryption patterns, and regulatory compliance. Instead, we mandate relying on external corporate identity providers (OAuth/SAML) directly.\n\nThis decision is referenced heavily by auth components and avoids over-engineering auth schemas.`,
    "what is the state of auth": `The authentication layer is currently bounded by 2 core Decisions and 2 active Backlog Items:\n\n* **Past Decisions:**\n  - [Enforce MFA as default (Decision #9)](#decision-9) (Mandate Multi-Factor configuration for high privilege admin views).\n  - [Rely on Customer IdP (Decision #4)](#decision-4) (Rely on external SAML/OpenID connectors).\n\n* **Active Backlog Items:**\n  - [Billing Auth Block (Item #71)](#item-71) (*In Progress*) - Adding checkout gatekeeper auth check variables.\n  - [Post-Login Deep-Linking Redirect (Item #120)](#item-120) (*Inbox*) - Resolving subdomain routes logic.`,
    "what breaks if we change csv": `If you change CSV reports, you affect [High-volume CSV Export Reporter (Item #88)](#item-88) (*Done*) and must comply with [Consolidate reporting CSV outputs on server side (Decision #12)](#decision-12). It emphasizes that all CSV formats should execute via separate asynchronous background processes on the server rather than direct client-side scraping loads.`
  };

  // Pre-matched smart mock
  const cleanQ = (query || '').toLowerCase().trim();
  let selectedMock = "";
  for (const k of Object.keys(mockAnswers)) {
    if (cleanQ.includes(k) || k.includes(cleanQ)) {
      selectedMock = mockAnswers[k];
      break;
    }
  }

  if (!selectedMock) {
    if (proj.decisions.length === 0 && proj.items.length === 0) {
      selectedMock = `This project doesn't have any memory yet. Connect a source or add a few cards and decisions, and I'll be able to answer questions with citations.`;
    } else {
      selectedMock = `Based on the active Decision Memory, the team has implemented strict parameters around the **auth** and **reporting** categories. For **auth**, our absolute baseline is [Decision #4 (Rely on customer IdP)](#decision-4) which stops internal database-based logins, and [Decision #9 (Enforce MFA)](#decision-9). For **reporting**, we maintain [Decision #12](#decision-12) to avoid client-side scraping.\n\nCould you specify which part of the system or database rules you would like me to retrieve?`;
    }
  }

  if (!client) {
    return res.json({
      answer: selectedMock,
      citations: proj.decisions.slice(0, 1).map(d => ({
        id: `decision-${d.id}`,
        type: 'decision',
        title: d.title,
        snippet: d.description
      }))
    });
  }

  try {
    const decisionsText = proj.decisions.map(d => `[Decision #${d.id}]: ${d.title} - ${d.description}`).join('\n');
    const itemsText = proj.items.map(i => `[Backlog Item #${i.id}] (Status: ${i.status}, Area: ${i.area}): ${i.title} - ${i.description}`).join('\n');

    let itemContext = "";
    if (activeItemId) {
      const activeObj = proj.items.find(i => i.id === activeItemId);
      if (activeObj) {
        itemContext = `You are focusing on Item #${activeObj.id}: "${activeObj.title}" - Description: ${activeObj.description}. Search solutions tailored to this card.`;
      }
    }

    const prompt = `
You are the "Decision Memory Layer" conversational partner. The user is asking: "${query}".
Analyze the provided decisions and backlog cards. Respond with a clear, professional, direct markdown-formatted answer explaining why, what, or how based strictly on these files.
Always quote the source using markdown hyperlinks of type [decision #ID](#decision-ID) or [item #ID](#item-ID) or cited names.

Available Project Memory:
--- Past Team Decisions ---
${decisionsText}

--- Backlog Tasks and Cards ---
${itemsText}

${itemContext}

Maintain a direct, precise tone. Cite specific items and decisions directly in your markdown summary.
`;

    const response = await client.models.generateContent({
      model: 'gemini-3.5-flash',
      contents: prompt
    });

    res.json({
      answer: response.text || selectedMock,
      citations: proj.decisions.slice(0, 1).map(d => ({
        id: `decision-${d.id}`,
        type: 'decision',
        title: d.title,
        snippet: d.description
      }))
    });
  } catch (err) {
    console.error("Ask query API failure, using mock synthesis:", err);
    res.json({
      answer: selectedMock,
      citations: []
    });
  }
});

// Author BRD/Specs endpoints
app.post('/api/author', async (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const { type, area, timeFrame } = req.body; // 'brd' | 'spec' | 'tree'
  const client = getGeminiClient();

  // Count unresolved conflicts in chosen scope
  const conflictingItems = proj.items.filter(i => i.area === area && i.verdict && i.verdict.type === 'conflict');

  // Standard pre-defined output summaries
  const mockDocs: Record<string, string> = {
    'brd': `# Business Requirement Document - Authentication Framework
## 1. Objective
Enable enterprise-grade credentials assertion while keeping credential vectors secured.

## 2. Constraints & Background
Consistent with past team architectural alignment, we rely on the customer's enterprise Identity Provider (IdP) via single sign-on redirect workflows ([Decision #4](#decision-4)) instead of building an internal custom username authentication stack. We also enforce mandated MFA for admin actions ([Decision #9](#decision-9)).

## 3. Product Features & Backlog Items
- **User Account Redirect Initialization:** Setup SAML redirects corresponding to [Post-Login Deep-Linking Redirect Flow (Item #120)](#item-120).
- **Control RBAC validation:** Ensure checkout hooks implement invoice assertions ([Billing Authorization Security Block (Item #71)](#item-71)).`,

    'spec': `# Technical Specification - Asynchronous Exporter Workers
## 1. System Design
Implement asynchronous report compilation tasks streaming results into S3 databases directly as formulated by [Consolidate reporting CSV outputs on server side (Decision #12)](#decision-12). All tables render downloads on background jobs instead of main server execution.

## 2. Requirements and APIs
* Backend service spawns microservices to query relational tables of [High-volume CSV Export Reporter (Item #88)](#item-88).`,

    'tree': `# Backlog Dependency Task Tree - Area: Auth
- **Level 1: Core OAuth configuration [Decision #4](#decision-4)**
  - Enforce redirect models after login routing ([Item #120](#item-120))
  - Support OAuth validation assertions in workspace gates
- **Level 2: Billing access RBAC [Item #71](#item-71)**
  - Validate billing tokens server-side`
  };

  const selectedDocType = type || 'brd';
  const sampleDoc = mockDocs[selectedDocType] || mockDocs['brd'];

  if (!client) {
    return res.json({
      unresolvedConflictsCount: conflictingItems.length,
      conflicts: conflictingItems.map(i => ({ id: i.id, title: i.title })),
      document: sampleDoc
    });
  }

  try {
    const scopeItems = proj.items.filter(i => i.area === area).map(i => `Item #${i.id}: "${i.title}" - Description: ${i.description}`).join('\n');
    const scopeDecisions = proj.decisions.filter(d => d.area === area).map(d => `Decision #${d.id}: "${d.title}" - Description: ${d.description}`).join('\n');

    const prompt = `
You are the "Decision Memory Layer" authoring module.
Generate a professional, detailed, human-ready draft formatted as markdown.
Document Type Requested: "${type.toUpperCase()}" (brd, technical spec, or hierarchical task tree).
Target Area: "${area}"
Time Boundary: "${timeFrame}"

Current Context in Area:
--- Decisions ---
${scopeDecisions || "No decisions recorded in this area."}

--- Active Backlog Cards ---
${scopeItems || "No items recorded in this area."}

Write a comprehensive, cited document. Use double brackets referencing decisions or items directly, like ([Decision #ID](#decision-ID)) or ([Item #ID](#item-ID)), inserting exact citations referencing why requirements are formulated this way.
`;

    const response = await client.models.generateContent({
      model: 'gemini-3.5-flash',
      contents: prompt
    });

    res.json({
      unresolvedConflictsCount: conflictingItems.length,
      conflicts: conflictingItems.map(i => ({ id: i.id, title: i.title })),
      document: response.text || sampleDoc
    });
  } catch (err) {
    console.error("Author generation failed, using sample:", err);
    res.json({
      unresolvedConflictsCount: conflictingItems.length,
      conflicts: conflictingItems.map(i => ({ id: i.id, title: i.title })),
      document: sampleDoc
    });
  }
});

// Deprecate Endpoints
app.post('/api/deprecate', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  // New/empty projects have nothing to retire yet.
  if (proj.items.length === 0 && proj.decisions.length === 0) {
    return res.json({ suggestions: [] });
  }

  // Suggest some deprecation candidates based on dormant tasks or superseded decisions
  const dps = [
    {
      id: "dec-12",
      title: "Synchronous CSV scraper route",
      reason: "Superseded by architectural High-volume CSV Export Reporter (#88) following server consolidations.",
      type: "superseded",
      confidence: 94,
      citation: "decision #12 (Consolidate reporting CSV outputs on server side)"
    },
    {
      id: "item-71",
      title: "Static authorization tier table mapping",
      reason: "Subsumed directly by centralized Billing Authorization Security Block (#71) integrations.",
      type: "dormant",
      confidence: 76,
      citation: "billing-auth card dependencies"
    }
  ];
  res.json({ suggestions: dps });
});

// Sources review pipeline
app.post('/api/sources/upload', async (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const { fileName, fileContent } = req.body;
  const client = getGeminiClient();

  const buildMockExtracted = (): IngestItem => {
    const title = "Add custom database-backed SSO login store";
    const description = "Setup server encryption algorithms to save and manage client enterprise dashboard credentials directly inside our server databases.";
    return {
      id: "ingest-" + Date.now(),
      title,
      description,
      area: "auth",
      priority: "P1",
      sourceId: "src-upload",
      sourceSnippet: `We should configure custom tables to write encryption credentials direct ... ${fileName || "Meeting Transcript"}`,
      verdict: mockAnalysis(proj, title, description)
    };
  };

  if (!client) {
    const mockExtracted = [buildMockExtracted()];
    proj.ingestQueue.push(...mockExtracted);
    saveStore();
    return res.json({ success: true, count: mockExtracted.length, items: mockExtracted });
  }

  try {
    const prompt = `
Parse the following text from an uploaded planning document/meeting transcript. Identify one logical feature proposal, backlog item, or requirement.
Output a JSON array representing the extracted backlog items.

Source File Content:
"${fileContent || "Develop custom internal password hashes and bypass external portals directly."}"

Generate a single JSON object in the array with properties:
{
  "title": "<short descriptive title>",
  "description": "<detailed requirement description>",
  "area": "auth" | "reporting" | "general",
  "priority": "P1" | "P2" | "P3"
}
`;

    const response = await client.models.generateContent({
      model: 'gemini-3.5-flash',
      contents: prompt,
      config: {
        responseMimeType: 'application/json'
      }
    });

    const parsed = JSON.parse(response.text || '[]');
    const results: IngestItem[] = [];

    const itemsToProcess = Array.isArray(parsed) ? parsed : [parsed];

    for (const rawItem of itemsToProcess) {
      if (rawItem && rawItem.title) {
        // Run alignment verdict against local project state
        const analysis = await performVerdictAnalysis(proj, rawItem.title, rawItem.description || '');
        results.push({
          id: "ingest-" + Math.floor(Math.random() * 100000),
          title: rawItem.title,
          description: rawItem.description || '',
          area: rawItem.area || 'general',
          priority: rawItem.priority || 'P2',
          sourceId: 'src-upload',
          sourceSnippet: fileContent ? fileContent.slice(0, 150) + "..." : "Uploaded document content excerpt",
          verdict: analysis
        });
      }
    }

    if (results.length === 0) {
      results.push(buildMockExtracted());
    }

    proj.ingestQueue.push(...results);
    saveStore();
    res.json({ success: true, count: results.length, items: results });
  } catch (error) {
    console.error("Failed to parse document via AI, pushing mockup item:", error);
    const mockExtracted = [buildMockExtracted()];
    proj.ingestQueue.push(...mockExtracted);
    saveStore();
    res.json({ success: true, count: mockExtracted.length, items: mockExtracted });
  }
});

// Resolve Ingest Queue elements (Add to Board or skip)
app.post('/api/ingest/resolve', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const { id, action } = req.body; // 'approve' | 'dismiss'
  const index = proj.ingestQueue.findIndex(iq => iq.id === id);

  if (index === -1) {
    return res.status(404).json({ error: "Item not found in review queue" });
  }

  const ingItem = proj.ingestQueue[index];

  if (action === 'approve') {
    // Migrate to items list!
    const newId = proj.items.length > 0 ? Math.max(...proj.items.map(i => i.id)) + 1 : 100;
    const newItem: Item = {
      id: newId,
      title: ingItem.title,
      description: ingItem.description,
      status: 'inbox',
      priority: ingItem.priority,
      assignee: 'AM',
      area: ingItem.area,
      created_at: new Date().toISOString(),
      source: {
        type: 'upload',
        name: 'Ingestion Pipeline',
        snippet: ingItem.sourceSnippet
      },
      verdict: ingItem.verdict
    };
    proj.items.push(newItem);
  }

  proj.ingestQueue.splice(index, 1);
  saveStore();
  res.json({ success: true });
});

// Start server containing Vite configuration OR hosting assets directly
async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
