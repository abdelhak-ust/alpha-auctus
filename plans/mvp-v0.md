---
feature: MVP v0 — document → features → clarification → tasks (presentation build)
phase: MVP
status: done
created: 2026-09-27
completed: 2026-09-27
note: automated verify passed (pytest 49, ruff, tsc, npm test 37, scratch-DB migration up/down/up). Live Vertex/Docling demo was not run in this environment — plans/mvp-v0-demo.md was not written.
---

# MVP v0: document → features → clarification chat → tasks (LangGraph agents)

> Branch `mpv_v0`. Build agents (`.claude/agents/mvp-*.md`) are created when the build starts.

## Context

We need a working, demo-able end-to-end flow for a presentation. The committed P6 pipeline
(`cf0f298`: Qdrant, Redis/arq, registry matching, conflict queue) is too heavy to run and
explain on stage. The MVP keeps FastAPI, Postgres, Docling and LangGraph. The AI work is done
by **LangGraph agents**, each with a clear role, which also makes the demo story easy to tell.

**The flow (the owner's 8 steps):**
1. Upload a PDF, Markdown or DOCX file.
2. Convert PDF/DOCX to Markdown.
3. Agents extract **features** from the Markdown.
4. Large documents are split into chunks before extraction.
5. **Pass 1** extracts features only. **Pass 2** runs per feature to gather all of its relevant
   information.
6. Each feature gets **clarification questions** where needed.
7. The questions are collected, and the **project manager answers them in a chat**. Each answer
   updates its feature.
8. **Tasks** are generated per feature, reviewed, and added to the board.

**Owner decisions (2026-09-27):**
- **LangGraph agents do all the AI work.** Pipeline code never calls the Gemini SDK directly.
  Gemini on Vertex AI is reached through LangChain's chat model, built in one place.
- Postgres only. No Qdrant and no Redis/arq; graphs run as in-process background tasks.
  LangGraph state and the human-in-the-loop pauses are saved with the Postgres checkpointer.
- Approved tasks become cards on the existing Kanban board.
- Reuse existing screens, plus one new Features view.

**Non-negotiables kept** (CLAUDE.md):
- Every feature detail cites a verbatim document quote or a PM answer. A quote that can't be
  found in the document is shown as "unverified", never presented as fact.
- Tasks reach the board only when a human clicks.
- Questions are never auto-answered: the clarification graph *pauses* for the PM.

---

## Architecture

```
client (React) ──REST──▶ backend (FastAPI :8000)
     │                     ├─ LangGraph graphs (in-process asyncio tasks)
     │                     │    document_graph ─ clarification_graph ─ task_graph
     │                     │    agents ──▶ ChatGoogleGenerativeAI(vertexai=True) ──▶ Gemini
     │                     └─ Postgres: app tables + LangGraph checkpoints
     └──REST──▶ client/server.ts (:3000, Node/SQLite): board Items (unchanged API)
```

### Three graphs and five agents (`backend/app/agents/`)

| Graph | Nodes (★ = LLM agent) | Owner step |
|---|---|---|
| **`document_graph`** (one run per upload, thread `doc:{id}`) | `convert` → `split` → ★**Feature Extractor** (loops over chunks) → ★**Feature Merger** (only if more than one chunk) → fan-out `Send` per feature → ★**Feature Analyst** → `verify_citations` → `persist` | 1–6 |
| **`clarification_graph`** (one per project, thread `clarify:{project_id}`) | `next_question` → `interrupt()` (waits for the PM) → ★**Clarifier** → loop until no open questions | 7 |
| **`task_graph`** (one run per feature, thread `tasks:{feature_id}`) | ★**Task Planner** → ★**Task Reviewer** (critic; sends back to the planner at most once) → `persist_drafts` | 8 |

**The five agents:**
- **Feature Extractor (pass 1).**
  - A structured-output agent (`model.with_structured_output(ExtractedFeatures)`).
  - Input: one chunk plus the running list of features found so far (name + one-liner).
  - Output: new features `{name, summary, source_quotes[]}` only, never repeats.
- **Feature Merger.**
  - A structured-output agent.
  - Merges duplicate or near-duplicate features found across chunks into canonical ones,
    keeping every quote.
- **Feature Analyst (pass 2 + questions).**
  - A **tool-using ReAct agent** (`langgraph.prebuilt.create_react_agent` with
    `response_format=FeatureDetails`). It actively collects all relevant information instead of
    relying on one prompt.
  - **Tools** (in `tools.py`, read-only over the document's Markdown):
    - `search_document(query)`: the top passages by keyword match, with their offsets.
    - `read_section(heading)`: the full text of one section.
    - `list_sections()`: the document's outline.
  - **Output `FeatureDetails`:**
    - `description`, `user_roles[]`
    - `functional_requirements[{text, quote}]`
    - `acceptance_criteria[{given, when, then, quote}]`
    - `constraints[]`, `dependencies[]`, `out_of_scope[]`
    - `questions[{question, why, target_field}]`, at most `max_questions_per_feature` (5).
  - A recursion limit (`analyst_max_steps`, 8) bounds tool use.
- **Clarifier (step 7).**
  - A **tool-using ReAct agent**. Input: the feature, the question and the PM's answer.
  - **Tools:**
    - `update_feature_field(field, value)`: every value it writes is cited as a PM answer.
    - `ask_follow_up(question, why)`: capped at 2 follow-ups per feature.
    - `mark_resolved()`.
  - It writes only through these tools; never free text into the DB.
- **Task Planner and Task Reviewer (step 8).**
  - **Planner:** a structured-output agent that produces 3–10 tasks, each `{title, description,
    area, priority P0–P3, acceptance_criteria[{given,when,then}], estimate S|M|L,
    traces_to: [requirement text]}`.
  - **Reviewer:** a structured-output critic. It checks that each task traces to a requirement
    or PM answer, has testable AC, and adds no invented scope. It returns
    `{pass, issues[{task_index, problem}]}`.
  - On failure the planner gets the issues and runs once more. After that the drafts are saved
    as they are, with `review_notes` shown to the human.

**Deterministic nodes (no LLM):** `convert`, `split`, `verify_citations`, `persist`,
`next_question`, `persist_drafts`. The LLM only proposes; code verifies and writes.

**The LLM factory (`agents/llm.py`) is the only place a model is built:**
`get_chat_model() -> BaseChatModel`, returning
`ChatGoogleGenerativeAI(model=settings.gemini_model, vertexai=True, project=…, location=…,
temperature=0.2, max_retries=…)`. It keeps the actionable "Vertex not configured" error.
Tests inject a scripted fake model through the same factory. If `langchain-google-genai`'s
Vertex mode doesn't work in step 1, fall back to `langchain-google-vertexai`'s `ChatVertexAI`;
it's the same factory, and nothing else changes.

### Running graphs from FastAPI
- **Upload:** `asyncio.create_task(run_document_graph(doc_id))`. Every node persists
  `documents.status` and `progress`. A semaphore caps concurrent Analyst runs
  (`agent_concurrency`, default 4).
- **Clarification:**
  - `GET /clarification` starts or reads the project thread, which is paused at `interrupt()`
    with the current question.
  - `POST /clarification/answer` resumes it with `Command(resume={"answer": …})`.
  - `POST /clarification/skip` resumes it with `Command(resume={"skip": true})`.
  - The Clarifier runs synchronously within the request (a few seconds, with a spinner in the
    UI).
- **Tasks:** `POST /features/{id}/tasks/generate` runs `task_graph` as a background task, and
  the UI polls the feature's status.
- **Startup:** any document left in a running state is marked `failed` ("server restarted —
  re-upload"). Re-uploading a `failed` document restarts it.
- **Board publishing:** the frontend posts approved tasks to Node's `POST /api/items`, then
  records the returned item id with `PATCH /tasks/{id}`.

### Reused (on `mpv_v0`, from `cf0f298`)
- **`backend/app/graph/checkpointer.py`:** `get_checkpointer()`, a Postgres `AsyncPostgresSaver`
  that runs `setup()` once. Also `record_audit` from `app/graph/audit.py`, kept for an
  agent-step log.
- **`backend/app/ingest/parse.py`:** the Docling converter setup, `UnsupportedDocumentType` and
  `EmptyDocument`.
- **`backend/app/ingest/chunk.py`:** the `_split_span` / `_snap_forward_to_word` splitting logic.
- **`backend/app/ingest/cite.py`:** the exact-substring quote locating, simplified.
- **Other backend pieces:** `backend/app/config.py` (settings, `BACKEND_DIR`, `blob_dir`),
  `backend/app/db/*`, and the conftest fixtures `db_session` and `api_client`.
- **Client:**
  - `client/src/lib/backend.ts`: the fetch wrapper, `BackendError` and `withPeriod`.
  - `SourcesView` in `App.tsx`: the drop zone, type guard and inline problem/cause/fix error.
  - `ClarificationChat.tsx`: the chat UI.
  - Node `POST /api/items`.

### Removed on this branch (kept in git history at `cf0f298`)
- **Backend packages:**
  - `app/vector/` and `app/queue/`.
  - `app/ai/`: its `generate_json` / `embed_texts` direct SDK calls are replaced by `agents/llm.py`.
- **Pipeline modules** in `app/ingest/`: `graph.py`, `jobs.py`, `match.py`, `sweep.py`,
  `consolidate.py`, `store.py`, `llm.py`, `extract.py`, `prompts.py`.
- **Routes and tests:** `app/api/routes/ingestion.py` and the P6 tests for all of the above.
- **Dependencies:** `qdrant-client`, `arq`, `redis`, and `docker-compose.yml`.
  - **Kept:** `langgraph`, `langgraph-checkpoint-postgres`, `psycopg[binary]`, `docling`,
    `google-genai`.
  - **Added:** `langchain-google-genai` and `langchain-core`.
- **Client:** the backend review-queue polling and the backend-item branch in `VerdictRow.tsx`.
- **Launch config:** the `nexus-worker` launch entry.

---

## Data model: one new Alembic migration

It drops the P6 tables (`documents`, `chunks`, `features`, `feature_versions`,
`feature_relations`, `review_items`) and keeps `audit_events`. It creates the tables below.
Every table carries a `project_id` String (projects live in Node SQLite, so there is no foreign
key). LangGraph's checkpoint tables are created at runtime by `setup()`; they are already
excluded from autogenerate in `migrations/env.py`.

| Table | Columns |
|---|---|
| `documents` | `id` uuid, `project_id`, `filename`, `mime_type`, `size_bytes`, `content_hash`, `blob_path`, `markdown` text, `status`, `progress` jsonb `{step, done, total}`, `error`, timestamps. Unique on (`project_id`, `content_hash`) |
| `features` | `id`, `project_id`, `document_id` FK, `name`, `summary`, `details` jsonb (`FeatureDetails`), `source_quotes` jsonb `[{quote, verified, char_start?, char_end?}]`, `status`, `position`, timestamps |
| `feature_questions` | `id`, `feature_id` FK, `question`, `why`, `target_field`, `is_follow_up`, `status`, `answer`, `answered_at`, `ordinal` |
| `chat_messages` | `id`, `project_id`, `role` (`ai`/`pm`), `text`, `question_id?`, `feature_id?`, `created_at` |
| `tasks` | `id`, `feature_id` FK, `title`, `description`, `area`, `priority`, `acceptance_criteria` jsonb, `estimate`, `traces_to` jsonb, `review_notes`, `status`, `board_item_id`, `ordinal` |

Status values:
- **`documents.status`:** `uploaded → converting → extracting → analysing → ready`, or `failed`.
- **`features.status`:** `extracted → analysed → needs_clarification → clarified → planning →
  tasks_ready`.
- **`feature_questions.status`:** `open`, `answered` or `skipped`.
- **`tasks.status`:** `draft`, `approved` or `on_board`.

---

## Backend layout

```
backend/app/
├─ ingest/            deterministic document handling (no LLM)
│   ├─ convert.py     md passthrough; pdf/docx → Docling export_to_markdown()
│   ├─ split.py       ≤ extract_chunk_chars (40k) → 1 chunk; else split on ^#{1,3} headings,
│   │                 pack sections, overlap chunk_overlap_chars (1.5k), keep char offsets
│   └─ cite.py        locate quotes (exact, then whitespace-normalised) → verified + offsets
├─ agents/
│   ├─ llm.py         get_chat_model() — the only model factory
│   ├─ prompts.py     all system prompts ("quote verbatim; never invent requirements")
│   ├─ tools.py       search_document, read_section, list_sections, update_feature_field,
│   │                 ask_follow_up, mark_resolved (bound to one doc / feature per run)
│   ├─ extractor.py   Feature Extractor + Feature Merger
│   ├─ analyst.py     Feature Analyst (ReAct + structured response)
│   ├─ clarifier.py   Clarifier (ReAct)
│   ├─ planner.py     Task Planner + Task Reviewer
│   └─ graphs/        document.py · clarification.py · tasks.py (StateGraph definitions + runners)
├─ models/mvp.py      the five tables · schemas/mvp.py (LLM schemas snake_case + API camelCase)
└─ api/routes/mvp.py  the routes below
```

- **Settings:** `gemini_model`, `extract_chunk_chars`, `chunk_overlap_chars`, `agent_concurrency`,
  `max_questions_per_feature`, `analyst_max_steps`, `max_follow_ups_per_feature`.
- **Errors:** any graph error sets `failed` with a problem/cause/fix string, and Vertex being
  unconfigured gets its own message. Every agent step writes an `audit_events` row with
  `graph`, `node`, `agent` and a short detail, so the demo can show what each agent did.

## Backend API: `backend/app/api/routes/mvp.py`

All routes are under `/api/projects/{projectId}`. Errors use the shape
`{detail: {problem, cause, fix}}`.

| Method & path | Purpose |
|---|---|
| `POST /documents` (multipart `file`) | Upload a pdf, md or docx (≤ 25 MB) and start `document_graph`. Returns `202 MvpDocument`. A duplicate returns the existing document; a duplicate of a `failed` one restarts it |
| `GET /documents` · `GET /documents/{id}` | Status and progress, for polling |
| `GET /documents/{id}/markdown` | The converted Markdown |
| `GET /features` · `GET /features/{id}` | Features with details, quotes, questions and tasks |
| `GET /features/{id}/activity` | The agent-step log (from `audit_events`) for the demo's "what the agents did" panel |
| `GET /clarification` | `{history, next: {questionId, featureId, featureName, question, why} \| null, remaining}` |
| `POST /clarification/answer` `{questionId, answer}` | Resume the graph; returns the updated feature, the changes the Clarifier made, and the next question |
| `POST /clarification/skip` `{questionId}` | Resume the graph with skip; returns the next question |
| `POST /features/{id}/tasks/generate` | Start `task_graph`; returns `202` |
| `PATCH /tasks/{id}` `{status?, title?, description?, priority?, boardItemId?}` | Edit, approve, or mark `on_board` |

## Frontend: reuse existing screens, plus one Features view

- **`types.ts`:** add `MvpDocument`, `Feature`, `FeatureDetails`, `FeatureQuestion`,
  `ChatMessage`, `GeneratedTask` and `AgentActivity`, matching the backend's camelCase schemas.
- **`lib/backend.ts`:** replace the P6 functions with the endpoints above, keeping the error
  parsing.
- **Sources view:** same drop zone (`.pdf,.md,.docx`). A document list shows each file's step
  and progress ("Extractor: chunk 2/5", "Analyst: 4/9 features"), with a failed state and Retry.
  "Open features" jumps to the Features view.
- **Features view (new; nav "Features", next to Sources):**
  - Feature cards: name, summary, status badge, open-question count and task count.
  - Expanding a card shows the details with a `CitationChip` quote, an "unverified" tint or a
    "PM answer" chip.
  - The card also shows its questions, a "View source Markdown" toggle, and an **Agent
    activity** list (which agent ran, what it did).
  - Buttons: **Clarify**, **Generate tasks**, and **Add to board** / **Add all approved**.
  - Tasks show their `traces_to` and the reviewer's notes.
- **Clarification chat:** extract `ChatThread` from `ClarificationChat.tsx`, reused by New
  Project setup and a new `FeatureClarification` panel.
  - The AI asks the next question, prefixed with the feature name and "why this matters".
  - The PM answers or skips.
  - The panel shows the Clarifier's changes ("Updated <feature> → acceptance criteria") and ends
    with "All questions answered".
- **Board publishing:** "Add to board" posts `{title, description + Given/When/Then lines,
  priority, area, status:'inbox', source:{type:'upload', name: filename, snippet: feature name}}`
  to Node `POST /api/items`, then `PATCH`es the task to `on_board`.
- **`ProjectContext.tsx`:** remove the backend review-queue polling and routing. Add feature,
  clarification and task actions. Polling runs only while something is running.
- **`VerdictRow.tsx`:** revert the backend-item branch.

**Spec gap:** the Features view, agent activity list and per-document progress aren't in
`ui_ux_design.md`. They are approved here as MVP-only, built with the existing tokens and
components (`StatusBadges`, `CitationChip`, `VerdictBadge` tints). Log them as a gap to spec
later.

---

## Build order, with agents for a parallel run

Freeze the contract first: the routes, the TS types, the `schemas/mvp.py` names and the tool
signatures above.

1. **`mvp-backend-core`:**
   - Migration and models, `schemas/mvp.py`, settings.
   - `agents/llm.py` (verify `ChatGoogleGenerativeAI` Vertex mode here, or fall back).
   - The removals and dependency changes, and the scripted fake chat model for tests.
2. **`mvp-agents`:**
   - `ingest/{convert,split,cite}.py`.
   - `agents/{prompts,tools,extractor,analyst,clarifier,planner}.py` and the three graphs.
   - Unit tests with the fake model: every node, tool and graph path, including the interrupt
     and resume.
3. **`mvp-backend-api`:**
   - `routes/mvp.py`, the background runners and startup recovery.
   - Route tests, with the graphs mocked at the runner boundary.
4. **`mvp-frontend`:**
   - The types, `backend.ts`, Sources progress, the Features view with agent activity,
     `ChatThread` + `FeatureClarification`, and board publishing.
   - The `ProjectContext` and `VerdictRow` cleanup.
5. **`mvp-verifier`** (read-only):
   - Tests, lint, migration up/down, the contract ↔ `types.ts` match.
   - The non-negotiables: verified quotes, no auto-publish, no auto-answer (the interrupt is
     always hit), and no direct SDK calls outside `agents/llm.py`.
   - Ownership check and the live demo run.

Agents 1–4 run in parallel against the frozen contract, with the verifier cross-checking during
and after (the same method as the P6 build). New definitions go in `.claude/agents/mvp-*.md`;
the `ingestion-*` agents are removed on this branch. Set `plans/ingestion.md` to `status: done`
with the note "superseded on mpv_v0 by mvp-v0.md", and add an MVP row to the master plan's phase
table.

---

## Verification

- **Automated:**
  - `cd backend && poetry run pytest && poetry run ruff check .`, using the fake chat model
    (no network). The tests cover:
    - **Chunking:** a fixture of more than 40k characters splits on headings with overlap.
    - **Extractor/Merger:** dedupe across chunks.
    - **Analyst:** it calls `search_document` / `read_section`, and questions are capped.
    - **Quotes:** verified and unverified.
    - **Clarification graph:** it pauses at `interrupt` and resumes on answer or skip; the
      Clarifier's tool writes are cited as PM answers; follow-ups are capped.
    - **Planner/Reviewer:** one retry loop, then the drafts are saved.
    - **Tasks:** regenerating keeps `on_board` tasks.
    - **Routes:** every route and error.
    - **Recovery:** a stuck document is marked `failed` on startup.
    - **Guard:** a grep test that no module outside `agents/llm.py` imports `google.genai` or
      builds a chat model.
  - Migration upgrade → downgrade → upgrade on a scratch DB.
  - `cd client && npx tsc --noEmit && npm test`.
- **Live demo run** (needs `gcloud auth application-default login`, `backend/.env` with
  `GCP_PROJECT_ID` + `VERTEX_LOCATION`, and `poetry run docling-tools models download`, but no
  Docker). Run `nexus-backend` + `nexus-client` via the preview tools and upload three files:
  1. A short `.md` spec → features with verified quotes and questions.
  2. A large PDF (more than 40k characters) → several extractor chunks, and no duplicate
     features after the merge.
  3. A `.docx` → the Markdown is viewable.

  Then:
  - Agent activity shows the Analyst's tool calls.
  - Clarify: answer two questions and skip one. The features update and show "PM answer".
  - Generate tasks → the reviewer's notes are visible → Add all approved → the cards appear on
    the Board.
  - An empty `GCP_PROJECT_ID` → `failed` with problem/cause/fix and Retry.
- **Demo script:** a one-page walkthrough, written to `plans/mvp-v0-demo.md` after the live run
  passes.

---

**Completed 2026-09-27.** Implemented on `mpv_v0`. Automated verification passed; see
[IMPLEMENTATION_LOG.md](../IMPLEMENTATION_LOG.md) 2026-09-27. Live Vertex/Docling demo was not
run, so `plans/mvp-v0-demo.md` was not written. The master plan file
`.claude/plans/we-want-nexus-to-sorted-shell.md` is not in this workspace, so no MVP phase-table
row was added.
