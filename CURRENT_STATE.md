# Current state

Snapshot of Nexus as of 2026-09-27. Written from the repo (plans, implementation log, and the code that actually runs). Not a roadmap.

**Status words used below**

- **real** — persists or calls the live path (Node SQLite and/or FastAPI + Vertex).
- **partial** — UI and some real data; leftover mock, canned copy, or a missing backend piece.
- **mock** — seeded, hardcoded, or Node Gemini/canned demo. Looks like the spec screen; does not execute the product thesis.

---

## 1. What it is

Nexus (internal name Alpha Auctus) is an internal AI-native delivery tool: raw project intent (docs + a board) becomes cited features and task contracts, humans approve, and completion is supposed to be proven per requirement. The UI is a React SPA. Board/projects live in Node + SQLite. Document → features → clarification → tasks and the cited AI paths live in FastAPI + Postgres + LangGraph + Gemini on Vertex. Autonomy is L0–L1: the human is the final approver.

**Cite or stay silent** applies to the FastAPI AI routes (verdict, item Ask, Memory, Author, Trace explain): no citation ⇒ no assertion; fabricated decision ids are dropped. Node leftover `/api/ask` and `/api/author` do not follow that rule.

---

## 2. How to run it

From `CLAUDE.md`. Do not invent other ports or services.

**Frontend** (port **3000**; `PORT=…` overrides)

```bash
cd client && npm run dev
```

Or the `nexus-client` preview in `.claude/launch.json`. Board data is `client/data/nexus.db` (gitignored). First boot imports `client/data/database.json` (seed only — never written again). Reset: stop the server, delete `nexus.db*`, restart. `better-sqlite3` is pinned to **v12** (v13 segfaults on Node 23.3).

**Backend** (port **8000**)

```bash
cd backend && poetry install && poetry run uvicorn app.main:app --reload --port 8000
```

Needs local **Postgres 16**, database **`nexus_dev`**, and the **`vector`** extension (`backend/README.md`). Apply Alembic migrations (`alembic upgrade head`) or MVP routes 500 on missing columns.

**Vertex**

```bash
gcloud auth application-default login
```

Set `GCP_PROJECT_ID` in `backend/.env` (see `backend/.env.example`). Gemini is reached only through `backend/app/agents/llm.py` (LangChain). Empty project id → structured 4xx `{problem, cause, fix}`.

The browser talks to Node at same-origin `/api/…` (board) and to FastAPI at `VITE_BACKEND_URL` (default `http://localhost:8000`) for MVP routes. CORS allows `http://localhost:3000`.

**Health:** `GET /api/health` (liveness), `GET /api/health/ready` (Postgres + pgvector).

---

## 3. Two stores (read this before the inventory)

| Store | Process | Owns |
| --- | --- | --- |
| SQLite `client/data/nexus.db` | Express `client/server.ts` | Projects, board items, verdict resolve, decisions (manual rows), connector rows, agents, BYOK config, leftover ingest queue |
| Postgres `nexus_dev` | FastAPI `backend/app/main.py` | Documents, features, questions, generated tasks, chat/workflow history, audit; LangGraph checkpointer |

Deleting a project on Node does **not** delete that project’s Postgres documents/features.

---

## 4. Feature inventory

Nav groups follow `ui_ux_design.md` §3 as implemented in `client/src/App.tsx` (plus Chat and Features, which are approved spec gaps).

### Login / session — **partial** (guest-login in tree; plan still active)

Unspec’d gate (`ui_ux_design.md` has no login page). Sign in / Sign up ignore the password; they only stamp a local profile.

- **Log in as guest** is in the tree: `client/src/components/LandingPage.tsx`, `client/src/lib/session.ts`, `client/src/App.tsx`. Guest → `localStorage` `nexus-session` + `nexus-authed=1`; sidebar shows “Guest”; Log out clears both.
- Sign in with email stores `kind: 'user'` and shows that email. **No users table, no password check, no FastAPI auth.**
- `plans/guest-login.md` is still **`status: active`** (sibling may still be finishing or verifying). Treat as landed-in-tree, not closed.

### Projects — **real** (Node)

List / create / delete / switch. First run with no projects opens guided setup.

