// Run with: npm test  (node:test through tsx — no extra test dependency).
// Every test opens its own ':memory:' database, so tests are independent and touch no files.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, test } from 'node:test';
import type { IngestItem, Item } from '../src/types.js';
import { bootstrap, parseStoreFile } from './import-json.js';
import { openDatabase } from './index.js';
import { createRepo } from './repo.js';
import { defaultAgents, defaultApiConfig, freshStore } from './seed.js';
import type { StoreShape } from './types.js';

function freshRepo() {
  const db = openDatabase(':memory:');
  return { db, repo: createRepo(db) };
}

const silent = { log: () => {}, warn: () => {} };

const ingestItem = (id: string, extra: Partial<IngestItem> = {}): IngestItem => ({
  id,
  title: `Candidate ${id}`,
  description: 'desc',
  area: 'auth',
  priority: 'P1',
  sourceId: 'src-abc',
  sourceSnippet: 'we need this',
  verdict: { type: 'net-new', confidence: 100, message: 'Net-new', candidates: [] },
  ...extra
});

const item = (id: number): Item => ({
  id,
  title: `Item ${id}`,
  description: '',
  status: 'inbox',
  priority: 'P2',
  assignee: 'AM',
  area: 'general',
  created_at: '2026-01-01T00:00:00.000Z',
  source: null,
  verdict: null
});

function storeWith(projects: StoreShape['projects']): StoreShape {
  return { projects, apiConfig: { ...defaultApiConfig }, agents: defaultAgents.map(a => ({ ...a })) };
}

const emptyProject = (id: string, name = id) => ({
  id, name, createdAt: '2026-01-01T00:00:00Z', items: [], decisions: [], sources: [], ingestQueue: []
});

describe('schema', () => {
  test('migrations run once and are idempotent', () => {
    const db = openDatabase(':memory:');
    assert.equal(db.pragma('user_version', { simple: true }), 1);
    // re-opening/migrating an up-to-date database is a no-op, not an error
    assert.doesNotThrow(() => openDatabase(':memory:'));
  });

  test('foreign keys are enforced', () => {
    const { db } = freshRepo();
    assert.equal(db.pragma('foreign_keys', { simple: true }), 1);
    assert.throws(() =>
      db.prepare("INSERT INTO items (project_id,id,title,status,priority,assignee,area,created_at) VALUES ('nope',1,'t','inbox','P2','AM','g','x')").run()
    );
  });
});

describe('round-trip parity with the JSON store', () => {
  test('the built-in seed project reads back identical to what was imported', () => {
    const { repo } = freshRepo();
    const seed = freshStore();
    repo.importStore(seed);

    const got = repo.getProject('proj-core')!;
    const want = seed.projects[0];
    // The only tolerated difference: an Item missing `source`/`verdict` reads back as null
    // (the TS type says `| null`, and the UI treats missing and null the same).
    const norm = (i: Item) => ({ ...i, source: i.source ?? null, verdict: i.verdict ?? null });
    assert.deepEqual(got.items, want.items.map(norm));
    assert.deepEqual(got.decisions, want.decisions);
    assert.deepEqual(got.sources, want.sources);
    assert.deepEqual(got.ingestQueue, want.ingestQueue);
    assert.equal(got.name, want.name);
    assert.equal(got.createdAt, want.createdAt);
    // Guard against this test silently passing on an empty seed.
    for (const [name, rows] of Object.entries({
      items: got.items, decisions: got.decisions, sources: got.sources, ingestQueue: got.ingestQueue
    })) {
      assert.ok(rows.length > 0, `seed ${name} should not be empty`);
    }
  });

  test('optional fields that ARE set survive the round trip (the seed never sets them)', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([{
      ...emptyProject('p1'),
      decisions: [{ id: 1, title: 'd', description: 'x', date: '2026-01-01', area: 'a', createdBy: 'AM', sourceSnippet: 'quoted line' }],
      sources: [{ id: 's1', name: 'n', type: 'sheet', status: 'syncing', lastSynced: '2 min ago', pendingCount: 3 }]
    }]));
    const p = repo.getProject('p1')!;
    assert.equal(p.decisions[0].sourceSnippet, 'quoted line');
    assert.deepEqual(p.sources[0], { id: 's1', name: 'n', type: 'sheet', status: 'syncing', lastSynced: '2 min ago', pendingCount: 3 });
  });

  test('agents (incl. the boolean builtin flag) and api config round-trip', () => {
    const { repo } = freshRepo();
    repo.importStore(freshStore());
    assert.deepEqual(repo.listAgents(), defaultAgents);
    assert.deepEqual(repo.getApiConfig(), defaultApiConfig);
    assert.equal(typeof repo.listAgents()[0].builtin, 'boolean');
    assert.equal(typeof repo.getApiConfig().noRetention, 'boolean');
  });

  test('insertion order is preserved even when ids are not ascending', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([{ ...emptyProject('p1'), items: [item(5), item(3), item(9)] }]));
    assert.deepEqual(repo.getProject('p1')!.items.map(i => i.id), [5, 3, 9]);
  });

  test('optional fields stay absent (not null) when unset', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([{
      ...emptyProject('p1'),
      decisions: [{ id: 1, title: 'd', description: '', date: '2026-01-01', area: 'a', createdBy: 'AM' }],
      sources: [{ id: 's1', name: 'n', type: 'upload', status: 'synced', pendingCount: 0 }]
    }]));
    const p = repo.getProject('p1')!;
    assert.ok(!('sourceSnippet' in p.decisions[0]));
    assert.ok(!('lastSynced' in p.sources[0]));
  });
});

