---
feature: Real database (SQLite) for the board data client/server.ts owns
phase: P0
status: done
created: 2026-09-24
completed: 2026-09-25
---

# Real database (SQLite) for the board data

## Why

Everything the running app actually shows — projects, board items, decisions, sources, the
ingest review queue, the agent catalog, AI settings — lives in `client/data/database.json`, a
hand-rolled JSON file: the whole store is loaded into memory at boot, handlers mutate live
objects, and `saveStore()` rewrites the entire file after each change (`server.ts`
`initializeStore`/`saveStore`, lines ~246-317). No transactions, no schema, no constraints,
whole-file rewrites racing with fire-and-forget verdict updates (`performVerdictAnalysis(...)
.then(... saveStore())` in `POST/PUT /api/items`), and every test run dirties a git-tracked
file. The user asked for "a real db — sqlite for now".

## Interpretation (assumption to confirm — cheap to redirect *before* building)

"Real db" = give **the Node-owned data** a real embedded database, replacing the JSON file.
Node keeps owning board data; Python/Postgres keeps owning ingestion + AI + vectors — unchanged.
This is deliberately an **interim** step ("for now"): the master plan's long-term direction
(§3: "the real backend behind it, replacing `client/data/database.json`") still points at moving
this data into `backend/`/Postgres when a later phase needs it there (P1 Task Contract extends
`Item`; P5's conflict engine wants Items/Decisions next to the embeddings). **Not doing** (the
alternative reading): migrating Item/Decision/Project/Agent into new SQLAlchemy models now
behind a `client/server.ts` proxy. Bigger lift, avoids a second migration later — say so before
build and this plan gets rewritten.

## Spec grounding

`ui_ux_design.md`/`architecture.md` don't specify Node's storage — pure infrastructure, so
nothing to improvise against; the contract that matters is the API shapes in
`client/src/types.ts` (CLAUDE.md: "The API contract lives in `client/src/types.ts`"). Rule for
this feature: **zero API changes** — same routes, same request/response JSON.

## Placement

Master plan P0 (foundation / K substrate) — completes the "real data substrate" for the data P0
never migrated. No dependencies. New code lives in `client/db/`; only `client/server.ts`
consumes it.

## Impact analysis

Consumers of the store today and what happens to each:

| Consumer | Change |
|---|---|
| `client/src/context/ProjectContext.tsx` + all UI | None — API contract unchanged. |
| Python ingestion verdict (`backend/app/ingest/verdict.py` → Node `GET /api/state`) | None — same response shape. |
| `client/server.ts` mutating handlers: `POST/DELETE /api/projects`, `POST/DELETE /api/agents`, `POST /api/sources`, `POST /api/config`, `POST/PUT/DELETE /api/items`, `POST /api/items/:id/verdict/resolve`, `POST /api/decisions`, and the 3 ingestion handlers (`/api/sources/upload`, `/upload-file`, `/api/ingest/resolve`) | Rewritten from in-memory mutation + `saveStore()` to targeted SQL via the repository. |
| Read-only paths: `GET /api/state`, `/api/ask`, `/api/author`, `/api/deprecate`, `mockAnalysis`, `performVerdictAnalysis`, `getGeminiClient` | **Untouched logic** — they take a `ProjectRecord`-shaped snapshot; the repo provides `getProject(id)` returning exactly that. `/api/projects` uses `COUNT(*)` instead of loading arrays. |
| `client/data/database.json` (git-tracked) | Becomes the **seed/import source** only; never written again → `git status` stops churning. |
| Build: `esbuild ... --packages=external` | Native module stays external — no bundling change. |
| `.gitignore` | Add `client/data/nexus.db`, `-wal`, `-shm`. |
| Docs: `CLAUDE.md` repo-layout line ("Express + JSON-file mock"), master plan §3 | Reworded after build. |

**Data-loss trap to avoid:** the working-tree `database.json` has an uncommitted project
(`test`, created 2026-09-24T18:46) that exists nowhere else. The importer must read the file **on
disk**; never `git checkout` that file before the import runs (earlier sessions did this
routinely to clear test churn). Back it up to the scratchpad first.

## Design

- **Library:** `better-sqlite3` (synchronous API — matches this file's synchronous style, so no
  async refactor of ~15 handlers). **Pinned to v12.11.1, not v13** — see "As built" below: v13's
  prebuilt binary segfaults on Node 23.3.0. Fallback if the native module can't work:
  built-in `node:sqlite` (works here but needs `--experimental-sqlite` threaded through
  `dev`/`start`; rejected as the default — flag + "experimental").