- UI: `client/src/components/ProjectsView.tsx`, `ProjectSwitcher.tsx`
- API: Node `GET/POST /api/projects`, `DELETE /api/projects/:id`, `GET /api/state`
- Context: `client/src/context/ProjectContext.tsx`

### New Project setup — **partial**

Full-screen takeover (`ui_ux_design.md` §4.10). Name + description + optional PDF/DOCX/MD. Then lands on **Chat** (fake clarification Q&A skipped). Brief is uploaded as Markdown into the real ingest pipeline. Video / image / GitHub fields are listed by name only (not ingested).

- UI: `client/src/components/NewProjectSetup.tsx`
- Leftover unused: `client/src/components/ClarificationChat.tsx`

### Chat / workflow — **real** (FastAPI + LangGraph)

Drives ingest → feature review → task generation → **Add N to board**. Approve disabled (API **409**) while a feature has open questions. Skip-remaining is a human action, never an auto-answer. Reject excludes a feature from task generation. Sources / Features / Board stay as inspection.

- UI: `ProjectChat.tsx`, `ChatBlocks.tsx`, `FeatureCards.tsx`, `WorkflowStepper.tsx`, `client/src/lib/workflow.ts`
- FastAPI: `GET /api/projects/{id}/workflow`, `GET …/clarification`, `POST …/clarification/{answer,skip,skip-remaining}`, `PATCH …/features/{id}`, `POST …/features/{id}/tasks/generate`, `PATCH …/tasks/{id}`
- Graphs: `backend/app/agents/graphs/{document,clarification,tasks}.py`
- Plan: `plans/chat-workflow.md` (`done`)

Agents (Extractor, Merger, Analyst, Clarifier, Planner/Reviewer) run in-process; startup recovery marks stuck documents `failed`.

### Sources — **partial**

File upload to FastAPI is **real** (PDF / DOCX / MD → convert / split / extract). Connector tiles (Sheet, transcripts, email, Jira) only write a SQLite row (`POST /api/sources`) — no real sync. Node `POST /api/sources/upload` (canned SSO extract) is unused by the client.

- UI: `SourcesView` in `client/src/App.tsx`
- FastAPI: `POST/GET /api/projects/{id}/documents`, `GET …/documents/{id}`, `GET …/documents/{id}/markdown`
- Client: `client/src/lib/backend.ts` (`uploadDocument`, `listDocuments`, …)

### Features — **real** (inspection; review happens in Chat)

Approved spec gap (not in the written nav map). Lists extracted features, optional clarify sheet, **Add all approved** → Node `POST /api/items`.

- UI: `client/src/components/FeaturesView.tsx`, `FeatureClarification.tsx`
- FastAPI: `GET /api/projects/{id}/features`, `GET/PATCH …/features/{id}`, `GET …/features/{id}/activity`

### Board — **real** (SQLite) + **real** verdict check (FastAPI)

Kanban (inbox / next / in_progress / done). Inline add, drag between columns, card drawer. Create/edit is spreadsheet-fast; verdict is computed after persist. Run chips on cards are **mock** (see Runs).

- UI: `DashboardView` in `App.tsx`; drawer `client/src/components/Drawer.tsx`
- Node: `POST/PUT/DELETE /api/items`
- FastAPI: `POST /api/projects/{id}/verdicts/check` (`backend/app/agents/verdict.py`)
- Missing Vertex → toast, fallback `net-new`

### Card drawer — **partial**

Tabs: Overview, Ask AI, Impact, History, Citations. Spec also has Run / Review tabs; those are not here.

| Tab | Status | Notes |
| --- | --- | --- |
| Overview | **real** | Title/description/status persist via Node |
| Ask AI | **real** | `POST /api/projects/{id}/ask` — cited, item-scoped; does not write `chat_messages` |
| Impact | **partial** | Verdict candidates if present; leftover Dec #4 copy |
| History | **mock** | Hardcoded “June 2, 2026” trail |
| Citations | **partial** | Shows `verdict.citation` when present |

### Verdicts inbox — **partial**

Lists board cards whose verdict is not `net-new`. Classify-on-add is FastAPI. Confirm / dismiss / merge / supersede is Node `POST /api/items/:id/verdict/resolve`. Architecture **Decision Records** (normalized statements + vector retrieval) are **not built**; Settings can insert manual SQLite decision rows.

