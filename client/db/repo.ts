import type {
  Agent,
  Decision,
  IngestItem,
  Item,
  ProjectSummary,
  VerdictDetail,
  WebSource
} from '../src/types.js';
import type { DB } from './index.js';
import { defaultApiConfig } from './seed.js';
import type { ApiConfig, ProjectRecord, StoreShape } from './types.js';

// The repository: every SQL statement the app runs lives here (plans/node-sqlite-store.md).
// Routes and read-only code (ask/author/verdict analysis) never see SQL — reads that need a
// whole project get a ProjectRecord snapshot, the same shape the JSON store used to hand out.

// ---- row shapes + mappers -------------------------------------------------------------------

interface ProjectRow { id: string; name: string; created_at: string }
interface ItemRow {
  id: number; title: string; description: string; status: string; priority: string;
  assignee: string; area: string; created_at: string;
  source_json: string | null; verdict_json: string | null;
}
interface DecisionRow {
  id: number; title: string; description: string; date: string; area: string;
  created_by: string; source_snippet: string | null;
}
interface SourceRow {
  id: string; name: string; type: string; status: string;
  last_synced: string | null; pending_count: number;
}
interface IngestRow {
  id: string; title: string; description: string; area: string; priority: string;
  source_id: string; source_snippet: string; verdict_json: string;
}
interface AgentRow { id: string; name: string; kind: string; description: string | null; builtin: number }
interface ApiConfigRow {
  provider: string; provider_type: string; api_key: string; region: string;
  embeddings_provider: string; embeddings_key: string; no_retention: number; isolate_tenant: number;
}

const toJson = (value: unknown): string | null => (value == null ? null : JSON.stringify(value));

// Optional fields (Decision.sourceSnippet, WebSource.lastSynced, Agent.description) are only
// present on the object when set, exactly as they were in the JSON store — keeps API output
// identical rather than sprinkling `null`s the UI never saw.
function rowToItem(r: ItemRow): Item {
  return {
    id: r.id,
    title: r.title,
    description: r.description,
    status: r.status as Item['status'],
    priority: r.priority as Item['priority'],
    assignee: r.assignee,
    area: r.area,
    created_at: r.created_at,
    source: r.source_json ? JSON.parse(r.source_json) : null,
    verdict: r.verdict_json ? JSON.parse(r.verdict_json) : null
  };
}

function rowToDecision(r: DecisionRow): Decision {
  return {
    id: r.id,
    title: r.title,
    description: r.description,
    date: r.date,
    area: r.area,
    createdBy: r.created_by,
    ...(r.source_snippet != null ? { sourceSnippet: r.source_snippet } : {})
  };
}

function rowToSource(r: SourceRow): WebSource {
  return {
    id: r.id,
    name: r.name,
    type: r.type as WebSource['type'],
    status: r.status as WebSource['status'],
    ...(r.last_synced != null ? { lastSynced: r.last_synced } : {}),
    pendingCount: r.pending_count
  };
}

function rowToIngest(r: IngestRow): IngestItem {
  return {
    id: r.id,
    title: r.title,
    description: r.description,
    area: r.area,
    priority: r.priority as IngestItem['priority'],
    sourceId: r.source_id,
    sourceSnippet: r.source_snippet,
    verdict: JSON.parse(r.verdict_json)
  };
}

function rowToAgent(r: AgentRow): Agent {
  return {
    id: r.id,
    name: r.name,
    kind: r.kind as Agent['kind'],
    ...(r.description != null ? { description: r.description } : {}),
    builtin: r.builtin === 1
  };
}

function rowToApiConfig(r: ApiConfigRow): ApiConfig {
  return {
    provider: r.provider as ApiConfig['provider'],
    providerType: r.provider_type as ApiConfig['providerType'],
    apiKey: r.api_key,
    region: r.region,
    embeddingsProvider: r.embeddings_provider as ApiConfig['embeddingsProvider'],
    embeddingsKey: r.embeddings_key,
    noRetention: r.no_retention === 1,
    isolateTenant: r.isolate_tenant === 1
  };
}

