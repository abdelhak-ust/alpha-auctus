// Ordered schema migrations, applied by db/index.ts via `PRAGMA user_version` (entry N brings
// the database from version N to N+1). Append new entries; never edit a shipped one — this is
// the versioned-schema principle backend/ follows with Alembic, minus the dependency.
//
// Conventions (plans/node-sqlite-store.md):
// - `seq` is an explicit insertion-order key: the JSON store's arrays gave ordering for free,
//   SQL needs it stated. The domain ids are separate.
// - Item/decision ids are per-project integers, so uniqueness is (project_id, id), not id alone.
// - Item.source, Item.verdict and IngestItem.verdict are opaque JSON blobs the UI renders (P5
//   redefines verdicts), so they stay JSON text rather than being normalized now.
// - status/priority/kind are plain TEXT with no CHECK: existing rows must never be rejected.
export const MIGRATIONS: string[] = [
  `
  CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
  );

  CREATE TABLE projects (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    id         TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
  );

  CREATE TABLE items (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    id           INTEGER NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL,
    priority     TEXT NOT NULL,
    assignee     TEXT NOT NULL,
    area         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    source_json  TEXT,
    verdict_json TEXT,
    UNIQUE (project_id, id)
  );

  CREATE TABLE decisions (
    seq            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    id             INTEGER NOT NULL,
    title          TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    date           TEXT NOT NULL,
    area           TEXT NOT NULL,
    created_by     TEXT NOT NULL,
    source_snippet TEXT,
    UNIQUE (project_id, id)
  );

  CREATE TABLE sources (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    id            TEXT NOT NULL,
    name          TEXT NOT NULL,
    type          TEXT NOT NULL,
    status        TEXT NOT NULL,
    last_synced   TEXT,
    pending_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE (project_id, id)
  );

  -- source_id is a plain string on purpose: ingestion-side source ids live in Postgres.
  CREATE TABLE ingest_queue (
    seq            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    id             TEXT NOT NULL,
    title          TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    area           TEXT NOT NULL,
    priority       TEXT NOT NULL,
    source_id      TEXT NOT NULL,
    source_snippet TEXT NOT NULL DEFAULT '',
    verdict_json   TEXT NOT NULL,
    UNIQUE (project_id, id)
  );

  CREATE TABLE agents (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    id          TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    description TEXT,
    builtin     INTEGER NOT NULL DEFAULT 0
  );

  -- Single-row workspace settings (the id=1 CHECK enforces exactly one row).
  CREATE TABLE api_config (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    provider            TEXT NOT NULL,
    provider_type       TEXT NOT NULL,
    api_key             TEXT NOT NULL DEFAULT '',
    region              TEXT NOT NULL,
    embeddings_provider TEXT NOT NULL,
    embeddings_key      TEXT NOT NULL DEFAULT '',
    no_retention        INTEGER NOT NULL,
    isolate_tenant      INTEGER NOT NULL
  );
  `
];