- UI: `VerdictsView` + `VerdictRow.tsx`
- Plan: `plans/manual-add-verdict.md` (`done`)

### Runs (stage 12) — **mock**

`buildRuns()` in `client/src/lib/delivery.ts` seeds activity from item ids. Stop / answer toast only. No agent runner.

- UI: `client/src/components/RunsView.tsx`

### Reviews (stage 13) — **mock**

`buildReviews()` same file. Coverage matrix and row actions are seeded. Count badge is derived, not a real queue.

- UI: `client/src/components/ReviewsView.tsx`

### Delivery (stage 14) — **mock**

`buildDeliveries()`: fake PRs, CI pills, “Open in GH” toast. Stage 15 (run → PR → deploy on Trace) is out of scope.

- UI: `client/src/components/DeliveryView.tsx`

### Memory / Ask — **real** (FastAPI)

Project-level ask over ready document markdown, features/tasks, and a client board snapshot. CmdK “Ask…” opens this view and submits. Turns are not persisted.

- UI: `AskView` in `App.tsx`
- FastAPI: `POST /api/projects/{id}/memory/ask` (`backend/app/agents/memory.py`)
- Node `POST /api/ask` (SSO/CSV canned + optional Gemini) is **unused** by the SPA, **not deleted**
- Plan: `plans/project-memory-ask.md` (`done`)

### Trace — **partial** (graph **real** client-side; explain **real** FastAPI)

Nodes/edges from board cards, areas, SQLite decisions, features/tasks, verdicts. Click fills Selected Impact Explanation; **Explain this impact** calls FastAPI on the supplied subgraph only.

- UI: `client/src/components/ImpactGraph.tsx`, `client/src/lib/impactGraph.ts`
- FastAPI: `POST /api/projects/{id}/impact/explain` (`backend/app/agents/impact.py`)
- No persisted `Edge` table, no Qdrant
- Plan: `plans/trace-impact-graph.md` (`done`)

### Author — **real** (FastAPI; in-memory draft)

BRD / tech spec / task tree from scoped features, tasks, passages, board/decisions. Area list is live slugs + All. No streaming, no PDF, no saved draft.

- UI: `AuthorView` in `App.tsx`
- FastAPI: `POST /api/projects/{id}/author` (`backend/app/agents/author.py`)
- Node `POST /api/author` unused, not deleted
- Plan: `plans/author-documents.md` (`done`)

### Deprecate — **mock**

Hardcoded SSO/CSV-style suggestions. Retire / Snooze only toast and drop the row locally.

- UI: `DeprecateView` in `App.tsx`
- Node: `POST /api/deprecate` (**still called**)

### Settings — **partial**

Manual decision rows and agent CRUD persist in SQLite. BYOK / no-retention UI writes Node `POST /api/config` (plaintext keys). **FastAPI AI does not use this key** — it uses Vertex ADC + `GCP_PROJECT_ID`. Members, GitHub, audit log as specified are not real.

- UI: `SettingsView` in `App.tsx`
- Node: `POST /api/config`, `POST /api/decisions`, `POST/DELETE /api/agents`

### Command bar (⌘K) — **partial**

Nav shortcuts and card search are real. Ask jumps to Memory (FastAPI). Create card uses real `addItem`.

- UI: `client/src/components/CommandBar.tsx`

---

## 5. What FastAPI actually serves

Router: `backend/app/api/routes/mvp.py` under `/api`. Prefix + health: `backend/app/main.py`, `backend/app/api/routes/health.py`.

