# Implementation log

A dated, narrative record of what's actually been built and verified — not a roadmap (that's
the master plan at `.claude/plans/we-want-nexus-to-sorted-shell.md`) and not a per-feature plan
(those live in `/plans/`). This is the backward-looking counterpart: what landed, when, how it
was verified, and what's still open. Appended to by the `nexus-log` skill after a feature or
phase is implemented and passes `nexus-verify` — newest entry on top.

---

## 2026-09-25 — Real database (SQLite) for the board data

**What:** `client/server.ts`'s JSON-file store (`data/database.json`: whole file loaded into memory,
mutated in place, rewritten wholesale by `saveStore()` after every change) is replaced by a real
SQLite database, per `plans/node-sqlite-store.md` (now `done`). New `client/db/`: versioned
migrations (`PRAGMA user_version`), a repository that owns every SQL statement, a first-boot
importer that reads the legacy JSON (both formats the old server accepted) or the built-in seed,
and the seed data moved out of `server.ts`. ~15 mutating handlers rewritten to targeted SQL; the
read-only AI paths (`/api/ask`, `/api/author`, verdict analysis) are untouched — they consume a
project snapshot with the same shape as before. **Zero API changes.** `database.json` is now only
the seed a fresh clone imports; it's never written again, so `git status` stops churning.
Interim by design ("sqlite for now"): moving this data into the Python/Postgres backend remains
the long-term direction.