describe('id allocation (behaviour-preserving)', () => {
  test('first item of an empty project is #100, then max+1', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1')]));
    assert.equal(repo.createItem('p1', { title: 'a' }).id, 100);
    assert.equal(repo.createItem('p1', { title: 'b' }).id, 101);
  });

  test('continues from the highest existing id, not from 100', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([{ ...emptyProject('p1'), items: [item(7), item(42)] }]));
    assert.equal(repo.createItem('p1', {}).id, 43);
  });

  test('ids are per-project', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1'), emptyProject('p2')]));
    assert.equal(repo.createItem('p1', {}).id, 100);
    assert.equal(repo.createItem('p2', {}).id, 100);
  });

  test('deleting the highest id lets it be reused (existing quirk, preserved on purpose)', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1')]));
    repo.createItem('p1', {});
    const second = repo.createItem('p1', {});
    repo.deleteItem('p1', second.id);
    assert.equal(repo.createItem('p1', {}).id, second.id);
  });

  test('decisions start at #1 and increment per project', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1')]));
    assert.equal(repo.createDecision('p1', { title: 'x' }).id, 1);
    assert.equal(repo.createDecision('p1', { title: 'y' }).id, 2);
  });

  test('timestamp ids never collide when created in the same millisecond', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1')]));
    const projectIds = Array.from({ length: 5 }, () => repo.createProject('x').id);
    const sourceIds = Array.from({ length: 5 }, () => repo.createSource('p1', {}).id);
    const agentIds = Array.from({ length: 5 }, () => repo.createAgent({ name: 'a', kind: 'custom' }).id);
    for (const ids of [projectIds, sourceIds, agentIds]) assert.equal(new Set(ids).size, ids.length);
  });
});

describe('items', () => {
  test('a new item gets the same defaults and "checking" verdict the server always gave', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1')]));
    const it = repo.createItem('p1', {});
    assert.equal(it.title, 'Untitled Item');
    assert.equal(it.status, 'inbox');
    assert.equal(it.priority, 'P2');
    assert.equal(it.assignee, 'AM');
    assert.equal(it.area, 'general');
    assert.equal(it.source, null);
    assert.equal(it.verdict?.type, 'checking');
    assert.match(it.created_at, /^\d{4}-\d{2}-\d{2}T/);
  });

  test('update changes only whitelisted fields: id and unknown keys are ignored', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1')]));
    const { id } = repo.createItem('p1', { title: 'orig' });

    const updated = repo.updateItem('p1', id, {
      title: 'new title', status: 'done', id: 999, bogus: 'x', projectId: 'p1'
    })!;

    assert.equal(updated.id, id);
    assert.equal(updated.title, 'new title');
    assert.equal(updated.status, 'done');
    assert.ok(!('bogus' in updated));
    assert.equal(repo.getItem('p1', 999), undefined);
  });

  test('update can set and clear the JSON fields', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1')]));
    const { id } = repo.createItem('p1', {});
    const src = { type: 'upload' as const, name: 'brief.txt', snippet: 'quote' };
    assert.deepEqual(repo.updateItem('p1', id, { source: src })!.source, src);
    assert.equal(repo.updateItem('p1', id, { source: null })!.source, null);
  });

  test('update of a missing item returns undefined', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1')]));
    assert.equal(repo.updateItem('p1', 12345, { title: 'x' }), undefined);
  });

  test('setItemVerdict on a deleted item is a silent no-op (async analysis finishing late)', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1')]));
    const { id } = repo.createItem('p1', {});
    repo.deleteItem('p1', id);
    assert.doesNotThrow(() =>
      repo.setItemVerdict('p1', id, { type: 'net-new', confidence: 100, message: 'late', candidates: [] })
    );
    assert.equal(repo.getItem('p1', id), undefined);
  });

  test('verdicts round-trip as structured JSON', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1')]));
    const { id } = repo.createItem('p1', {});
    const verdict = {
      type: 'conflict' as const, confidence: 88, message: 'Conflicts with Decision #4',
      candidates: [{ id: '4', type: 'decision' as const, title: 'IdP', reason: 'because', confidence: 88 }],
      citation: { id: '4', type: 'decision' as const, title: 'IdP', snippet: 'use the IdP' }
    };
    repo.setItemVerdict('p1', id, verdict);
    assert.deepEqual(repo.getItem('p1', id)!.verdict, verdict);
  });
});