| Method | Path | Role |
| --- | --- | --- |
| GET | `/api/health`, `/api/health/ready` | Liveness / Postgres + pgvector |
| POST/GET | `/api/projects/{id}/documents` | Upload (202) + list |
| GET | `…/documents/{id}`, `…/markdown` | Status / converted text |
| GET/PATCH | `…/features`, `…/features/{id}` | Registry + review_status |
| GET | `…/features/{id}/activity` | Audit rows |
| POST | `…/features/{id}/tasks/generate` | Start task graph (202); 409 if rejected |
| GET | `…/clarification`, `…/workflow` | Interrupt + full chat history |
| POST | `…/clarification/answer`, `/skip`, `/skip-remaining` | Human answers / skips |
| PATCH | `…/tasks/{id}` | draft / approved / on_board + boardItemId |
| POST | `…/ask` | Drawer Ask |
| POST | `…/memory/ask` | Memory nav |
| POST | `…/impact/explain` | Trace explain |
| POST | `…/author` | BRD / spec / tree |
| POST | `…/verdicts/check` | Manual add/edit classify |

Errors on these routes: `{"detail": {"problem", "cause", "fix"}}`.

---

## 6. What Node still mocks or still owns

`client/server.ts` — still the board API.

**Still used (real SQLite unless noted)**

- `/api/projects`, `/api/state`, `/api/items`, `/api/items/:id/verdict/resolve`
- `/api/decisions`, `/api/agents`, `/api/config`, `/api/sources` (connector row only)
- `/api/ingest/resolve` (legacy SQLite ingest queue)
- **`POST /api/deprecate` — canned suggestions (mock, still wired)**

**Unused by the SPA, not deleted**

- **`POST /api/ask`** — SSO/auth/CSV canned answers + optional Gemini
- **`POST /api/author`** — canned BRD/spec/tree
- **`POST /api/sources/upload`** — one Gemini call or canned “Add custom database-backed SSO…”

Create/edit no longer call Node `analyseInBackground` (that path would overwrite the FastAPI verdict).

---

## 7. Plans

**Active (one allowed):** `plans/guest-login.md` — guest button / local identity. Code is already in the tree; plan not flipped to `done`.

**Done:** `mvp-v0`, `chat-workflow`, `manual-add-verdict`, `task-ask-ai`, `project-memory-ask`, `trace-impact-graph`, `author-documents`, `node-sqlite-store`, `ingestion` (P6 pipeline **superseded** by MVP v0; Qdrant/arq/Redis removed).

**Draft (not started as written):** `feature-pipeline-contract.md`, `FEATURE_REGISTRY.md`, `Devevloper_tasks_factory.md`. MVP v0 + chat-workflow cover a presentation-sized slice of that pipeline, not those drafts as specified (no Qdrant registry matching).

Master roadmap `.claude/plans/we-want-nexus-to-sorted-shell.md` is **missing from this workspace**. Dated narrative: `IMPLEMENTATION_LOG.md`.

---

## 8. Known gaps

- **No real user accounts.** Guest / Sign in are localStorage only. Guest-login plan still `active`.
- **Decision Records** (architecture.md hybrid memory + vector retrieval) are not implemented. Manual SQLite decisions exist; FastAPI drops invented decision cites.
- **Qdrant / embeddings retrieval** removed with P6; not restored.
- **Stages 12–15 mocked:** Runs, Reviews, Delivery, and Trace “run → PR → deploy”.
- **Browser-unverified** in recent log entries: Chat create → ingest → Add N; Trace click/Explain; live Vertex/Docling three-file demo (`plans/mvp-v0-demo.md` not written). Guest-login plan still asks for a browser pass.
- Author: no stream, PDF, or persisted draft. Memory: no persisted threads.
- Dual store: Node project delete does not cascade Postgres. Project ids must match `^[A-Za-z0-9_-]{1,128}$` for FastAPI.
- Settings BYOK does not drive Vertex. Sidebar “zero-retention / tenant isolated” is copy, not enforcement.
- Leftovers: `ClarificationChat.tsx`; Node `/api/ask`, `/api/author`, `/api/sources/upload`.
- New Project video/image/GitHub not ingested. Connector catalog is a stub.
- Drawer History is fake; Impact tab still mentions Dec #4.
- Confidence below 70 still surfaces (never dropped). Nothing auto-merges or auto-closes a requirement.

---

## 9. Non-negotiables (product thesis)

From `CLAUDE.md` — the FastAPI AI paths are written to these; the mocked Build/Verify screens are not:

1. Cite or stay silent.
2. Human is the final approver.
3. Never silently miss, never cry wolf (low confidence stays visible, excluded from bulk).
4. Ranked candidates, not a single assertion (verdicts).