**Deliberate behaviour changes:** `POST /api/config` and `PUT /api/items/:id` no longer persist
arbitrary request-body keys (the JSON store let a PUT rewrite an item's `id`) — both asserted
explicitly by the differential test. `merge` in verdict-resolve now returns `item: null` instead of
the *neighbouring* item (an off-by-one after `splice`) — found by reading the code; the
differential test *excludes* that one response field, so it is not independently verified
(the UI ignores it). Fire-and-forget verdict promises now have a `.catch` (a DB error there would
have been an unhandled rejection that crashes Node) — defensive, not tested. Preserved on purpose:
per-project ids (`#100`/`#1` starts, `MAX+1`, reuse-after-delete).

**Problems hit and how they were resolved:** `better-sqlite3` v13's prebuilt binary **segfaults
(exit 139) on `new Database()` under Node 23.3.0**, and compiling from source is impossible here
because the project path contains a space (`Personal Projects`) and node-gyp doesn't quote its
include paths — so it's pinned to v12.11.1 (declares Node 20–24; works). A design catch during
implementation: "import when there are no projects" would resurrect the seed after a user deletes
every project, so bootstrap is gated by a `meta` flag instead. During verification, the user's
`database.json` changed under me (new projects created on their running server), so the backup and
golden capture were refreshed, and the SQLite file my test boot created was deleted afterwards —
left in place it would have been a stale snapshot that made the user's first real boot skip the
import.

**Files:** `client/db/{index,migrations,repo,import-json,seed,types}.ts` and
`client/db/repo.test.ts` (new); `client/server.ts` (store + handlers rewritten; `PORT` now
env-overridable); `client/package.json`/`package-lock.json` (+`better-sqlite3`,
+`@types/better-sqlite3`, `npm test`); `.gitignore` (`nexus.db*`); `CLAUDE.md`;
`.claude/skills/nexus-verify/SKILL.md`; `plans/node-sqlite-store.md`.

**Verified:** **Differential test — the old JSON code (git HEAD) vs the new SQLite code, both fully
isolated, identical scripted requests: 66 compared steps all identical** (projects, decisions,
items with the 1.5 s background analysis, all four verdict-resolve actions, sources, agents,
config, ask/author/deprecate, ingestion via a stub backend, cascade delete), plus the intentional
deltas checked explicitly. Golden parity on the user's real 5 projects: `/api/projects` and every
`/api/state` byte-identical. Durability (write → SIGTERM → restart: intact, no re-import, WAL
checkpointed). Cross-stack: the real Python `provisional_verdict` read a decision from the
SQLite-backed Node and returned a cited conflict. `npm test` 37/37, `tsc` clean, `npm run build`
+ `node dist/server.cjs` boot/import/serve OK, backend `pytest` 23/23 + `ruff` clean.

**Open:** (1) **Restart your `npm run dev` on :3000** to pick this up — the process running now is
still the old JSON code; its first boot imports `database.json` (incl. `test`/`qwerty`).
(2) The **browser walkthrough was not done**: the app's login form needs typed credentials, which
I don't enter. The UI only consumes the API verified above, but a click-through is still worth doing.
(3) `apiKey`/`embeddingsKey` are stored in plaintext in the DB — gitignored now (they used to sit in
a git-tracked JSON file), but encrypting at rest is out of scope. (4) WAL mode is working on this
ExFAT volume; if it ever misbehaves, switching `journal_mode` in `db/index.ts` is the lever.
(5) Re-check `better-sqlite3` v13 after a Node upgrade.

**Commit:** _pending — see the next commit in `git log`._

---

## 2026-09-24 — Ingestion pipeline (P6), backend + frontend

**What:** The real architecture.md pipeline (parse → chunk → extract → embed → provenance),
replacing `client/server.ts`'s single-shot Gemini mock, per `plans/ingestion.md` (now
`status: done`). Backend: 5 new models (`Source`, `Chunk`, `Entity`, `DecisionRecord`,
`IngestCandidate`) + migration; `app/ingest/` (mime-aware parser — text/md/csv/PDF/images via
Claude vision; paragraph-packing token-aware chunker; forced-tool-call extractor with a
hallucination guard that drops any candidate whose citation isn't a literal substring of its
source chunk; a ported deterministic provisional verdict, calling Node's existing `/api/state`
since items/decisions haven't migrated off the JSON store yet); 4 API routes
(`/api/sources/upload`, `/api/sources/upload-file`, `/api/sources/{id}/status`,
`/api/ingest/resolve`). Frontend: `client/server.ts`'s 4 ingestion handlers now proxy to the
backend and merge the result into its own store (added `multer` for the new binary-upload
path) — the response contract the existing UI already expects is unchanged.

**Design refinement made during implementation (differs from the plan's original sketch):**
the plan assumed Node could be a dumb proxy; discovered Node's JSON store is still what
`/api/state` reads, so a background-task design would leave new candidates invisible. Fixed by
running the pipeline synchronously in the request (matching today's contract exactly, no
queue needed this pass) and having Node merge the returned candidates into its own
`ingestQueue`/`items` — see `plans/ingestion.md`'s pipeline.py docstring for the full
rationale.

**Bugs found and fixed along the way** (each caught by actually running things, not just
reading code): the chunker's `TARGET_TOKENS` flush path never reset `group_start`, which would
crash on any input needing 3+ chunks — caught by a real char-offset unit test, not inspection.
Alembic autogenerate referenced `pgvector.sqlalchemy.vector.VECTOR` without importing it
(`NameError` at migration time). The `AnthropicVertex` client from the foundations pass was
the *sync* SDK class, contradicting this project's own "async everywhere" rule — swapped for
`AsyncAnthropicVertex` (and `embed_texts` now runs its still-sync Vertex SDK call in a worker
thread). A stray AppleDouble sidecar file (`._<name>.py`, this machine's recurring ExFAT-volume
quirk) was being picked up by Alembic's directory scan as a fake migration
(`SyntaxError: null bytes`). A module-level async DB engine shared across pytest's per-test
event loops caused a real (not flaky-in-a-good-way) `RuntimeError: Future attached to a
different loop` on the 2nd+ DB-touching test — fixed with an autouse `engine.dispose()`
fixture, not by fighting pytest-asyncio's loop-scope config.

**Files:** `backend/app/models/{source,entity,decision_record,ingest_candidate}.py` (new),
`backend/migrations/versions/3e6a80f4bb8f_*.py` (new); `backend/app/ingest/{parse,chunk,extract,
verdict,pipeline}.py` (new); `backend/app/api/routes/ingestion.py` (new);
`backend/app/schemas/ingestion.py` (new); `backend/app/ai/vertex.py` (sync→async client);
`backend/app/config.py` (+`vertex_model`, `+node_server_url`); `backend/app/main.py` (router +
duplicate-operation-id fix); `backend/tests/conftest.py` (new) +
`test_ingest_{chunk,parse,extract,routes}.py` (new, 19 tests); `client/server.ts` (4 handlers
now proxy+merge); `client/package.json` (+`multer`).

**Verified:** `poetry run pytest` 23/23, `ruff check` clean, client `tsc --noEmit` clean. Full
request chain verified live with both servers actually running: upload → Node → Python → real
parse/chunk → correctly blocked at the embed step by `VertexNotConfigured` (expected — GCP
account-level setup is still the user's open item, not a code defect); confirmed zero partial
rows left in Postgres (clean transaction rollback) and `ingestQueue` uncorrupted after the
failed attempt. Resolve's 404 path verified through the full chain too.

**Open:** the account-level GCP steps (project id/region, Model Garden access, `gcloud auth
application-default login`) are still the user's to do — see the master plan §0.3. Once set,
the AI-dependent checks in `plans/ingestion.md`'s Verification section (real extraction
accuracy, embeddings, the full browser walkthrough) should be run for the first time. A
pydantic `UnsupportedFieldAttributeWarning` on `SomeModel | None` response fields is cosmetic
(verified harmless; documented in `app/schemas/ingestion.py`, not chased further). `npm audit`
flages 9 pre-existing transitive vulnerabilities in the vite/express/tailwind toolchain,
unrelated to this change — noted, not fixed here.

**Commit:** `f24894d`

---

## 2026-09-24 — Dev-standards, planning, and progress-tracking skills

**What:** Four more project skills, closing the gaps from the previous entry's foundations
pass. `nexus-frontend-standards` and `nexus-backend-standards` — this codebase's specific
conventions (component/reuse rules, the design-token system, the API-contract-lives-in-
types.ts rule, async/AI-adapter discipline, migration discipline, error handling) as a
reference while writing code, not just when scaffolding. `nexus-plan` — plans one feature at a
time: grounds it in spec + the master plan's phase status, does an impact analysis (greps
every consumer of anything the feature modifies, especially shared types/schemas, so a
contract change can't silently break a consumer), and saves the result to `plans/<slug>.md`
with `status: active` frontmatter — refuses to start a second plan while one is still active.
`nexus-log` (this skill, used to write this very entry) — records what shipped into this file
and flips the matching `plans/` entry to `done`.

**Files:** `.claude/skills/{nexus-frontend-standards,nexus-backend-standards,nexus-plan,
nexus-log}/SKILL.md` (new); `plans/README.md` (new — the one-active-plan-at-a-time convention);
`IMPLEMENTATION_LOG.md` (new, this file); `CLAUDE.md` (new "Workflow" section tying all six
skills together, plus `plans/`/`IMPLEMENTATION_LOG.md` added to "Repo layout").

**Verified:** `grep -l "^status: active" plans/*.md --exclude=README.md` — confirmed empty
(no plan blocks the first real one). Caught and fixed a real bug in the same pass: the
README's own example frontmatter block literally started a line with `status: active`, which
would have made `nexus-plan` permanently refuse to ever start a feature — fixed by excluding
`README.md` from the check and rewording the example so it can't false-match a similar grep
elsewhere.

**Open:** none — this entry is itself the first real use of `nexus-log`.

**Commit:** `1e3dd66`

## 2026-09-24 — Foundations: CLAUDE.md, project skills, GCP/Vertex AI backend

**What:** `CLAUDE.md`; the first three project skills (`nexus-verify`, `nexus-new-phase`,
`nexus-spec`); backend P0 pivoted from a direct-Anthropic-API/local-only design to GCP-native
(`AnthropicVertex` + Vertex embeddings via Application Default Credentials, Postgres+pgvector
local for dev / Cloud SQL when deployed, arq/Redis local / Cloud Tasks deployed); Alembic wired
to the app's real settings; `gcloud` CLI installed.

**Files:** `CLAUDE.md`; `.claude/skills/{nexus-verify,nexus-new-phase,nexus-spec}/SKILL.md`;
`backend/app/ai/vertex.py` (new); `backend/app/{config.py,main.py}`; `backend/pyproject.toml`;
`backend/migrations/` (new, async Alembic template); `.claude/launch.json`.

**Verified:** `pytest` 4/4, `ruff` clean; direct uvicorn+curl round-trip on `/`, `/api/health`,
`/api/health/ready` (confirms live Postgres + pgvector 0.8.6); `alembic current` connects
cleanly; `app.ai`'s `VertexNotConfigured` error tested for the not-yet-configured case.

**Open:** account-level GCP steps only the user can do (project ID/region, confirm Vertex AI
Model Garden access, `gcloud auth application-default login`); the Browser-pane preview tool
couldn't actually bind either the new backend or (on retest) the previously-working frontend
config this session — flagged as likely session-side preview-daemon state, not an app defect.

**Commit:** `b0bf4fd`

---

## 2026-09-23 — `ui_v2`: BUILD→VERIFY lifecycle screens

**What:** The app was UI-complete for the PLAN half (Board, Verdicts, Memory, Trace, Author,
Sources, Deprecate, Settings) but missing the entire BUILD→VERIFY half the current product
vision is built on. Added: nav regrouped into lifecycle phases (PLAN/BUILD/VERIFY/KNOWLEDGE,
ui_ux_design.md §3) with two triage bells (Verdicts + Reviews); **Runs** (§4.12) — live
activity stream, acceptance-criteria tracker, blocking-question prompt, self-assessment;
**Reviews** (§4.13, the co-hero) — the per-requirement coverage matrix (met/partial/unmet/
off-task, dual citations, staggered reveal, human-only approve); **Delivery** (§4.14) — PR/CI/
build/deploy with the requirement re-check that travels with the PR; run-status chips on board
cards. New screens derive deterministically from real board items (`lib/delivery.ts`) since the
backend for these phases didn't exist yet. Kept the app's established warm accent/neutral
palette rather than the spec's nominal indigo (documented tradeoff, not an oversight).

**Files:** `client/src/components/{RunsView,ReviewsView,DeliveryView,StatusBadges}.tsx` (new);
`client/src/lib/delivery.ts` (new); `client/src/types.ts`, `App.tsx`,
`context/ProjectContext.tsx`; `client/src/components/CommandBar.tsx` (follow-up fix — the ⌘K
"Go to…" list hadn't been updated for the three new screens).

**Verified:** `tsc --noEmit` clean throughout; full live browser walkthrough of every screen in
both light and dark mode (see the session's verification pass) plus a dedicated re-verification
pass after the fact confirming nothing regressed.

**Commits:** `649eda8`, `358f8fc`

---

## 2026-09-23 — Git repository initialized

**What:** The project had no git history (a nested `client/.git` existed but the top-level repo
didn't). Initialized a single top-level repo (removed the nested one — its GitHub history is
safe on `origin`), committed the existing app + `architecture.md`/`ui_ux_design.md` to `main`,
branched `ui_v2` for the UI redesign work above.

**Commit:** `6eb3931` (initial), branch `ui_v2` created from it.