describe('projects', () => {
  test('list returns summaries with live counts, in creation order', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([
      { ...emptyProject('p1', 'One'), items: [item(1), item(2)], ingestQueue: [ingestItem('q1')] },
      emptyProject('p2', 'Two')
    ]));
    assert.deepEqual(repo.listProjectSummaries(), [
      { id: 'p1', name: 'One', createdAt: '2026-01-01T00:00:00Z', itemCount: 2, decisionCount: 0, sourceCount: 0, pendingCount: 1 },
      { id: 'p2', name: 'Two', createdAt: '2026-01-01T00:00:00Z', itemCount: 0, decisionCount: 0, sourceCount: 0, pendingCount: 0 }
    ]);
  });

  test('getProject without an id returns the first project; unknown id returns undefined', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('first'), emptyProject('second')]));
    assert.equal(repo.getProject()!.id, 'first');
    assert.equal(repo.getProject('nope'), undefined);
  });

  test('deleting a project cascades to everything it owns', () => {
    const { db, repo } = freshRepo();
    repo.importStore(storeWith([{
      ...emptyProject('p1'),
      items: [item(1)],
      decisions: [{ id: 1, title: 'd', description: '', date: 'x', area: 'a', createdBy: 'AM' }],
      sources: [{ id: 's', name: 'n', type: 'upload', status: 'synced', pendingCount: 0 }],
      ingestQueue: [ingestItem('q')]
    }, emptyProject('keep')]));

    assert.equal(repo.deleteProject('p1'), true);
    for (const table of ['items', 'decisions', 'sources', 'ingest_queue']) {
      const n = (db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get() as { n: number }).n;
      assert.equal(n, 0, `${table} should be empty after cascade`);
    }
    assert.ok(repo.getProject('keep'), 'other projects are untouched');
    assert.equal(repo.deleteProject('p1'), false, 'deleting again reports not-found');
  });
});

describe('decisions, sources, ingest queue, agents, config', () => {
  test('superseding appends to a decision description', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1')]));
    const d = repo.createDecision('p1', { title: 't', description: 'base' });
    assert.equal(repo.appendToDecisionDescription('p1', d.id, '\n[SUPERSEDED]'), true);
    assert.equal(repo.getProject('p1')!.decisions[0].description, 'base\n[SUPERSEDED]');
    assert.equal(repo.appendToDecisionDescription('p1', 999, 'x'), false);
  });

  test('ingest queue: add, read, delete, JSON verdict preserved', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1')]));
    repo.addIngestItems('p1', [ingestItem('a'), ingestItem('b')]);
    assert.deepEqual(repo.getProject('p1')!.ingestQueue.map(q => q.id), ['a', 'b']);
    assert.deepEqual(repo.getIngestItem('p1', 'a')!.verdict, ingestItem('a').verdict);
    assert.equal(repo.deleteIngestItem('p1', 'a'), true);
    assert.equal(repo.getIngestItem('p1', 'a'), undefined);
    assert.equal(repo.deleteIngestItem('p1', 'a'), false);
  });

  test('a duplicate ingest id fails loudly instead of overwriting', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([emptyProject('p1')]));
    repo.addIngestItems('p1', [ingestItem('a')]);
    assert.throws(() => repo.addIngestItems('p1', [ingestItem('a')]));
  });

  test('agents: custom ones are non-builtin and deletable', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([]));
    const a = repo.createAgent({ name: 'Mine', kind: 'custom' });
    assert.equal(a.builtin, false);
    assert.equal(repo.getAgent(a.id)!.name, 'Mine');
    assert.equal(repo.getAgent('figma-ai')!.builtin, true);
    assert.equal(repo.deleteAgent(a.id), true);
    assert.equal(repo.getAgent(a.id), undefined);
  });

  test('api config: known fields merge; unknown keys and wrong types are ignored', () => {
    const { repo } = freshRepo();
    repo.importStore(storeWith([]));
    const out = repo.updateApiConfig({
      provider: 'byok', apiKey: 'sk-test', noRetention: false,
      injected: 'evil', isolateTenant: 'yes', region: 42
    });
    assert.equal(out.provider, 'byok');
    assert.equal(out.apiKey, 'sk-test');
    assert.equal(out.noRetention, false);
    assert.equal(out.isolateTenant, defaultApiConfig.isolateTenant, 'wrong type ignored');
    assert.equal(out.region, defaultApiConfig.region, 'wrong type ignored');
    assert.ok(!('injected' in out));
    assert.deepEqual(repo.getApiConfig(), out, 'persisted, not just returned');
  });
});

