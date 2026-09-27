import express from 'express';
import path from 'path';
import { createServer as createViteServer } from 'vite';
import { GoogleGenAI } from '@google/genai';
import { DBState, VerdictDetail, IngestItem, WebSource } from './src/types.js';
import { bootstrap } from './db/import-json.js';
import { openDatabase } from './db/index.js';
import { createRepo } from './db/repo.js';
import type { ProjectRecord } from './db/types.js';

const app = express();
const PORT = Number(process.env.PORT) || 3000;

app.use(express.json());

// The board data (projects, items, decisions, sources, ingest queue, agents, AI settings) lives
// in SQLite — see client/db/ and plans/node-sqlite-store.md. On first run it is populated from the
// legacy client/data/database.json (or the built-in seed); that file is never written again.
const db = openDatabase();
const repo = createRepo(db);
bootstrap(repo, path.join(process.cwd(), 'data', 'database.json'));

// Close cleanly so SQLite checkpoints its WAL file.
for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.on(signal, () => {
    db.close();
    process.exit(0);
  });
}

// Resolve the project a request targets (query param for GET/DELETE, body for
// POST/PUT). Falls back to the first project so older callers keep working.
// Returns a snapshot: read-only code (ask/author/verdict analysis) consumes it as a plain object,
// while mutations go through `repo` with `proj.id`.
function resolveProject(req: express.Request): ProjectRecord | undefined {
  const pid = (req.query.projectId as string) || (req.body && req.body.projectId);
  return repo.getProject(pid || undefined);
}

function buildState(proj: ProjectRecord): DBState {
  return {
    items: proj.items,
    decisions: proj.decisions,
    sources: proj.sources,
    ingestQueue: proj.ingestQueue,
    agents: repo.listAgents(),
    apiConfig: repo.getApiConfig()
  };
}

// Helpers for invoking Gemini
function getGeminiClient() {
  let key = process.env.GEMINI_API_KEY;
  const apiConfig = repo.getApiConfig();
  if (apiConfig.provider === 'byok' && apiConfig.apiKey) {
    key = apiConfig.apiKey;
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
  res.json(repo.listProjectSummaries());
});

app.post('/api/projects', (req, res) => {
  const name = (req.body.name || '').trim() || 'Untitled project';
  res.json(repo.createProject(name));
});

app.delete('/api/projects/:id', (req, res) => {
  // ON DELETE CASCADE removes the project's items, decisions, sources and ingest queue with it.
  if (!repo.deleteProject(req.params.id)) return res.status(404).json({ error: "Project not found" });
  res.json({ success: true });
});

// Workspace-wide AI agent catalog (shared across projects).
app.post('/api/agents', (req, res) => {
  const name = (req.body.name || '').trim();
  if (!name) return res.status(400).json({ error: "Agent name required" });
  const validKinds = ['design', 'code', 'qa', 'docs', 'test', 'security', 'custom'];
  const kind = validKinds.includes(req.body.kind) ? req.body.kind : 'custom';
  res.json(repo.createAgent({ name, kind }));
});

app.delete('/api/agents/:id', (req, res) => {
  const agent = repo.getAgent(req.params.id);
  if (!agent) return res.status(404).json({ error: "Agent not found" });
  if (agent.builtin) return res.status(400).json({ error: "Built-in agents cannot be removed" });
  repo.deleteAgent(req.params.id);
  res.json({ success: true });
});

// Connect a source to a project (used by the new-project sources setup step).
app.post('/api/sources', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const { type, name } = req.body as { type: WebSource['type']; name?: string };
  res.json(repo.createSource(proj.id, { type, name }));
});

// REST APIs
app.get('/api/state', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });
  res.json(buildState(proj));
});

