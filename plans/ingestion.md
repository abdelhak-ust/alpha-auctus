---
feature: Document ingestion → Feature Registry (stage 1 of 3)
phase: P6
status: done
created: 2026-09-26
completed: 2026-09-27
note: built and verified at cf0f298 (live Qdrant/Redis/Vertex path not exercised); superseded on branch mpv_v0 by plans/mvp-v0.md
---

# Document Ingestion & Feature-Understanding Pipeline

## Design Document

> **Stage 1 of 3.** Output feeds [`FEATURE_REGISTRY.md`](FEATURE_REGISTRY.md) (clarification chat),
> which feeds [`Devevloper_tasks_factory.md`](Devevloper_tasks_factory.md) (task generation). The
> data model, lifecycle, citation shape and LangGraph conventions shared by all three live in
> [`feature-pipeline-contract.md`](feature-pipeline-contract.md) — that file wins on any conflict.
> (Supersedes the removed 2026-09-24 P6 pipeline; see IMPLEMENTATION_LOG.md 2026-09-26.)

---

## 1. Purpose

This pipeline ingests large, heterogeneous documents (specs, BRDs, PRDs, meeting notes, etc.), extracts a coherent, deduplicated **feature registry** from them, and keeps that registry consistent as new documents are added over time — without losing information split across chunks or across separate document uploads, and without creating duplicate or contradictory feature entries.

Two operating modes are covered:

1. **Initial ingestion** — processing a document (or corpus) for the first time.
2. **Incremental ingestion** — processing a new document against an already-populated registry, merging new information, detecting duplicates, and flagging conflicts.

---



## 2. Core Design Principles

- **Structure before text.** Parse documents into structured representations (headings, sections, tables, reading order) before chunking. Never chunk raw flattened text.
- **No chunk is extracted in isolation.** Every extraction call is given compressed context of what's already been found — either rolling state (within one document) or retrieved candidates (across documents).
- **Separate "find candidates" from "merge candidates."** A single LLM pass should not both discover fragments and resolve them into a final coherent registry. These are two distinct passes with different goals (recall vs. precision).
- **Provenance is mandatory.** Every feature record must trace back to the exact document, section, and chunk it came from. Without this, deduplication and conflict resolution are unauditable.
- **Upsert, never blind-insert.** Both the vector store and the relational store treat features as stable entities identified by `feature_id`, not as append-only logs.
- **Idempotency.** Re-uploading the same document must not reprocess or duplicate anything.

---



## 3. Tech Stack


