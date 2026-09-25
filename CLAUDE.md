# Nexus (aka "Alpha Auctus" internal build)

AI-native software delivery platform, built as an **internal tool**. Turns raw project
intent into provenance-linked task contracts, executes them via AI agents, and proves
completion with per-requirement evidence — not just "the tests pass."

**Read first, in order:**
1. `/ui_ux_design.md` — the UI/UX spec. Screens, flows, states, keyboard model, design
   tokens. Source of truth for anything user-facing.
2. `/architecture.md` — the plan/memory-half system architecture (ingestion, conflict/dedup
   engine, data model).
3. The active build plan at `.claude/plans/we-want-nexus-to-sorted-shell.md` — feature
   catalog, user stories, phased build order, resolved decisions, and what's actually been
   built vs. still a mock.

Don't improvise product behavior — if a screen, flow, or copy isn't covered by (1) or (2),
that's a gap to flag, not a blank to fill from taste.

## Non-negotiables (violate these and the product breaks its own thesis)
- **Cite or stay silent.** Every AI claim (verdict, answer, authored doc, requirement-
  coverage row) shows its source. No citation ⇒ say so, never assert.
- **Human is the final approver.** AI never merges, deploys, or closes a requirement on its
  own (autonomy capped at L0–L1 for this build — see the plan's resolved decisions).
- **Never silently miss, never cry wolf.** Low-confidence findings surface tinted as
  "please review," excluded from bulk actions — never auto-resolved, never dropped.
- **Ranked candidates, not single assertions.** Verdicts and coverage rows show ranked
  candidates for human confirmation.

## Repo layout
- `client/` — React 19 + TypeScript + Vite + Tailwind v4 SPA. Every screen in the spec is
  built here (`client/src/App.tsx`, `client/src/components/`). Currently talks to
  `client/server.ts` (Express) — its board data (projects, items, decisions, sources, ingest
  queue, agents, AI settings) lives in a **SQLite** database via `client/db/`; the AI paths there
  are still mocked/Gemini. Being replaced by `backend/` phase by phase.
- `backend/` — Python 3.13 + FastAPI, built phase by phase per the plan. Poetry-managed.
  AI (generation + embeddings) always goes through **Vertex AI**; local dev otherwise stays
  local (Postgres+pgvector, filesystem blobs, arq) and deployed environments go GCP-native
  (Cloud SQL, Cloud Storage, Cloud Tasks, Secret Manager, Cloud Run) — see §3 of the plan.
- `ui_ux_design.md`, `architecture.md` — the two source specs (read first, above).
- `.claude/plans/we-want-nexus-to-sorted-shell.md` — the living **master** build plan (the
  whole-platform roadmap — doesn't move).
- `plans/` — one file per **feature**, written by `nexus-plan` right before it's built. Finer
  grain than the master plan; see `plans/README.md` for the convention.
- `IMPLEMENTATION_LOG.md` — dated record of what's actually been built and verified, newest
  first. Written by `nexus-log` after a feature passes `nexus-verify`.

## Running it locally
- Frontend: `cd client && npm run dev` (or the `nexus-client` preview config in
  `.claude/launch.json`) — port 3000 (`PORT=…` overrides). The board data is a SQLite file,
  `client/data/nexus.db` (gitignored). On first boot it is populated from `client/data/
  database.json` (the legacy JSON store, kept only as the seed — never written again); to reset
  to that seed, stop the server, delete `nexus.db*`, restart. Uses `better-sqlite3` **v12** — v13
  segfaults on Node 23.3 and can't be compiled from source in a path containing a space.
- Backend: `cd backend && poetry install && poetry run uvicorn app.main:app --reload --port
  8000`. Needs local Postgres 16 with the `nexus_dev` database and the `vector` extension
  (see `backend/README.md` — pgvector was built from source on this machine since the
  Homebrew bottle only targets pg17/18).
- Vertex AI needs `gcloud auth application-default login` and a configured GCP project — see
  the plan's §0.3 checklist.

## Verifying a change
- Frontend: `cd client && npx tsc --noEmit` must be clean and `npm test` (the `client/db/`
  repository, `node:test` via tsx) must pass; drive the change in the browser preview (never run
  dev servers via bash — use the preview tools).
- Backend: `cd backend && poetry run pytest && poetry run ruff check .`
- Every phase in the plan has its own "Verification" subsection — follow it, don't invent a
  different check.

## Conventions
- **The API contract lives in `client/src/types.ts`.** New backend endpoints return shapes
  that match those types exactly, so the already-built frontend needs no rewrite (the plan's
  "Key reuse" principle).
- New backend packages under `backend/app/` follow the existing pattern: an `__init__.py`
  docstring naming which plan phase fills it in, routes registered in `main.py`, tests via
  `pytest-asyncio` + `httpx.ASGITransport` (see `backend/tests/test_health.py`).
- Active branch: `ui_v2`. For commit/PR attribution, follow whatever the current session's
  standing instruction says (it has changed mid-project — don't hardcode a line here).
- Keep the plan file in sync: when a phase's status changes (mock → real), update its row in
  the phased-plan table.

## Workflow — the project skills, and when to use them

One feature at a time, grounded in spec, with a visible record of what happened:

1. **`nexus-plan`** before starting anything non-trivial — grounds it in spec, checks it won't
   break existing consumers, confirms it's the right phase/placement, and saves the plan to
   `plans/<slug>.md`. Refuses to start a second feature while one is still `active`.
2. **`nexus-spec`** any time a requirement is unclear mid-implementation — don't improvise.
3. **`nexus-frontend-standards`** / **`nexus-backend-standards`** while writing code in
   `client/` / `backend/` — this project's specific conventions (reuse, the API-contract rule,
   design tokens, async/AI-adapter discipline, error handling, tests).
4. **`nexus-new-phase`** specifically when starting a new backend phase's scaffolding
   (models/schemas/routes/tests skeleton).
5. **`nexus-verify`** before considering any change done.
6. **`nexus-log`** after `nexus-verify` passes — records the outcome in
   `IMPLEMENTATION_LOG.md` and flips the matching `plans/` file to `done`, which is what
   allows the next `nexus-plan` to proceed.