- **File:** `client/data/nexus.db` (override with `NEXUS_DB_PATH`, tests use `:memory:`).
  Pragmas: `journal_mode=WAL`, `foreign_keys=ON`.
- **Migrations:** ordered SQL strings applied via `PRAGMA user_version` — schema versioned in
  git (same principle as Alembic on the Python side), no extra dependency.
- **Schema** (per-project integer ids are preserved — `(project_id, id)` is unique, not `id`
  alone; an explicit `seq` column preserves insertion order, which the JSON arrays gave for free):
  - `projects(seq PK AUTOINC, id TEXT UNIQUE, name, created_at)`
  - `items(seq, project_id FK CASCADE, id INT, title, description, status, priority, assignee,
    area, created_at, source_json NULL, verdict_json NULL, UNIQUE(project_id,id))`
  - `decisions(seq, project_id FK CASCADE, id INT, title, description, date, area, created_by,
    source_snippet NULL, UNIQUE(project_id,id))`
  - `sources(seq, project_id FK CASCADE, id TEXT, name, type, status, last_synced NULL,
    pending_count, UNIQUE(project_id,id))`
  - `ingest_queue(seq, project_id FK CASCADE, id TEXT, title, description, area, priority,
    source_id, source_snippet, verdict_json, UNIQUE(project_id,id))` — `source_id` is a plain
    string (Python-side ids live in Postgres; no FK).
  - `agents(seq, id TEXT UNIQUE, name, kind, description NULL, builtin INT)`
  - `api_config(id INT PK CHECK(id=1), provider, provider_type, api_key, region,
    embeddings_provider, embeddings_key, no_retention INT, isolate_tenant INT)`
  - `Item.source`, `Item.verdict`, `IngestItem.verdict` stay **JSON text columns** — opaque
    blobs the UI renders; P5 will redefine verdicts, so normalizing them now is wasted work.
    Status/priority/kind are plain TEXT (no CHECK) so existing rows can never be rejected.
- **Id semantics preserved exactly:** items = `MAX(id)+1` per project, starting at 100;
  decisions = `MAX(id)+1`, starting at 1 (including the existing reuse-after-delete quirk —
  behaviour-preserving, not a fix). Allocation + insert run in one transaction.
- **Boot:** open DB → run migrations → if no projects: import `data/database.json` (handles both
  formats `initializeStore` handles today: multi-project and legacy single-`DBState`), else seed
  the built-in fresh store (`seedSlice()` moves to `db/seed.ts`). Import is one transaction and
  **fails loudly** (naming the offending ids) on duplicate ids rather than silently dropping
  rows. Reset = delete `nexus.db`, restart → re-imports the seed.