describe('import', () => {
  test('duplicate ids abort the whole import, name the culprits, and leave the db empty', () => {
    const { repo } = freshRepo();
    const bad = storeWith([{ ...emptyProject('p1'), items: [item(1), item(1), item(2), item(2)] }]);
    assert.throws(() => repo.importStore(bad), /project p1: duplicate items ids: 1, 2/);
    assert.equal(repo.listProjectSummaries().length, 0);
    assert.equal(repo.isBootstrapped(), false);
  });

  test('a row that violates a constraint aborts everything, with its location in the message', () => {
    const { repo } = freshRepo();
    const broken = { ...item(1), assignee: undefined as unknown as string };
    assert.throws(() => repo.importStore(storeWith([{ ...emptyProject('p1'), items: [item(2), broken] }])),
      /Import failed at project p1, item 1/);
    assert.equal(repo.listProjectSummaries().length, 0, 'rolled back — no half-imported project');
  });
});

describe('parseStoreFile', () => {
  test('multi-project format', () => {
    const s = parseStoreFile({ projects: [emptyProject('p1')], agents: [], apiConfig: { region: 'eu' } })!;
    assert.equal(s.projects.length, 1);
    assert.equal(s.apiConfig.region, 'eu');
    assert.equal(s.apiConfig.provider, defaultApiConfig.provider, 'missing config fields get defaults');
    assert.deepEqual(s.agents, defaultAgents, 'empty agent list falls back to the built-ins');
  });

  test('legacy single-state format becomes one "Core Platform" project', () => {
    const s = parseStoreFile({ items: [item(1)], decisions: [], sources: [] })!;
    assert.equal(s.projects.length, 1);
    assert.equal(s.projects[0].id, 'proj-core');
    assert.equal(s.projects[0].items.length, 1);
    assert.deepEqual(s.projects[0].ingestQueue, []);
  });

  test('anything else is unrecognised', () => {
    assert.equal(parseStoreFile({}), null);
    assert.equal(parseStoreFile(null), null);
  });
});

describe('bootstrap', () => {
  const tmpJson = (contents: string) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nexus-db-test-'));
    const file = path.join(dir, 'database.json');
    fs.writeFileSync(file, contents);
    return file;
  };

  test('seeds the starter project when there is no JSON file, then never runs again', () => {
    const { repo } = freshRepo();
    assert.equal(bootstrap(repo, '/definitely/not/here.json', silent), 'seeded');
    assert.equal(repo.getProject()!.id, 'proj-core');
    assert.equal(bootstrap(repo, '/definitely/not/here.json', silent), 'skipped');
  });

  test('imports an existing JSON file, and does not touch it', () => {
    const { repo } = freshRepo();
    const raw = JSON.stringify(storeWith([{ ...emptyProject('mine', 'My project'), items: [item(1)] }]));
    const file = tmpJson(raw);
    assert.equal(bootstrap(repo, file, silent), 'imported');
    assert.deepEqual(repo.listProjectSummaries().map(p => p.id), ['mine']);
    assert.equal(fs.readFileSync(file, 'utf-8'), raw, 'the JSON file is left exactly as it was');
  });

  test('deleting every project does NOT resurrect the seed on the next boot', () => {
    const { repo } = freshRepo();
    bootstrap(repo, '/nope.json', silent);
    repo.deleteProject('proj-core');
    assert.equal(repo.listProjectSummaries().length, 0);
    assert.equal(bootstrap(repo, '/nope.json', silent), 'skipped');
    assert.equal(repo.listProjectSummaries().length, 0);
  });

  test('a corrupt JSON file refuses to boot instead of silently hiding data behind the seed', () => {
    const { repo } = freshRepo();
    assert.throws(() => bootstrap(repo, tmpJson('{ not json'), silent), /not valid JSON/);
    assert.equal(repo.isBootstrapped(), false);
  });

  test('an unrecognised JSON shape falls back to the seed (as the old server did)', () => {
    const { repo } = freshRepo();
    assert.equal(bootstrap(repo, tmpJson('{"hello":"world"}'), silent), 'seeded');
  });
});