| Layer                                   | Tool                                                                                              | Notes                                                                                                                        |
| --------------------------------------- | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Document parsing                        | **Docling**                                                                                       | Layout-aware extraction: headings, tables, reading order, figures. Fallback to Tesseract/PaddleOCR for poor scans if needed. |
| Chunking                                | Structure-aware splitter (LlamaIndex / LangChain header splitters, driven by Docling's structure) | Boundary overlap of ~200–500 tokens.                                                                                         |
| Orchestration / stateful extraction     | **LangGraph**                                                                                     | Manages rolling state within a document and multi-step extraction/consolidation flow.                                        |
| Embeddings                              | **Gemini Embedding API via Vertex AI** (`RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY` task types)      | Batched, cached by content hash.                                                                                             |
| Extraction / consolidation LLM          | **Gemini via Vertex AI**                                                                          | Same shared `backend/app/ai/` client as embeddings (resolves former open decision #2).                                       |
| Vector store                            | **Qdrant**                                                                                        | Dense vectors + payload metadata; optional sparse vectors (BM25/SPLADE) for hybrid search.                                   |
| Structured/versioned store              | **Postgres**                                                                                      | Canonical feature registry, versioned records, provenance links.                                                             |
| Evaluation                              | **Ragas**                                                                                         | Validates retrieval/extraction quality, tunes similarity thresholds.                                                         |
| Alternative parser (bake-off candidate) | **Marker**                                                                                        | Compare against Docling on dense/academic-style PDFs.                                                                        |
| Alternative pipeline framework          | **Haystack**                                                                                      | Considered if LangGraph/LangChain orchestration proves insufficient.                                                         |


---



## 4. Data Model



### 4.1 Feature record (Postgres — canonical, versioned)

Full definition: [contract §2](feature-pipeline-contract.md#2-the-feature-record-owned-by-ingestion-extended-downstream).
Ingestion creates these rows; the registry later fills `classification` / `readiness` / `override`.

```
features
├── feature_id (stable UUID)
├── project_id
├── current_version_id
├── name
├── lifecycle_state (extracted | consolidated | conflicted | … — see contract §3)
├── classification / readiness / override   (jsonb, written by the registry stage)
├── created_at / updated_at

feature_versions
├── version_id
├── feature_id (FK)
├── version_no (monotonic; = the task factory's spec_version)
├── description
├── source_refs [{doc_id, doc_type, chunk_id, section, char_start, char_end, snippet, confidence}]
├── created_from (ingest:<doc_id> | chat:<doc_id> | manual:<user_id>)
├── created_at

feature_relations   (optional, if features reference each other)
├── feature_id_a
├── feature_id_b
├── relation_type (depends_on | extends | conflicts_with)
```



### 4.2 Vector store (Qdrant)

- One point per **feature** (not per chunk) for the canonical registry — re-embedded and upserted by `feature_id` whenever the description changes.
- A second collection of **chunk-level embeddings** (`chunks`) — **required**, not optional: the registry's Completeness Assessor retrieves a feature's source chunks (filter by `feature_id` / `doc_id`) to fill readiness fields from the documents before asking the user anything. Chat answers (`doc_type: chat`) are chunked and embedded here too.
- Payload includes: `project_id`, `feature_id`, `name`, `lifecycle_state`, `source_refs`, `last_updated` (every query filters by `project_id`).



### 4.3 Document tracking

```
documents
├── doc_id
├── project_id
├── doc_type (upload | transcript | email | ticket | sheet | chat)
├── content_hash (for idempotency — unique per project_id)
├── filename, upload metadata
├── ingestion_status (pending | parsed | extracted | consolidated | done | failed)
├── ingested_at
```

---



## 5. Pipeline — Initial Ingestion

```
1. Intake & Triage
   - Validate file, compute content_hash
   - If hash already exists in `documents` → skip (idempotent)
   - Register document, status = pending

2. Parse (Docling)
   - Extract structured representation: headings, sections, tables, reading order
   - Output: structured doc tree with page/section metadata

3. Chunk
   - Split along section/heading boundaries
   - Apply overlap (~200–500 tokens) at boundaries
   - Each chunk tagged with: chunk_id, doc_id, section_path, page_range, char_start, char_end
     (offsets are what every downstream citation points at — contract §5)

4. Sequential Extraction (LangGraph, rolling state)
   For each chunk, in order:
     - Pass chunk + compact running feature summary (name + 1-line status per
       feature found so far in THIS document) to extraction LLM
     - LLM emits structured fragments:
         { feature_name, description, status: new|continuation|update,
           references_feature (if continuation), source_location, confidence }
     - Update rolling state (compact form only — full detail stored separately)

5. Consolidation Pass
   - Group fragments by feature_id / references_feature
   - One LLM call per group: merge into one coherent description,
     flag contradictions within the same document

6. Completeness Sweep
   - Run a high-recall, low-precision pass: "list every candidate feature
     mention, even fragments"
   - Reconcile against consolidated set; anything uncovered → flag for review
   - Track chunks that contributed zero features (spot-check candidates)

7. Embed & Store
   - Embed each consolidated feature (Gemini, RETRIEVAL_DOCUMENT)
   - Upsert into Qdrant (feature_id as point ID)
   - Write feature + feature_version rows into Postgres, with source_refs
   - lifecycle_state = consolidated (or conflicted if step 5 found an in-document contradiction)

8. Mark document status = done

9. Hand off to the registry (contract §3)
   - For every feature now `consolidated`: enqueue a `readiness` graph run
   - `conflicted` features are NOT handed off until a human resolves them
```

---



## 6. Pipeline — Incremental Ingestion (New Document)

The key structural difference: extraction must be aware of the **existing registry**, not just this document's own rolling state.

```
1. Intake & Triage
   - Same idempotency check via content_hash

2. Parse (Docling) + Chunk
   - Same as initial ingestion

3. Retrieve Candidate Matches (per chunk, before extraction)
   - Embed chunk (Gemini, RETRIEVAL_QUERY)
   - Query Qdrant feature collection for top-k similar existing features

4. Extraction with Registry Awareness (LangGraph)
   - Pass: chunk + retrieved candidate features + rolling state for THIS document
   - LLM classifies each fragment into one of four outcomes:

     a) NEW FEATURE       → no good match in registry
     b) UPDATE            → matches existing feature, adds new detail
     c) CONFLICT          → matches existing feature, contradicts it
     d) DUPLICATE         → matches existing feature, adds nothing new

5. Route by outcome
   - NEW      → normal consolidation (as in initial ingestion, step 5)
   - UPDATE   → merge pass: reconcile new detail into existing feature_version,
                append source_document, create new version, upsert Qdrant point
   - CONFLICT → do NOT auto-merge; write to conflict queue with both versions
                and sources; resolve per configured policy (see §7)
   - DUPLICATE → discard fragment, but append this document to the existing
                 feature's source_documents list (provenance/confirmation signal)

6. Completeness Sweep
   - Same as initial ingestion, scoped to this document's chunks

7. Registry Update
   - Postgres: new/updated feature_versions, updated `current_version_id`
   - Qdrant: upsert changed feature points only (not full re-embed of registry)

8. Mark document status = done

9. Hand off to the registry (contract §3)
   - NEW features → `consolidated` → enqueue a `readiness` run
   - UPDATE on a feature already past `consolidated` (classified … dev_ready, overridden,
     broken_down) → new version sets `stale` → re-enters the readiness graph; if it already
     has tasks, the task factory later runs diff-aware regeneration
   - CONFLICT → `conflicted`, no hand-off until resolved (§7)
   - DUPLICATE → no new version, no hand-off (provenance append only)
```

---



## 7. Conflict Resolution Policy

Conflicts (same feature, contradictory description) are the highest-risk case for silent data corruption. Recommended default:

- **Do not auto-merge conflicts.** Write both versions to `feature_versions`, mark feature `lifecycle_state = conflicted`, and surface in a review queue with both versions, their `source_refs`, and ranked candidates for the human to confirm.
- **Policy: manual only.** A human must resolve every conflict before the feature leaves `conflicted` (CLAUDE.md: "Human is the final approver"). Resolution writes a new `feature_version` → `consolidated` → hand-off to the registry.
- *Recency wins* / *confidence wins* may be offered later **only as a pre-selected suggestion** in the review UI, never as automatic resolution.
- A `conflicted` feature is invisible to the registry and task factory stages.

---



## 8. Guardrails & Operational Concerns

- **Similarity threshold tuning** for the retrieval-before-extraction step is the single biggest lever on false-duplicate vs. false-new-feature rates. Validate with Ragas against a labeled eval set before trusting it in production.
- **Batching & rate limits** on Vertex AI embedding calls — batch chunks, apply backoff/retry, cache by content hash to avoid re-embedding unchanged text.
- **Cost tracking** — log token counts per embedding/extraction call if volume is significant.
- **Batch-of-documents case** — if multiple new documents arrive together, extract from all first, then run one consolidation pass across the batch + existing registry, rather than processing documents one at a time (reduces redundant merge calls when several new docs mention the same new feature).
- **Hybrid search** — pair Gemini dense embeddings with Qdrant sparse vectors (BM25/SPLADE, computed locally, no API cost) to improve retrieval precision without increasing Vertex AI spend.
- **Access control** — if source documents carry permissions, propagate them to derived features/chunks so downstream retrieval respects the same boundaries.

---



## 9. Open Decisions (to confirm before implementation)

- [x] Conflict policy default → **manual-only** (§7).
- [x] Extraction/consolidation LLM → **Gemini via Vertex AI**, one shared client with embeddings.
- [x] Similarity threshold for "same feature" → **0.80 cosine, config-tunable** (`settings.feature_match_threshold`), leaning toward recall; any candidate ≥ threshold (top-k = 5) goes to the LLM classifier. Re-tune once an eval set exists.
- [x] v1 file types → **PDF, DOCX, Markdown, TXT**. CSV/spreadsheets, transcripts, email, tickets and images are out of v1 (upload rejects them with a clear message).
- [x] v1 dependencies → **Docling only** for parsing. Marker bake-off and Ragas evals are deferred until a labeled eval set exists.
- [x] Relationship graph from day one → **yes**, `feature_relations` (`depends_on` is read by the registry and task factory).
- [x] Human review UI for the conflict queue → **reuse** the existing ingest review queue / Verdicts inbox (`IngestItem`, `VerdictRow.tsx`); a conflicted feature appears there with both versions as ranked candidates, each with its `source_refs`.
- [x] How the running app reaches this pipeline → **the frontend calls `backend/` directly** (CORS for `http://localhost:3000` on the FastAPI app; `VITE_BACKEND_URL` in the client). The Node `/api/sources/upload` mock is retired once the upload screen points at `backend/`.
- [x] DecisionRecord extraction → **dropped**: features only. Conflict detection here is feature-vs-feature.

---

## 10. Output contract (what the registry stage can rely on)

- `features` row per feature, `lifecycle_state ∈ {consolidated, conflicted}`, `project_id` set.
- Current `feature_versions` row with `description` and non-empty `source_refs` (char offsets included).
- Source chunks retrievable from Qdrant `chunks` by `feature_id` / `doc_id`.
- `feature_relations` rows for any `depends_on` / `extends` / `conflicts_with` found.
- One `readiness` job enqueued per `consolidated` feature; none for `conflicted`.

---

## 11. Implementation team & build contract

Built by the agents in `.claude/agents/` (`ingestion-*`), in waves. Each agent owns a disjoint
set of files; anything outside its list is read-only to it.

| Wave | Agent | Owns |
| --- | --- | --- |
| 1 | `ingestion-foundation` | `app/ai/` (→ Gemini), `app/config.py`, `app/vector/` (Qdrant), `app/graph/` (LangGraph checkpointer + audit helper), `app/queue/`, `pyproject.toml`/`poetry.lock`, `backend/README.md`, `.env.example`, `docker-compose.yml` |
| 1 | `ingestion-data` | `app/models/` (ingestion tables), `app/schemas/ingestion.py`, `migrations/versions/*`, `tests/conftest.py` |
| 2 | `ingestion-pipeline` | `app/ingest/` (LangGraph `ingest` graph: parse → chunk → extract → consolidate → sweep → embed/store → hand-off) |
| 2 | `ingestion-api` | `app/api/routes/ingestion.py`, route registration in `app/main.py`, `tests/test_ingestion_routes.py` |
| 2 | `ingestion-frontend` | `client/src/lib/backend.ts`, additive types in `client/src/types.ts`, ingestion calls in `client/src/context/ProjectContext.tsx`, `client/.env.example` |
| 3 | `ingestion-verifier` | nothing — read-only review + `nexus-verify`; reports findings |

### 11.1 Interfaces between agents (frozen — change only by editing this section)

**Settings** (`app/config.py`): `qdrant_url` (default `http://localhost:6333`), `vertex_location`
(default `us-central1`), `gemini_model` (default `gemini-2.5-pro`), `gemini_embedding_model`
(default `gemini-embedding-001`), `embedding_dim` (default `768`), `feature_match_threshold`
(default `0.80`), `feature_match_top_k` (default `5`), `blob_dir` (default `./data/blobs`),
`max_upload_mb` (default `25`), `cors_origins` includes `http://localhost:3000`.

**AI adapter** (`app/ai/`): `async generate_json(prompt: str, schema: type[BaseModel], *, system: str | None = None) -> BaseModel`
and `async embed_texts(texts: list[str], *, task_type: Literal["RETRIEVAL_DOCUMENT","RETRIEVAL_QUERY"]) -> list[list[float]]`;
both raise `VertexNotConfigured` when unconfigured. Tests mock these two functions, never the SDK.

**Vector store** (`app/vector/`): `ensure_collections()`, `upsert_features(points)`,
`upsert_chunks(points)`, `search_features(project_id, vector, top_k, threshold)`,
`get_chunks(project_id, *, feature_id=None, doc_id=None)`. Collections `features`, `chunks`
(`historical_tasks` is created later by stage 3). Every point payload carries `project_id`.

**Graph infra** (`app/graph/`): `get_checkpointer()` (LangGraph Postgres checkpointer),
`record_audit(session, *, project_id, feature_id, graph, node, type, detail)`.
**Queue** (`app/queue/`): `enqueue(job_name: str, **kwargs)` — arq; job names `ingest_document`,
`readiness_run` (the latter is a registered no-op stub until stage 2 exists).

**Tables** (`app/models/`, one Alembic migration): `documents`, `chunks`, `features`,
`feature_versions`, `feature_relations`, `review_items`, `audit_events` — columns per §4 and
contract §2; `project_id` is a plain `String` (projects still live in Node SQLite, no FK).
`review_items(id, project_id, kind: conflict|sweep_flag, feature_id?, document_id, payload jsonb, status: open|approved|dismissed, created_at, resolved_by?)`.

**HTTP API** (prefix `/api`, all project-scoped; shapes in `app/schemas/ingestion.py`, camelCase
aliases so JSON matches `client/src/types.ts`):

| Method & path | Body | Returns |
| --- | --- | --- |
| `POST /projects/{projectId}/documents` | multipart `file` (PDF/DOCX/MD/TXT, ≤ `max_upload_mb`) | `202 IngestDocument` (duplicate hash → `200` with the existing one, `duplicate: true`) |
| `GET /projects/{projectId}/documents` | — | `IngestDocument[]` |
| `GET /projects/{projectId}/documents/{documentId}` | — | `IngestDocument` |
| `GET /projects/{projectId}/features` | — | `RegistryFeature[]` |
| `GET /projects/{projectId}/review-queue` | — | `IngestItem[]` (existing type; `verdict.candidates` = ranked alternatives, `sourceSnippet` = cited snippet) |
| `POST /projects/{projectId}/review-queue/{itemId}/resolve` | `{ action: 'approve' \| 'dismiss' }` | `{ ok: true }` — conflict: approve = accept the new version, dismiss = keep current; sweep flag: approve = create feature, dismiss = drop flag |

New client types (added to `client/src/types.ts` by `ingestion-frontend`, mirrored exactly by
`ingestion-data`):

```ts
export type IngestionStatus = 'pending' | 'parsed' | 'extracted' | 'consolidated' | 'done' | 'failed';
export interface IngestDocument {
  id: string; projectId: string; filename: string; status: IngestionStatus;
  error?: string; duplicate?: boolean; featureCount: number; uploadedAt: string;
}
export type FeatureLifecycle = 'extracted' | 'consolidated' | 'conflicted' | 'classified' | 'assessing'
  | 'awaiting_answers' | 'answered' | 'dev_ready' | 'overridden' | 'stale'
  | 'in_breakdown' | 'needs_review' | 'broken_down';
export interface SourceRef {
  docId: string; docType: string; chunkId: string; section: string;
  charStart: number; charEnd: number; snippet: string;
}
export interface RegistryFeature {
  id: string; projectId: string; name: string; description: string; versionNo: number;
  lifecycleState: FeatureLifecycle; sourceRefs: SourceRef[]; updatedAt: string;
}
```

**Errors:** `{ detail: { problem, cause, fix } }` (ui_ux_design.md §7 "problem + cause + fix").
Unsupported type → 415, too large → 413, unknown project/doc/item → 404, Vertex unconfigured → 503.

### 11.2 Definition of done (whole stage)
- `cd backend && poetry run pytest && poetry run ruff check .` green; AI and Qdrant mocked in tests.
- `alembic upgrade head` then `downgrade base` both succeed on `nexus_dev`.
- `cd client && npx tsc --noEmit && npm test` green.
- Browser preview: upload a PDF on the Sources view → status reaches `done` (or a cited
  `failed` error when Vertex isn't configured) → conflicts appear in the existing review queue
  and approve/dismiss works. Board-data endpoints on `client/server.ts` keep working.
- `nexus-verify` passes, then `nexus-log`.

### 11.3 Amendments from the mid-build cross-check (2026-09-26) — frozen, supersede §11.1 where they differ

**Names & ids.** Models keep their column names (`Document.doc_id`, `.ingestion_status`,
`.uploaded_at`, `.blob_path`, `.mime_type`, `.size_bytes`; `Feature.feature_id`;
`FeatureVersion.version_id`). API builds response schemas explicitly (`id=str(doc.doc_id)`…),
never via `from_attributes`. All ids are UUIDs, serialized as lowercase hyphenated strings.
Confidence is a 0–1 float everywhere in DB/payloads; the API converts to 0–100 for the UI.

**Paths & settings (foundation).** `BACKEND_DIR = Path(__file__).resolve().parents[1]`;
`env_file = BACKEND_DIR / ".env"`; relative `blob_dir` resolved against `BACKEND_DIR`.
`vertex_location` replaces `gcp_region`. API stores `blob_path = f"{project_id}/{sha256}{ext}"`
(relative to `blob_dir`) plus `mime_type`, `size_bytes`; pipeline reads `Path(settings.blob_dir) / doc.blob_path`.

**Queue (foundation).** `app/queue/__init__.py`: `async def enqueue(job_name: str, **kwargs) -> str | None`,
raises `QueueUnavailable` if Redis is down (API → 503); must not import `app.ingest`/`app.api`.
`app/queue/worker.py`: `WorkerSettings`, jobs registered by string path
(`func("app.ingest.jobs.ingest_document", name="ingest_document")`), `on_startup` calls
`ensure_collections()`. Stub: `async def readiness_run(ctx, feature_id: str, project_id: str, **_) -> None`.
Calls: `enqueue("ingest_document", document_id=..., _job_id=f"ingest_document:{id}")`;
`enqueue("readiness_run", feature_id=..., project_id=...)`. Callers use `from app import ai, queue`
and call through the module (so tests monkeypatch `app.ai.*` / `app.queue.*`).
`docker-compose.yml` runs **Qdrant and Redis**.

**Job (pipeline).** `async def ingest_document(ctx, document_id: str, *, session_factory=None) -> None`
(defaults to `app.db.session.async_session_factory`); `build_ingest_graph(checkpointer=None)`.

**Graph infra (foundation).** `async def record_audit(session, *, project_id, feature_id, graph, node, type, detail=None) -> AuditEvent`
— add + flush, never commit. `async def get_checkpointer()` — process-wide `AsyncPostgresSaver`,
DSN converted from `postgresql+asyncpg://` to `postgresql://`, `setup()` once, langgraph imported
lazily. `app.models` never imports `app.graph`.

**Vector (foundation), async.** `get_client()` cached (`qdrant_url == ":memory:"` → in-memory),
`set_client(c)` / `reset_client()` for tests. Points `{id: str(UUID), vector, payload}`.
Feature payload `{project_id, feature_id, name, lifecycle_state, source_refs, last_updated}`;
chunk payload `{project_id, doc_id, chunk_id, feature_ids: list[str], section, char_start, char_end, text}`;
payload indexes on those ids. `search_features(project_id, vector, top_k=…, threshold=…) -> list[ScoredFeature(feature_id, score, payload)]`.
`get_chunks(project_id, *, feature_id=None, doc_id=None)` filters `feature_ids`.
`embed_texts` passes `output_dimensionality=settings.embedding_dim`; falls back to per-text
calls if the model rejects batches.

**Citations (pipeline).** `source_ref.char_start/char_end` are **document-level** offsets into the
parsed text; `snippet == text[char_start:char_end]` exactly, located by exact string search
(never LLM-returned offsets). `section` = last element of the section path; chunk column stores
`" > ".join(path)`. `created_from = f"ingest:{doc_id}"`. `documents.error` = one string
`"<problem> <cause> <fix>"`.

**Review item payloads (pipeline writes, API reads).**
- `conflict`: `{feature_name, reason, confidence, current_version_id, incoming_version_id}`. The
  incoming side is a real `feature_versions` row (`version_no = max+1`), **not** made current and
  **not** upserted to Qdrant. In-document contradiction on a new feature: first statement = v1
  (current), contradicting one = v2 (incoming). No `candidates` key — the API builds the two ranked candidates.
- `sweep_flag`: `{feature_name, description, reason, confidence, source_ref}`; `source_ref` always
  present — if the snippet isn't found verbatim, cite the whole chunk (first ~300 chars) and add `"located": false`.
- Candidate ids in `IngestItem.verdict.candidates` are non-numeric: `incoming:v{n}`, `current:v{n}`, `flag:{item_id}`.
- Sweep flags map to `verdict.type = 'net-new'` with confidence ≤ 49 (low-confidence).

**Resolve (API).** Conflict approve = point `current_version_id` at `incoming_version_id` (create a
version only if that row is missing). After any resolution that changes the current description or
creates a feature, call `app.ingest.store.reindex_feature(session, feature_id)` (pipeline exports it;
no Docling imports in `store.py`) before commit; on `VertexNotConfigured` / vector error → rollback + 503.

**DUPLICATE provenance.** Append the new `source_ref` to the current version's `source_refs`
(no version bump — it adds evidence, not content) and write a `provenance_append` audit row.

**Frontend.** May make a minimal edit to `client/src/components/VerdictRow.tsx`: backend ingest
items with `net-new` render the existing low-confidence badge + "please review" tint and are
excluded from bulk actions. Conflict button copy / incoming-vs-current labels = spec gap (flag, don't invent).

**Data.** `conftest.py` never imports `app.main` at module level. Fixtures: `db_session`,
`api_client` (overrides `get_db`), factories `make_document`, `make_feature`; per-test engine
with `NullPool`; outer transaction with `join_transaction_mode="create_savepoint"`. Migration
up/down/up cycle on a scratch DB (`nexus_migcheck`); leave `nexus_test` and `nexus_dev` at head.
`migrations/env.py` excludes LangGraph `checkpoint*` tables from autogenerate.

**Foundation also owns:** `.gitignore` entry `backend/data/`, and a `nexus-worker` entry in
`.claude/launch.json` (arq worker) plus pinning `nexus-client` to port 3000 (no autoPort) so CORS holds.

**Test gate while in flight:** each agent runs only its own test files until foundation reports;
nobody patches another agent's files to get green.

**Post-verification sign-off (2026-09-26).** `ingestion-frontend` also owns the file-passing /
inline-error changes in `client/src/App.tsx` (SourcesView) and
`client/src/components/NewProjectSetup.tsx` — they were already in its agent definition ("minimal
changes … only where they must pass a `File`"); the §11 table omitted them. Retry semantics: a
re-upload whose `(project_id, content_hash)` row is `failed` resets it to `pending`, clears
`error`, and re-enqueues (`_job_id = f"ingest_document:{id}:retry:{n}"`) — it is **not** a
duplicate. Resolving one conflict never moves a feature out of `conflicted` (or hands it off)
while another `open` conflict item exists for that feature.