- **Fire-and-forget verdict writes** become `UPDATE items SET verdict_json=? WHERE project_id=?
  AND id=?` — a deleted-meanwhile item is a 0-row no-op (today's `findIndex` guard, for free).

### Intentional behaviour deltas (the only ones)
1. `POST /api/config` whitelists the 8 known `apiConfig` fields. Today it spreads *any* body key
   into the stored config. (Also: the BYOK `apiKey` now lives in a gitignored DB instead of a
   git-tracked JSON file — strictly safer; encrypting it at rest is out of scope.)
2. `database.json` is no longer written.

## Implementation steps

1. **Safety + golden capture (before touching code):** copy `database.json` to the scratchpad;
   with the *current* server running, save `GET /api/projects` and `GET /api/state?projectId=…`
   for every project as golden JSON.
2. `npm i better-sqlite3 && npm i -D @types/better-sqlite3`; confirm the native module loads on
   this Node (else switch to the `node:sqlite` fallback and document it). *(Tests use Node's
   built-in `node:test` through the already-installed `tsx` — no vitest, zero new test deps.)*
3. `client/db/`: `index.ts` (open + pragmas + migrate), `migrations.ts`, `repo.ts` (typed
   functions per entity; `getProject()` snapshot), `import-json.ts`, `seed.ts`.
4. Rewrite the mutating handlers in `server.ts` to call the repo; delete `Store`, `store`,
   `initializeStore`, `saveStore`, `DB_FILE`; keep read-only logic as-is on snapshots.
5. `.gitignore`; scripts (`"test": "vitest run"`); tsconfig `include` check.
6. Docs: CLAUDE.md layout line, master plan §3/§4 status — then `nexus-log`.

## Verification

- **Unit (`node:test` via tsx, `:memory:`):** id allocation (100/1 starts, max+1, reuse-after-delete), JSON
  round-trip incl. `null` vs missing `source`/`verdict`, insertion-order preservation, project
  cascade delete, importer on both JSON formats + duplicate-id failure, agent `builtin` bool
  round-trip, `api_config` whitelist.
- **Parity vs golden:** boot fresh (no `nexus.db`) → importer → `GET /api/state` for every
  project deep-equals the step-1 golden capture. Normalize only missing↔`null` on
  `item.source`/`item.verdict` and list any other diff explicitly instead of hiding it.
- **Every mutating route via curl**, reading state back each time: create/update/delete item,
  verdict resolve (dismiss/merge/supersede/confirm), create decision, create/delete project,
  add/delete agent (built-in delete → 400), connect source, update config, ingestion upload
  (502 path with backend down; success path once Vertex quota allows) and resolve 404.
- **Durability:** restart the server → data persists; `git status` shows `database.json`
  untouched.
- `npx tsc --noEmit` clean; `npm run build` still produces `dist/server.cjs` and `npm start`
  boots it (native module external); Python `poetry run pytest` still 23/23 and the ingestion
  verdict call to `/api/state` still works; browser walkthrough through the preview pane.

## Out of scope

Moving this data into `backend/`/Postgres; any API contract change; the ingestion tables in
Postgres; encrypting `apiKey`; normalizing verdict/source JSON; auth; frontend changes.

---

## As built (2026-09-25) — where reality differed from the plan above

- **`better-sqlite3` is v12.11.1, not v13.** v13.0.3's prebuilt darwin-arm64 binary loads but
  **segfaults (exit 139) on `new Database()` under Node 23.3.0**. Compiling from source can't work
  in this checkout either: the project path contains a space (`Personal Projects`) and node-gyp
  doesn't quote its include paths (`clang++: no such file: 'Projects/unicorn/...'`). v12.x declares
  support for Node 20/22/23/24 and works. Bumping to v13 needs a newer Node (or a path without
  spaces) — recheck when Node is upgraded.
- **Tests:** Node's built-in `node:test` through the existing `tsx`, not vitest (37 tests,
  `npm test`).
- **Added a `meta` table** with a `bootstrapped` flag. The plan said "if no projects: import", but
  that would resurrect the seed after a user deletes every project; the flag distinguishes "fresh
  database" from "emptied database".
- **Approve-from-queue is one atomic repo method** (`approveIngestItem`): card created + queue
  entry removed in a single transaction.
- **Two more intentional behaviour deltas** beyond the two planned (the first is asserted
  by the differential test; the second is code-reading only — the test excludes that field): `PUT /api/items/:id` now only accepts Item fields and can no longer rewrite
  `id` (the JSON store spread any request-body key into the item, including `id`); and
  `POST /api/items/:id/verdict/resolve` with `merge` now returns `item: null` for the deleted item
  — the old code returned the *neighbouring* item (an off-by-one after `splice`). The UI ignores
  that field.
- **`PORT` is now `process.env.PORT || 3000`** so a second server can run beside the first.
- **Fire-and-forget verdict promises now have a `.catch`** — an unhandled rejection from a DB
  error would otherwise crash Node.

### Verification actually run
- **Differential test:** the *old* JSON-backed code (from git HEAD) and the new SQLite code, both
  fully isolated from the user's data, driven with the identical scripted sequence — **66 compared
  request steps, all identical** (status + body + resulting state), covering projects, decisions,
  items (incl. the 1.5 s background verdict analysis), verdict resolve (all 4 actions), sources,
  agents, config, `/api/ask|author|deprecate`, ingestion via a stub backend (upload, approve,
  dismiss, 404s, upload-file), and project cascade delete — plus the 2 intentional deltas checked
  explicitly.
- **Parity vs golden capture** of the user's real 5 projects: `GET /api/projects` and every
  `GET /api/state` **byte-identical** (no normalization needed).
- **Durability:** write → SIGTERM → restart: data intact, no re-import, WAL checkpointed to a single
  `nexus.db`, seed JSON never written.
- **Cross-stack:** the real Python `provisional_verdict` reading Node `/api/state` (SQLite) found a
  decision created there and returned a cited conflict verdict.
- `npm test` 37/37, `tsc --noEmit` clean, `npm run build` OK with the native module external and
  `node dist/server.cjs` booting + importing + serving the SPA; backend `pytest` 23/23, `ruff` clean.
- **Not done:** the browser walkthrough. The app's login form requires typed credentials, which
  I don't enter; the UI only consumes the API verified above.