// The only fields PUT /api/items/:id may change. `id` is deliberately absent (the JSON store let
// a request body silently rewrite it), and unknown keys are dropped instead of being persisted.
const ITEM_PATCH_COLUMNS: Record<string, { column: string; json?: boolean }> = {
  title: { column: 'title' },
  description: { column: 'description' },
  status: { column: 'status' },
  priority: { column: 'priority' },
  assignee: { column: 'assignee' },
  area: { column: 'area' },
  created_at: { column: 'created_at' },
  source: { column: 'source_json', json: true },
  verdict: { column: 'verdict_json', json: true }
};

// POST /api/config used to spread any request-body key into the stored config. Now: only the
// known fields, and only when the value has the right type.
function pickApiConfigPatch(patch: Record<string, unknown>): Partial<ApiConfig> {
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(defaultApiConfig) as (keyof ApiConfig)[]) {
    if (key in patch && typeof patch[key] === typeof defaultApiConfig[key]) {
      out[key] = patch[key];
    }
  }
  return out as Partial<ApiConfig>;
}

// ---- duplicate detection for the one-time import ---------------------------------------------

function findDuplicates<T>(rows: T[], key: (row: T) => string | number): (string | number)[] {
  const seen = new Set<string | number>();
  const dupes = new Set<string | number>();
  for (const row of rows) {
    const k = key(row);
    if (seen.has(k)) dupes.add(k);
    seen.add(k);
  }
  return [...dupes];
}

function assertNoDuplicateIds(store: StoreShape): void {
  const problems: string[] = [];
  const projectDupes = findDuplicates(store.projects, p => p.id);
  if (projectDupes.length) problems.push(`duplicate project ids: ${projectDupes.join(', ')}`);
  for (const p of store.projects) {
    for (const [table, dupes] of [
      ['items', findDuplicates(p.items, i => i.id)],
      ['decisions', findDuplicates(p.decisions, d => d.id)],
      ['sources', findDuplicates(p.sources, s => s.id)],
      ['ingestQueue', findDuplicates(p.ingestQueue, q => q.id)]
    ] as const) {
      if (dupes.length) problems.push(`project ${p.id}: duplicate ${table} ids: ${dupes.join(', ')}`);
    }
  }
  const agentDupes = findDuplicates(store.agents, a => a.id);
  if (agentDupes.length) problems.push(`duplicate agent ids: ${agentDupes.join(', ')}`);
  if (problems.length) {
    // Fail loudly rather than dropping rows: a silently-lost board item is worse than a boot error.
    throw new Error(`Cannot import the JSON store — fix these and restart:\n  - ${problems.join('\n  - ')}`);
  }
}

// ---- the repository --------------------------------------------------------------------------

