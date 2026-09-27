# Alpha Auctus: Technical Description

**Fix It Forward with Claude, D3 2026 Hackathon, Big Build submission (deliverable #3)**

Alpha Auctus is an AI-native software delivery tool. It takes
raw project intent, such as a spec, meeting notes or a brief, and turns it into cited features.
A PM clarifies those features in a chat, and the tool generates reviewed task drafts from them.
The drafts go onto a delivery board. Every AI claim links back to the source passage it came
from, and a human approves every step.

| Deliverable | Value |
| --- | --- |
| Hosted prototype | _TBD: add the demo URL before the deadline (28 Sep 2026, 09:00 IST)_ |
| Git repository | _TBD: add the repo URL (no remote is configured in the local checkout yet)_ |
| This document | Architecture · tech stack · tools and integrations · setup and run · test datasets |

---

## 1. What the prototype does (end-to-end flow)

```
Upload spec (PDF / DOCX / MD)
   │
   ▼
① Convert → split → extract features → merge duplicates → analyse each feature
   │        (every requirement carries a verbatim source quote, which code checks against the document)
   ▼
② Clarification chat: the AI asks the PM targeted questions per feature
   │        (it pauses for the human and never auto-answers)
   ▼
③ PM approves or rejects features (Approve is blocked while questions are still open)
   │
   ▼
④ Task generation: Planner drafts 3–10 tasks, Reviewer critiques them (one retry)
   │        (each task traces to a requirement or a PM answer)
   ▼
⑤ "Add N to board": approved tasks become Kanban cards
   │
   ▼
⑥ On every card add/edit: cited duplicate/conflict verdict against the board and draft tasks
   Plus: Memory Q&A · card-level Ask AI · Trace impact graph + explain · Author BRD/spec/task tree
```

### Design rules the code enforces

| Principle | How it is enforced |
| --- | --- |
| **Cite or stay silent** | Agents must return source quotes. A deterministic `verify_citations` node (`backend/app/ingest/cite.py`) drops any quote it can't find in the document. Answers with no citation are refused. Decision IDs the model invents are removed. |
| **Human is the final approver** | Autonomy is capped at L0–L1. The clarification graph blocks on LangGraph `interrupt()` until the PM acts. Approving a feature with open questions returns HTTP 409. Nothing auto-merges, auto-deploys or auto-closes a requirement. |
| **Never silently miss, never cry wolf** | Low-confidence results stay visible and tinted "please review". They are left out of bulk actions and never dropped. |
| **Ranked candidates, not single assertions** | Verdicts return ranked, cited candidates for a human to confirm, dismiss, merge or supersede. |
| **The LLM proposes, code verifies and writes** | Convert, split, citation checks, persistence and question scheduling are all deterministic nodes. The Clarifier can only write to the DB through typed tools. |

---

## 2. Architecture

```
┌──────────────────────────────── Browser ────────────────────────────────┐
│  React 19 SPA (Vite, Tailwind v4)                                       │
│  Projects · Chat/Workflow · Sources · Features · Board · Verdicts ·     │
│  Memory · Trace · Author · Settings · ⌘K command bar                    │
└──────────────┬──────────────────────────────────────┬───────────────────┘
               │ same-origin /api/*                   │ VITE_BACKEND_URL (:8000)
               ▼                                      ▼
┌──────────────────────────────┐   ┌──────────────────────────────────────────────┐
│ Node / Express  (:3000)      │   │ Python FastAPI  (:8000)                      │
│ client/server.ts             │   │ backend/app/main.py → api/routes/mvp.py      │
│  • serves the SPA (Vite)     │   │                                              │
│  • board API: projects,      │   │  LangGraph graphs (in-process asyncio tasks) │
│    items, verdict resolve,   │   │   document_graph      (one run per upload)   │
│    decisions, agents, config │   │   clarification_graph (one per project)      │
│                              │   │   task_graph          (one per feature)      │
│  SQLite (better-sqlite3 v12) │   │                                              │
│  client/data/nexus.db        │   │  Single-shot cited agents: verdict, ask,     │
└──────────────────────────────┘   │   memory ask, impact explain, author         │
                                   │                                              │
                                   │  agents/llm.py ── the only model factory ──┐ │
                                   │  Postgres 16: app tables + LangGraph        │ │
                                   │   checkpoints + audit_events                │ │
                                   └─────────────────────────────────────────────┼─┘
                                                                                 ▼
                                                    Gemini 2.5 Pro on Google Vertex AI
                                                    (LangChain ChatGoogleGenerativeAI,
                                                     vertexai=True, ADC auth, no API key)
```

### 2.1 Two stores

| Store | Owned by | Contents |
| --- | --- | --- |
| **SQLite** `client/data/nexus.db` | Express `client/server.ts` | Projects, board items, verdict resolutions, manual decision rows, connector rows, agent registry, model config |
| **Postgres** `nexus_dev` | FastAPI | `documents`, `features`, `feature_questions`, `chat_messages`, `tasks`, `audit_events`, plus LangGraph checkpoints so paused chats survive restarts. Schema is managed by Alembic (`backend/migrations/`). |

The board runs on Node + SQLite. The AI pipeline is being moved to FastAPI one phase at a time.
The shared API contract is `client/src/types.ts`, and every FastAPI response matches those types
exactly, so the frontend didn't have to be rewritten.

### 2.2 LangGraph graphs and agents (`backend/app/agents/`)

| Graph | Nodes (★ = LLM agent) |
| --- | --- |
| `document_graph` (thread `doc:{id}`) | `convert` (Docling / python-docx) → `split` → ★ **Feature Extractor** (per chunk) → ★ **Feature Merger** → fan-out `Send` per feature → ★ **Feature Analyst** → `verify_citations` → `persist` |
| `clarification_graph` (thread `clarify:{project}`) | `next_question` → `interrupt()` (waits for the PM) → ★ **Clarifier** → loop |
| `task_graph` (thread `tasks:{feature}`) | ★ **Task Planner** → ★ **Task Reviewer** (critic, sends back to the Planner at most once) → `persist_drafts` |

- **Feature Extractor / Merger:** structured-output agents that return `{name, summary, source_quotes[]}`.
- **Feature Analyst:** a ReAct agent with read-only tools (`search_document`, `read_section`,
  `list_sections`). It produces requirements, Given/When/Then acceptance criteria, constraints,
  dependencies, out-of-scope items and up to 5 questions. Tool use is capped at 8 steps.
- **Clarifier:** a ReAct agent. Its only way to write is through the `update_feature_field`,
  `ask_follow_up` (max 2 per feature) and `mark_resolved` tools, and each value it writes is
  cited as a PM answer.
- **Task Planner / Reviewer:** the Planner writes tasks with area, priority (P0–P3), estimate
  (S/M/L), acceptance criteria and `traces_to`. The Reviewer rejects any task that is
  untraceable, has AC that can't be tested, or invents scope.
- **Single-shot cited agents:** `verdict.py` (duplicate/conflict/net-new with ranked
  candidates), `ask.py` (card-scoped Q&A), `memory.py` (project Q&A), `impact.py` (Trace
  subgraph explanation), `author.py` (BRD / tech spec / task tree).

**Runtime behaviour:** a semaphore limits concurrent Analyst runs (default 4). Every node
writes the document's status and progress. On startup, any document that was left mid-run is
marked `failed` with a message to re-upload it. Errors come back as
`{"detail": {"problem", "cause", "fix"}}`.

### 2.3 FastAPI surface (`/api/projects/{id}/…`)

`documents` (upload 202 / list / status / markdown) · `features` (list / get / PATCH review
status / activity) · `features/{id}/tasks/generate` · `tasks/{id}` (PATCH) · `workflow` ·
`clarification` (+ `answer`, `skip`, `skip-remaining`) · `ask` · `memory/ask` ·
`impact/explain` · `author` · `verdicts/check` · plus `GET /api/health` and `/api/health/ready`.

### 2.4 Path to production (technical feasibility)

This is how the prototype would be deployed beyond the hackathon:

| Local dev (today) | Deployed target (GCP-native) |
| --- | --- |
| Local Postgres 16 | Cloud SQL for Postgres |
| Filesystem blobs `backend/data/blobs` | Cloud Storage |
| In-process `asyncio` graph runs | Cloud Tasks → Cloud Run workers (dependencies already in `pyproject.toml`) |
| `.env` + `gcloud` ADC | Secret Manager + service-account identity |
| Uvicorn / Express | Cloud Run services |

LangGraph checkpoints are stored in Postgres, which keeps the graph runs stateless, so they
scale horizontally. The model is created in exactly one place (`agents/llm.py`), so changing
the model or provider is a one-file change.

---

## 3. Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript 5.8, Vite 6, Tailwind CSS v4, `motion`, `lucide-react`, `react-markdown` |
| Board API | Node.js, Express 4, `tsx`, `better-sqlite3` v12 (SQLite, WAL) |
| AI backend | Python 3.13, FastAPI 0.115, Uvicorn, Pydantic v2 / pydantic-settings, Poetry |
| Orchestration | LangGraph 1.x (`StateGraph`, `Send` fan-out, `interrupt()` / `Command(resume=…)`, `create_react_agent`), `langgraph-checkpoint-postgres` |
| LLM | Gemini 2.5 Pro via **Vertex AI**, through LangChain (`langchain-google-genai` with `vertexai=True`; `langchain-google-vertexai` as a fallback) |
| Data | PostgreSQL 16 (+ pgvector extension; readiness probe), SQLAlchemy 2 async + asyncpg, psycopg 3, Alembic |
| Document parsing | Docling (PDF/DOCX layout-aware → Markdown), python-docx |
| Testing / quality | pytest + pytest-asyncio + httpx `ASGITransport`, ruff; `node:test` via tsx; `tsc --noEmit` |

---

## 4. Tools and integrations

### 4.1 Real integrations
- **Google Vertex AI (Gemini 2.5 Pro):** all generation. Auth uses Application Default
  Credentials, so no API key is stored anywhere. With no project configured, the backend
  returns an actionable 4xx error instead of crashing.
- **Docling:** converts uploaded PDF/DOCX files to Markdown.
- **PostgreSQL + LangGraph checkpointer:** stores paused clarification threads, so they
  survive a server restart.

### 4.2 Mocked external systems (per guideline §3: no live production systems)

| System | Status in prototype | How the real integration would work |
| --- | --- | --- |
| Source connectors (Google Sheet, meeting transcripts, email, Jira) | Tiles only write a connector row (`POST /api/sources`). There is no sync. | Each connector pulls documents into the same `POST …/documents` pipeline, so everything after upload is unchanged. |
| Agent runs (Runs view) | Seeded activity (`client/src/lib/delivery.ts`) | A sandboxed coding agent (Claude Code) runs against an approved task contract and streams activity over WebSocket (`backend/app/runner`, `ws`, `mcp` are scaffolded). |
| Requirement coverage review (Reviews view) | Seeded coverage matrix | For each acceptance criterion, ranked evidence candidates (tests, diff hunks) that a human confirms |
| GitHub PRs / CI / deploy (Delivery view) | Fake PRs and CI status pills | A GitHub App (`backend/app/github_app`, scaffolded) receives PR/CI webhooks and links them back to tasks |
| User accounts | Guest / local profile in `localStorage`. No password check. | SSO via the organisation's identity provider |
| Deprecate suggestions | Canned suggestions from Node `/api/deprecate` | Usage- and trace-based retirement candidates |

### 4.3 How Claude Code was used to build it
- **`CLAUDE.md` as the project constitution:** reading order for the specs, non-negotiables,
  repo layout, run and verify commands, and conventions (for example, "the API contract lives
  in `types.ts`").
- **Custom project skills** (`.claude/skills/`) that form a disciplined one-feature-at-a-time loop:
  `nexus-plan` (grounds the feature in the spec, checks what it could break, saves
  `plans/<slug>.md`, allows only one active plan at a time) → `nexus-spec` (quotes the exact
  spec instead of improvising) → `nexus-frontend-standards` / `nexus-backend-standards` →
  `nexus-new-phase` (scaffolds models, schemas, routes and tests) → `nexus-verify` (typecheck,
  tests, lint, phase-specific checks) → `nexus-log` (appends to `IMPLEMENTATION_LOG.md` and
  closes the plan).
- **Custom subagents for parallel build waves** (`.claude/agents/`): `mvp-backend-core`
  (wave 1: freeze the contract, migrations, LLM factory, fake model), then
  `mvp-agents`, `mvp-backend-api` and `mvp-frontend` in parallel (wave 2), then
  `mvp-verifier` (wave 3: a read-only reviewer against the plan and the non-negotiables).
- **Browser preview tools** (`.claude/launch.json`: `nexus-client`, `nexus-backend`) to drive
  and check UI changes in the browser.
- **Artifacts from the process:** 14 per-feature plans in `plans/`, a dated
  `IMPLEMENTATION_LOG.md`, and `CURRENT_STATE.md` (an honest real / partial / mock inventory).

---

## 5. Setup and run instructions

### 5.1 Prerequisites
- Node.js 22+ (tested on 23.3) and npm
- Python 3.13 and Poetry
- PostgreSQL 16 with the `vector` extension available
- Google Cloud SDK, and a GCP project with the Vertex AI API enabled (needed for the AI features only)

### 5.2 Backend (FastAPI, port 8000)

```bash
cd backend
poetry install
cp .env.example .env            # then set GCP_PROJECT_ID
poetry run docling-tools models download   # one-time, needs network (PDF layout models)
createdb nexus_dev
psql -d nexus_dev -c "CREATE EXTENSION IF NOT EXISTS vector;"
poetry run alembic upgrade head
gcloud auth application-default login
poetry run uvicorn app.main:app --reload --port 8000
```

Key `.env` settings: `DATABASE_URL`, `GCP_PROJECT_ID`, `VERTEX_LOCATION=us-central1`,
`GEMINI_MODEL=gemini-2.5-pro`, `BLOB_DIR`, `MAX_UPLOAD_MB=25`, `AGENT_CONCURRENCY=4`,
`MAX_QUESTIONS_PER_FEATURE=5`, `CORS_ORIGINS=["http://localhost:3000"]`.

Health checks: `GET http://localhost:8000/api/health` (liveness) and `/api/health/ready`
(Postgres + pgvector).

### 5.3 Frontend + board API (Node, port 3000)

```bash
cd client
npm install
npm run dev          # Express + Vite middleware on http://localhost:3000
```

- On first boot, the Node server creates `client/data/nexus.db` from the synthetic seed
  `client/data/database.json`. To reset: stop the server, delete `client/data/nexus.db*`, then
  restart.
- The SPA calls FastAPI at `VITE_BACKEND_URL` (default `http://localhost:8000`).
- `better-sqlite3` is pinned to v12 because v13 segfaults on Node 23.3.

### 5.4 Demo walkthrough
1. Open `http://localhost:3000` → **Log in as guest**.
2. **New Project**: enter a name and description, and attach `backend/tests/fixtures/spec_a.md`.
3. In **Chat**, watch ingestion progress, then review the extracted features and their cited quotes.
4. Answer or skip the clarification questions, then **Approve** the features.
5. **Generate tasks** → review the drafts → **Add N to board**.
6. On the **Board**, add a card like "Sessions expire after 30 minutes". A cited **duplicate**
   verdict appears in **Verdicts**.
7. Try **Memory** ("How does sign-in work?"), **Trace** → *Explain this impact*, and **Author** → BRD.

### 5.5 Verification

```bash
cd client && npx tsc --noEmit && npm test
```

```bash
cd backend && poetry run pytest && poetry run ruff check .
```

The backend tests run with **no network**. A scripted `FakeChatModel`
(`backend/tests/fakes.py`) is injected through the `get_chat_model()` factory.
`test_no_direct_sdk.py` fails the build if any code outside `agents/llm.py` imports the Gemini
SDK directly.

---

## 6. Test datasets

All data is **synthetic**. No client, confidential or personal data is used anywhere.

| Dataset | Location | Purpose |
| --- | --- | --- |
| "Acme Portal — Product Spec v1" | `backend/tests/fixtures/spec_a.md` | Main demo spec: SSO via Okta, session timeout, audit-log CSV export, Azure AD integration |
| "Acme Portal — Security Addendum" | `backend/tests/fixtures/spec_b.md` | Deliberate overlap (Okta SSO) and conflict (8-hour vs 30-minute session timeout) for merge and conflict detection |
| Kickoff meeting notes | `backend/tests/fixtures/notes.txt` | Informal source that repeats spec requirements (tests duplicate detection) |
| Word spec | `backend/tests/fixtures/spec.docx` | DOCX conversion path |
| Two-page PDF | `backend/tests/fixtures/two_page.pdf` | PDF conversion path (Docling) |
| Board seed | `client/data/database.json` | Sample projects, board items and an agent registry (9 agents) used to populate SQLite on first boot |
| Scripted model replies | `backend/tests/fakes.py` + individual tests | Deterministic LLM outputs for the graph, agent and route tests |

---

## 7. Current status and known limitations

Status words: **real** means the feature persists data or calls the live AI path, **partial**
means real data with some leftover mock pieces, and **mock** means seeded demo data. The full
breakdown is in `CURRENT_STATE.md`.

- **Real:** projects, the ingest → features → clarification → tasks → board workflow,
  classifying cards on add, Memory Q&A, card-level Ask AI, Trace explain, and Author.
- **Partial:** Sources (upload is real, connectors are stubs), the Verdicts inbox (there are no
  architecture Decision Records with vector retrieval yet), the card drawer (History tab is
  fake), and Settings (the bring-your-own-key field doesn't drive Vertex).
- **Mock:** Runs, Reviews and Delivery (build/verify/ship stages 12–15), plus Deprecate.
- **Other gaps:** there are no real user accounts. Deleting a project in Node doesn't delete
  its Postgres data. Embeddings and vector retrieval were removed with the earlier P6 pipeline
  and haven't been restored.