app.post('/api/config', (req, res) => {
  const { projectId, ...cfg } = req.body || {};
  // Only the known settings are stored (unknown keys are ignored, not persisted).
  res.json({ success: true, apiConfig: repo.updateApiConfig(cfg) });
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
// Create is immediate. Task-vs-task verdicts are checked by FastAPI
// (POST /api/projects/:id/verdicts/check) from ProjectContext — Node must not
// run analyseInBackground here or the mock/Gemini board+decisions path overwrites
// the real verdict. resolveVerdict stays on Node.

app.post('/api/items', async (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const newItem = repo.createItem(proj.id, req.body);
  res.json(newItem);
});

app.put('/api/items/:id', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const itemId = parseInt(req.params.id);
  const prevItem = repo.getItem(proj.id, itemId);
  if (!prevItem) {
    return res.status(404).json({ error: "Item not found" });
  }

  const { projectId, ...patch } = req.body;

  // Title/description edits keep the checking chip until the client persists
  // the FastAPI verdict. Do not kick off Node background analysis.
  const needsRecheck =
    (patch.title !== undefined && patch.title !== prevItem.title) ||
    (patch.description !== undefined && patch.description !== prevItem.description);
  if (needsRecheck) {
    patch.verdict = {
      type: 'checking',
      confidence: 100,
      message: 'Re-checking decisions...',
      candidates: []
    };
  }

  const updatedItem = repo.updateItem(proj.id, itemId, patch)!;
  res.json(updatedItem);
});

app.delete('/api/items/:id', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  if (repo.deleteItem(proj.id, parseInt(req.params.id))) {
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
  const item = repo.getItem(proj.id, itemId);

  if (!item) {
    return res.status(404).json({ error: "Item not found" });
  }

  if (action === 'dismiss') {
    // Mark as clean or cleared
    repo.setItemVerdict(proj.id, itemId, {
      type: 'net-new',
      confidence: 100,
      message: "Dismissed conflict. Backlog item approved by user.",
      candidates: []
    });
  } else if (action === 'merge') {
    // Delete item or change status/merge details
    if (req.body.targetId) {
      repo.deleteItem(proj.id, itemId);
    }
  } else if (action === 'supersede') {
    // De-couple decision or create a superseded note inside database decisions
    const decId = parseInt(req.body.targetId);
    if (!isNaN(decId)) {
      // Create an update/link noting it is superseded
      repo.appendToDecisionDescription(
        proj.id,
        decId,
        `\n[SUPERSEDED BY ITEM #${item.id} ON ${new Date().toLocaleDateString()}]`
      );
    }
    repo.setItemVerdict(proj.id, itemId, {
      type: 'net-new',
      confidence: 100,
      message: `Superseded Decision #${req.body.targetId}. Net-new validated.`,
      candidates: []
    });
  } else if (action === 'confirm') {
    // Kept as flagged for historical lock
    if (item.verdict) {
      repo.setItemVerdict(proj.id, itemId, {
        ...item.verdict,
        message: "Confirmed conflict. Backlog item remains flagged for rework."
      });
    }
  }

  res.json({ success: true, item: repo.getItem(proj.id, itemId) ?? null });
});

// Decisions endpoints
app.post('/api/decisions', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  res.json(repo.createDecision(proj.id, req.body));
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

// Sources review pipeline (a mock: one Gemini call — or a canned item when there is no API key —
// per uploaded text; the review queue lives in SQLite via `repo`)
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
    repo.addIngestItems(proj.id, mockExtracted);
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
          // The (project, id) pair is a primary key in SQLite, so ids in one batch must not collide.
          id: `ingest-${Date.now()}-${results.length}`,
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

    repo.addIngestItems(proj.id, results);
    res.json({ success: true, count: results.length, items: results });
  } catch (error) {
    console.error("Failed to parse document via AI, pushing mockup item:", error);
    const mockExtracted = [buildMockExtracted()];
    repo.addIngestItems(proj.id, mockExtracted);
    res.json({ success: true, count: mockExtracted.length, items: mockExtracted });
  }
});

// Resolve Ingest Queue elements (Add to Board or skip)
app.post('/api/ingest/resolve', (req, res) => {
  const proj = resolveProject(req);
  if (!proj) return res.status(404).json({ error: "Project not found" });

  const { id, action } = req.body; // 'approve' | 'dismiss'
  const queued = repo.getIngestItem(proj.id, id);

  if (!queued) {
    return res.status(404).json({ error: "Item not found in review queue" });
  }

  if (action === 'approve') {
    // Migrate to the board: the card is created and the queue entry removed in one transaction.
    repo.approveIngestItem(proj.id, queued, {
      title: queued.title,
      description: queued.description,
      area: queued.area,
      priority: queued.priority,
      sourceSnippet: queued.sourceSnippet
    });
  } else {
    repo.deleteIngestItem(proj.id, id);
  }
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