export function createRepo(db: DB) {
  const stmt = {
    listProjects: db.prepare(`
      SELECT p.id, p.name, p.created_at AS createdAt,
        (SELECT COUNT(*) FROM items i        WHERE i.project_id = p.id) AS itemCount,
        (SELECT COUNT(*) FROM decisions d    WHERE d.project_id = p.id) AS decisionCount,
        (SELECT COUNT(*) FROM sources s      WHERE s.project_id = p.id) AS sourceCount,
        (SELECT COUNT(*) FROM ingest_queue q WHERE q.project_id = p.id) AS pendingCount
      FROM projects p ORDER BY p.seq`),
    projectById: db.prepare('SELECT id, name, created_at FROM projects WHERE id = ?'),
    firstProject: db.prepare('SELECT id, name, created_at FROM projects ORDER BY seq LIMIT 1'),
    insertProject: db.prepare('INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)'),
    deleteProject: db.prepare('DELETE FROM projects WHERE id = ?'),

    itemsFor: db.prepare('SELECT * FROM items WHERE project_id = ? ORDER BY seq'),
    itemById: db.prepare('SELECT * FROM items WHERE project_id = ? AND id = ?'),
    maxItemId: db.prepare('SELECT COALESCE(MAX(id), 99) AS m FROM items WHERE project_id = ?'),
    insertItem: db.prepare(`
      INSERT INTO items (project_id, id, title, description, status, priority, assignee, area, created_at, source_json, verdict_json)
      VALUES (@project_id, @id, @title, @description, @status, @priority, @assignee, @area, @created_at, @source_json, @verdict_json)`),
    setItemVerdict: db.prepare('UPDATE items SET verdict_json = ? WHERE project_id = ? AND id = ?'),
    deleteItem: db.prepare('DELETE FROM items WHERE project_id = ? AND id = ?'),

    decisionsFor: db.prepare('SELECT * FROM decisions WHERE project_id = ? ORDER BY seq'),
    maxDecisionId: db.prepare('SELECT COALESCE(MAX(id), 0) AS m FROM decisions WHERE project_id = ?'),
    insertDecision: db.prepare(`
      INSERT INTO decisions (project_id, id, title, description, date, area, created_by, source_snippet)
      VALUES (@project_id, @id, @title, @description, @date, @area, @created_by, @source_snippet)`),
    appendDecisionDescription: db.prepare(
      "UPDATE decisions SET description = description || ? WHERE project_id = ? AND id = ?"),

    sourcesFor: db.prepare('SELECT * FROM sources WHERE project_id = ? ORDER BY seq'),
    sourceExists: db.prepare('SELECT 1 FROM sources WHERE project_id = ? AND id = ?'),
    insertSource: db.prepare(`
      INSERT INTO sources (project_id, id, name, type, status, last_synced, pending_count)
      VALUES (@project_id, @id, @name, @type, @status, @last_synced, @pending_count)`),

    ingestFor: db.prepare('SELECT * FROM ingest_queue WHERE project_id = ? ORDER BY seq'),
    ingestById: db.prepare('SELECT * FROM ingest_queue WHERE project_id = ? AND id = ?'),
    insertIngest: db.prepare(`
      INSERT INTO ingest_queue (project_id, id, title, description, area, priority, source_id, source_snippet, verdict_json)
      VALUES (@project_id, @id, @title, @description, @area, @priority, @source_id, @source_snippet, @verdict_json)`),
    deleteIngest: db.prepare('DELETE FROM ingest_queue WHERE project_id = ? AND id = ?'),

    agents: db.prepare('SELECT * FROM agents ORDER BY seq'),
    agentById: db.prepare('SELECT * FROM agents WHERE id = ?'),
    agentExists: db.prepare('SELECT 1 FROM agents WHERE id = ?'),
    insertAgent: db.prepare(
      'INSERT INTO agents (id, name, kind, description, builtin) VALUES (@id, @name, @kind, @description, @builtin)'),
    deleteAgent: db.prepare('DELETE FROM agents WHERE id = ?'),

    apiConfig: db.prepare('SELECT * FROM api_config WHERE id = 1'),
    upsertApiConfig: db.prepare(`
      INSERT OR REPLACE INTO api_config
        (id, provider, provider_type, api_key, region, embeddings_provider, embeddings_key, no_retention, isolate_tenant)
      VALUES (1, @provider, @provider_type, @api_key, @region, @embeddings_provider, @embeddings_key, @no_retention, @isolate_tenant)`),

    getMeta: db.prepare('SELECT value FROM meta WHERE key = ?'),
    setMeta: db.prepare('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)')
  };

  const nowIso = () => new Date().toISOString();

  function getItem(projectId: string, id: number): Item | undefined {
    const row = stmt.itemById.get(projectId, id) as ItemRow | undefined;
    return row ? rowToItem(row) : undefined;
  }

  const createItem = db.transaction(
    (
      projectId: string,
      fields: Partial<Pick<Item, 'title' | 'description' | 'status' | 'priority' | 'assignee' | 'area' | 'source'>>
    ): Item => {
      // Same allocation the JSON store used: per-project max+1, first item of a project is #100.
      // Runs inside the transaction, so allocation and insert are atomic.
      const id = (stmt.maxItemId.get(projectId) as { m: number }).m + 1;
      const verdict: VerdictDetail = {
        type: 'checking',
        confidence: 100,
        message: 'Checking against past decisions...',
        candidates: []
      };
      stmt.insertItem.run({
        project_id: projectId,
        id,
        title: fields.title || 'Untitled Item',
        description: fields.description || '',
        status: fields.status || 'inbox',
        priority: fields.priority || 'P2',
        assignee: fields.assignee || 'AM',
        area: fields.area || 'general',
        created_at: nowIso(),
        source_json: toJson(fields.source),
        verdict_json: toJson(verdict)
      });
      return getItem(projectId, id)!;
    }
  );

  const createDecision = db.transaction(
    (projectId: string, fields: Partial<Pick<Decision, 'title' | 'description' | 'area' | 'createdBy'>>): Decision => {
      const id = (stmt.maxDecisionId.get(projectId) as { m: number }).m + 1;
      stmt.insertDecision.run({
        project_id: projectId,
        id,
        title: fields.title || 'New Decision',
        description: fields.description || '',
        date: nowIso().split('T')[0],
        area: fields.area || 'general',
        created_by: fields.createdBy || 'AM',
        source_snippet: null
      });
      return rowToDecision(
        db.prepare('SELECT * FROM decisions WHERE project_id = ? AND id = ?').get(projectId, id) as DecisionRow
      );
    }
  );

  // Ids like 'proj-<Date.now()>' collide if two are created in the same millisecond; the JSON
  // store silently produced duplicates, here a UNIQUE constraint would throw — so bump instead.
  function uniqueTimestampId(prefix: string, exists: (id: string) => boolean): string {
    let n = Date.now();
    while (exists(`${prefix}${n}`)) n++;
    return `${prefix}${n}`;
  }

  const importStore = db.transaction((store: StoreShape) => {
    assertNoDuplicateIds(store);
    for (const p of store.projects) {
      const where = (table: string, id: string | number) => `project ${p.id}, ${table} ${id}`;
      const insert = (table: string, id: string | number, run: () => void) => {
        try { run(); } catch (e) { throw new Error(`Import failed at ${where(table, id)}: ${(e as Error).message}`); }
      };
      stmt.insertProject.run(p.id, p.name, p.createdAt);
      for (const i of p.items) {
        insert('item', i.id, () => stmt.insertItem.run({
          project_id: p.id, id: i.id, title: i.title, description: i.description ?? '',
          status: i.status, priority: i.priority, assignee: i.assignee, area: i.area,
          created_at: i.created_at, source_json: toJson(i.source), verdict_json: toJson(i.verdict)
        }));
      }
      for (const d of p.decisions) {
        insert('decision', d.id, () => stmt.insertDecision.run({
          project_id: p.id, id: d.id, title: d.title, description: d.description ?? '',
          date: d.date, area: d.area, created_by: d.createdBy, source_snippet: d.sourceSnippet ?? null
        }));
      }
      for (const s of p.sources) {
        insert('source', s.id, () => stmt.insertSource.run({
          project_id: p.id, id: s.id, name: s.name, type: s.type, status: s.status,
          last_synced: s.lastSynced ?? null, pending_count: s.pendingCount ?? 0
        }));
      }
      for (const q of p.ingestQueue) {
        insert('ingestQueue', q.id, () => stmt.insertIngest.run({
          project_id: p.id, id: q.id, title: q.title, description: q.description ?? '',
          area: q.area, priority: q.priority, source_id: q.sourceId,
          source_snippet: q.sourceSnippet ?? '', verdict_json: toJson(q.verdict)
        }));
      }
    }
    for (const a of store.agents) {
      stmt.insertAgent.run({
        id: a.id, name: a.name, kind: a.kind, description: a.description ?? null, builtin: a.builtin ? 1 : 0
      });
    }
    writeApiConfig(store.apiConfig);
    stmt.setMeta.run('bootstrapped', new Date().toISOString());
  });

  function writeApiConfig(c: ApiConfig): void {
    stmt.upsertApiConfig.run({
      provider: c.provider, provider_type: c.providerType, api_key: c.apiKey, region: c.region,
      embeddings_provider: c.embeddingsProvider, embeddings_key: c.embeddingsKey,
      no_retention: c.noRetention ? 1 : 0, isolate_tenant: c.isolateTenant ? 1 : 0
    });
  }

  function getApiConfig(): ApiConfig {
    const row = stmt.apiConfig.get() as ApiConfigRow | undefined;
    return row ? rowToApiConfig(row) : { ...defaultApiConfig };
  }

  return {
    // ---- bootstrap ----
    // "Has this database ever been initialised" is a flag, not "are there projects": a user who
    // deletes every project must not get the seed data resurrected on the next restart.
    isBootstrapped: (): boolean => stmt.getMeta.get('bootstrapped') !== undefined,
    importStore,

    // ---- projects ----
    listProjectSummaries: (): ProjectSummary[] => stmt.listProjects.all() as ProjectSummary[],

    // Without an id: the first project — older callers that send no projectId keep working.
    getProject(id?: string): ProjectRecord | undefined {
      const row = (id ? stmt.projectById.get(id) : stmt.firstProject.get()) as ProjectRow | undefined;
      if (!row) return undefined;
      return {
        id: row.id,
        name: row.name,
        createdAt: row.created_at,
        items: (stmt.itemsFor.all(row.id) as ItemRow[]).map(rowToItem),
        decisions: (stmt.decisionsFor.all(row.id) as DecisionRow[]).map(rowToDecision),
        sources: (stmt.sourcesFor.all(row.id) as SourceRow[]).map(rowToSource),
        ingestQueue: (stmt.ingestFor.all(row.id) as IngestRow[]).map(rowToIngest)
      };
    },

    createProject(name: string): ProjectSummary {
      const id = uniqueTimestampId('proj-', candidate => stmt.projectById.get(candidate) !== undefined);
      const createdAt = nowIso();
      stmt.insertProject.run(id, name, createdAt);
      return { id, name, createdAt, itemCount: 0, decisionCount: 0, sourceCount: 0, pendingCount: 0 };
    },

    // ON DELETE CASCADE removes the project's items/decisions/sources/ingest queue with it.
    deleteProject: (id: string): boolean => stmt.deleteProject.run(id).changes > 0,

    // ---- items ----
    getItem,
    createItem,

    updateItem(projectId: string, id: number, patch: Record<string, unknown>): Item | undefined {
      const sets: string[] = [];
      const params: unknown[] = [];
      for (const [key, spec] of Object.entries(ITEM_PATCH_COLUMNS)) {
        if (!(key in patch) || patch[key] === undefined) continue;
        if (spec.json) {
          sets.push(`${spec.column} = ?`);
          params.push(toJson(patch[key]));
        } else if (patch[key] != null) {
          sets.push(`${spec.column} = ?`);
          params.push(String(patch[key]));
        }
      }
      if (sets.length) {
        db.prepare(`UPDATE items SET ${sets.join(', ')} WHERE project_id = ? AND id = ?`).run(...params, projectId, id);
      }
      return getItem(projectId, id);
    },

    // A 0-row no-op when the item was deleted while an async verdict analysis was in flight —
    // the same guard the JSON store had via findIndex, now free.
    setItemVerdict(projectId: string, id: number, verdict: VerdictDetail | null): void {
      stmt.setItemVerdict.run(toJson(verdict), projectId, id);
    },

    deleteItem: (projectId: string, id: number): boolean => stmt.deleteItem.run(projectId, id).changes > 0,

    // ---- decisions ----
    createDecision,
    appendToDecisionDescription: (projectId: string, id: number, suffix: string): boolean =>
      stmt.appendDecisionDescription.run(suffix, projectId, id).changes > 0,

    // ---- sources ----
    createSource(projectId: string, fields: { type?: WebSource['type']; name?: string }): WebSource {
      const id = uniqueTimestampId('src-', candidate => stmt.sourceExists.get(projectId, candidate) !== undefined);
      const source: WebSource = {
        id,
        name: fields.name || 'Connected source',
        type: fields.type || 'upload',
        status: 'synced',
        lastSynced: 'just now',
        pendingCount: 0
      };
      stmt.insertSource.run({
        project_id: projectId, id, name: source.name, type: source.type, status: source.status,
        last_synced: source.lastSynced, pending_count: source.pendingCount
      });
      return source;
    },

    // ---- ingest review queue ----
    addIngestItems: db.transaction((projectId: string, items: IngestItem[]): void => {
      for (const q of items) {
        stmt.insertIngest.run({
          project_id: projectId, id: q.id, title: q.title, description: q.description ?? '',
          area: q.area, priority: q.priority, source_id: q.sourceId,
          source_snippet: q.sourceSnippet ?? '', verdict_json: toJson(q.verdict)
        });
      }
    }),
    getIngestItem(projectId: string, id: string): IngestItem | undefined {
      const row = stmt.ingestById.get(projectId, id) as IngestRow | undefined;
      return row ? rowToIngest(row) : undefined;
    },
    deleteIngestItem: (projectId: string, id: string): boolean => stmt.deleteIngest.run(projectId, id).changes > 0,

    // Approve = create the board card (carrying the queued verdict and the real citation as its
    // source snippet) AND drop it from the queue, atomically — a crash can't leave the same
    // candidate both on the board and still awaiting review.
    approveIngestItem: db.transaction(
      (
        projectId: string,
        queued: IngestItem,
        resolved: { title: string; description: string; area: string; priority: string; sourceSnippet: string }
      ): Item => {
        const created = createItem(projectId, {
          title: resolved.title,
          description: resolved.description,
          status: 'inbox',
          priority: resolved.priority as Item['priority'],
          assignee: 'AM',
          area: resolved.area,
          source: { type: 'upload', name: 'Ingestion Pipeline', snippet: resolved.sourceSnippet }
        });
        stmt.setItemVerdict.run(toJson(queued.verdict), projectId, created.id);
        stmt.deleteIngest.run(projectId, queued.id);
        return getItem(projectId, created.id)!;
      }
    ),

    // ---- agents (workspace-wide) ----
    listAgents: (): Agent[] => (stmt.agents.all() as AgentRow[]).map(rowToAgent),
    getAgent(id: string): Agent | undefined {
      const row = stmt.agentById.get(id) as AgentRow | undefined;
      return row ? rowToAgent(row) : undefined;
    },
    createAgent(fields: { name: string; kind: Agent['kind'] }): Agent {
      const id = uniqueTimestampId('custom-', candidate => stmt.agentExists.get(candidate) !== undefined);
      stmt.insertAgent.run({ id, name: fields.name, kind: fields.kind, description: null, builtin: 0 });
      return { id, name: fields.name, kind: fields.kind, builtin: false };
    },
    deleteAgent: (id: string): boolean => stmt.deleteAgent.run(id).changes > 0,

    // ---- workspace AI settings ----
    getApiConfig,
    updateApiConfig(patch: Record<string, unknown>): ApiConfig {
      const merged = { ...getApiConfig(), ...pickApiConfigPatch(patch) };
      writeApiConfig(merged);
      return merged;
    }
  };
}

export type Repo = ReturnType<typeof createRepo>;
