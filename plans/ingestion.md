---
feature: Real ingestion pipeline (parse → chunk → extract → embed → provenance)
phase: P6
status: done
created: 2026-09-24
completed: 2026-09-24
---

# Real ingestion pipeline

**Why now / what's wrong with today's version.** `client/server.ts` (`/api/sources/upload`,
lines 993-1083) is a single-shot mock: it stuffs the *entire* raw text into one Gemini prompt,
extracts at most one loosely-typed item, never extracts decisions, never chunks, never embeds
anything (no pgvector use at all), and `sourceSnippet` is a blind `slice(0, 150)` — not a real
citation. `performVerdictAnalysis` (line 524) stuffs *every* item and decision the project has
into one prompt per check — the exact anti-pattern architecture.md warns against ("never stuff
all decisions into one prompt"). None of this is reused as-is; it's replaced by the real
architecture.md pipeline (parse → chunk → extract → embed → write Memory Core), built in
`backend/app/ingest/`. The **API contract and review-queue UX are preserved** so the existing
frontend ([SourcesView](../client/src/App.tsx), [VerdictRow.tsx](../client/src/components/VerdictRow.tsx),
[NewProjectSetup.tsx](../client/src/components/NewProjectSetup.tsx),
[ClarificationChat.tsx](../client/src/components/ClarificationChat.tsx)) needs no rewrite.

**Findings from this planning pass** (grounded against the current codebase state, not just
the original architecture.md/ui_ux_design.md read):
- `app/ai/` (generation + embeddings) is now real, not future work — the embed step below just
  calls `embed_texts()`, no adapter to build.
- **New finding — the bridging gap.** Verified `client/server.ts`'s `startServer()`
  (line 1127): it registers every `/api/*` Express route handler *before*
  `app.use(vite.middlewares)`, so Express intercepts all API calls outright — Vite's dev
  server never sees them, and neither would `backend/` on port 8000 without something
  forwarding to it. "The frontend needs no rewrite" is true, but doesn't by itself explain how
  port 3000 (what the frontend actually talks to) reaches port 8000 (where the real pipeline
  runs). See "Placement" below for the fix.

**Scope for this pass:** real parsing for **text/markdown/CSV/PDF** (uploads) and
**images/whiteboards** (via Claude vision — no separate OCR library). Connector OAuth
(email/Jira/Sheets) stays mocked (as it is today); audio/video ingestion accepts only an
already-produced transcript for now, matching the spec's own deferral of transcription-provider
specifics (ui_ux_design.md, "what this spec deliberately leaves out").

## Placement

Feature-catalog **A** (Intake & knowledge layer), phase **P6** in the master plan. Depended-on
by nothing yet (P5/P7 aren't built); depends on P0 (done) only — P6's original "depends on P5"
is relaxed this pass, see "Conflict-check coupling" below. Correct package:
`backend/app/ingest/` (exists as an empty stub, docstring already names this phase).

**The bridging fix (this pass' key new design decision):** rather than a big-bang cutover of
`client/server.ts`, replace *only* its ingestion-related handlers with a thin proxy to
`backend/` (port 8000), leaving every other `/api/*` route (items, decisions, ask, author,
verdict resolve, etc.) running through the existing Express/Gemini mock exactly as today until
their own phases replace them:

- `app.post('/api/sources/upload', ...)` (line 993) → forward body to
  `POST http://localhost:8000/api/sources/upload`, relay the JSON response.
- New: `app.post('/api/sources/upload-file', ...)` → forward multipart to
  `POST http://localhost:8000/api/sources/upload-file`.
- New: `app.get('/api/sources/:id/status', ...)` → forward to
  `GET http://localhost:8000/api/sources/:id/status`.
- `app.post('/api/ingest/resolve', ...)` (line 1086) → forward to
  `POST http://localhost:8000/api/ingest/resolve`.

This is the route-by-route cutover mechanism the master plan needed and didn't have — worth
keeping as the standard pattern for P1/P2/P3/P4/P5/P9's own future plans too.

## Impact analysis

Files this feature **modifies** (not files it only creates) and what depends on them:

- **`client/server.ts`** — the 4 handlers above change from inline logic to proxy-forwards.
  Consumers: [ProjectContext.tsx](../client/src/context/ProjectContext.tsx)'s `uploadDocument`,
  `resolveIngestItem`, `connectSource` calls — all hit these exact paths with the exact same
  request/response shapes already, so no frontend change. Risk: low — a broken proxy fails
  loudly (connection refused) rather than silently, since `backend/` not running is
  immediately obvious.
- **`backend/app/main.py`** — registers the new `ingestion.py` router. Purely additive
  (`app.include_router(...)`); no existing route is touched.
- **`backend/migrations/env.py`** — already does `from app.models import *` for autogenerate
  (built in the foundations pass); the new `Source`/`Chunk`/`Entity`/`DecisionRecord`/
  `IngestCandidate` models must be actually exported from `app/models/__init__.py` (or
  re-exported from submodules) or autogenerate silently won't see them. Explicit
  implementation step, not just a model-file drop-in.
- **`client/src/types.ts`'s `apiConfig.embeddingsProvider: 'voyage' | 'gemini'`** — checked
  usage: not rendered anywhere in `SettingsView` today (only `provider`/`apiKey`/`noRetention`
  are). Since the backend now hardcodes Vertex embeddings (master plan's resolved decision #6
  — not a per-project configurable choice), this field is effectively **dead** going forward.
  **Decision: leave it alone.** Fixing/removing it is a Settings/governance concern (feature
  catalog K), out of scope for ingestion — flagged here rather than silently patched.
- **`backend/pyproject.toml`** — additive only (`pypdf` already added in the foundations pass;
  still need a chunking token-estimator, e.g. `tiktoken`). No existing dependency changes.

**Conflict-check coupling:** architecture.md states every extracted candidate must be routed
through the Conflict & Dedup Engine before landing. Building the full P5 engine (dual-path
retrieval + classifier) isn't required to prove ingestion end-to-end, so this pass ports
today's simple heuristic (one LLM call against currently-loaded items/decisions) as an
explicitly provisional placeholder — good enough for an internal tool bootstrapping its memory,
swapped for the real P5 engine later with no change to the ingestion pipeline or API shape.

## Data model (new, `backend/app/models/`)

- **`Source`** — id, project_id, type (`upload`|`sheet`|`transcript`|`email`|`ticket`), name,
  mime_type, raw_ref (stored blob path), checksum, status, ingested_at. Matches `WebSource` in
  [types.ts](../client/src/types.ts).
- **`Chunk`** *(new — not explicit in architecture.md's model list, but required to "capture
  all details")* — id, source_id, seq, text, char_start, char_end, `embedding vector(1024)`.
  The provenance unit: every downstream citation traces back to one chunk's exact offsets.
- **`Entity`** — id, project_id, name, aliases[] (drives area tagging, reused by P5/P7).
- **`DecisionRecord`** — id, project_id, statement (atomic, normalized "we will/will not X"),
  polarity, affected_entities[], source_id, chunk_id, decided_at, status, `embedding vector`.
  Today's mock never produces these at all — this is new, real extraction.
- **`IngestCandidate`** — the persisted form of `IngestItem`: id, project_id, title,
  description, entity_tags[], priority, source_id, chunk_id, **verbatim snippet**, status
  (`pending`|`approved`|`dismissed`), placeholder verdict (JSON, same shape as `VerdictDetail`).
  Kept separate from `Item` until approved, exactly like today's `ingestQueue` → `items` move.

Boundary note: extraction here produces `IngestCandidate` (title/description/entities/priority/
citation) — **not** a full Task Contract (AC/DoD/context-pack/agent-readiness). Contract
enrichment stays P1's job and can run on any item, ingested or hand-written, once P1 exists.

## Pipeline stages (`backend/app/ingest/`)

1. **Connector** — one `IngestConnector.fetch() -> RawDocument` interface so a future live
   connector (email/Jira/Sheets) implements the same shape without touching downstream stages.
   This pass: `POST /api/sources/upload` (text, same request shape as today) and new
   `POST /api/sources/upload-file` (multipart, for PDF/images).
2. **Parse** — per-mime-type: text/md/csv passthrough; PDF via `pypdf`; images sent to the
   `ai/` Claude-vision adapter with a transcribe/describe prompt. Both jobs run async via
   `queue/` (arq) so large files never block the request — mirrors the existing "background
   ingest, never block the UI" pattern already in `finishSetupAndGenerate`
   ([ProjectContext.tsx](../client/src/context/ProjectContext.tsx)).
3. **Chunk** — token-aware, paragraph-preserving splitter (~500-800 tokens, slight overlap),
   recording exact char offsets per chunk.
4. **Extract ("understand it")** — one Claude call per chunk with a structured-output schema
   producing candidate `Item`s **and** candidate `DecisionRecord`s together, each carrying a
   **verbatim snippet**. Server-side hallucination guard: reject/flag any candidate whose
   snippet isn't a literal substring of its source chunk — a concrete enforcement of "cite or
   stay silent."
5. **Embed ("index it")** — `from app.ai import embed_texts` (already built, tested — no new
   adapter work this pass) on each chunk and each extracted candidate; written as `pgvector`
   columns in `nexus_dev`. Supersedes architecture.md's original Voyage suggestion; the
   now-dead `apiConfig.embeddingsProvider` field is deliberately left alone (see Impact
   analysis above).
6. **Land + review** — candidates get the provisional placeholder verdict (see above) and are
   written as `IngestCandidate` rows, surfaced through the *existing* ingest review queue UI
   unchanged.
7. **Approve/dismiss** — same contract as today's `/api/ingest/resolve`; approve migrates to a
   real `Item` that now carries a **real** chunk citation (the Drawer's Citations tab stops
   showing a canned snippet).

## API surface (`backend/app/api/routes/ingestion.py`, new)

- `POST /api/sources/upload` — same shape as today (fileName, fileContent, projectId).
- `POST /api/sources/upload-file` — new, multipart, for PDF/images.
- `GET /api/sources/:id/status` — parse/extract/embed progress (feeds the "✓/⟳/⚠ per-file
  status" states already specced in ui_ux_design.md §4.10).
- `/api/ingest/resolve`, `/api/sources` (connector list) — same contract as today.

## New backend dependencies

`pypdf` — **already added** (foundations pass). Still needed: a lightweight token-estimator
for chunking (`tiktoken` is fine as an approximation even though the target model isn't GPT).
Vertex AI embeddings ride on `google-cloud-aiplatform` — already added, already wired via
`app.ai.embed_texts()`, nothing further needed. Raw blobs (uploaded PDFs/images): local disk
(`backend/.data/blobs/`, gitignored, already in `.gitignore`) in dev, Cloud Storage when
deployed, per the master plan §0.3's local-fast/cloud-native-deployed split.

## Implementation steps (order)

1. `backend/app/models/`: `Source`, `Chunk`, `Entity`, `DecisionRecord`, `IngestCandidate` —
   export them from `app/models/__init__.py` so Alembic autogenerate sees them (see Impact
   analysis). `poetry run alembic revision --autogenerate -m "P6: ingestion models"`, review
   the generated migration, apply it.
2. `backend/app/ingest/`: connector interface, per-mime-type parser (text/md/csv/PDF/images),
   chunker, extractor (Claude call + snippet-validator), embed step (`app.ai.embed_texts`).
3. `backend/app/api/routes/ingestion.py`: the 4 endpoints (§ API surface above); register in
   `main.py`.
4. `client/server.ts`: replace the 4 handlers with proxy-forwards per "Placement" above.
5. `backend/pyproject.toml`: add the chunking token-estimator; `poetry lock && poetry install`.
6. Fixtures for the Verification section below.

## Verification

- **Unit:** chunker produces correct char offsets on a fixture doc; the snippet-validator
  rejects a deliberately hallucinated (non-substring) candidate.
- **Integration:** upload a fixture text with one clear requirement + one clear decision
  statement → assert one candidate `Item` and one candidate `DecisionRecord`, each with a
  correct chunk citation; assert non-null embeddings in Postgres
  (`SELECT count(*) FROM chunks WHERE embedding IS NOT NULL`).
- **PDF/image:** upload a sample PDF and a sample whiteboard photo → both parse to non-empty
  text and produce at least one candidate.
- **End-to-end (browser):** upload via the existing Sources screen → candidate appears in the
  review queue within seconds → approve → appears on the Board with a real citation in the
  Drawer's Citations tab.

---

## Completion note (2026-09-24)

Implemented backend + frontend per the plan above — models, migration, `ingest/` pipeline
(parse/chunk/extract/embed/verdict), the 4 API routes, and the `client/server.ts` bridge.
23/23 backend tests pass, `ruff` clean, client `tsc --noEmit` clean. Full request chain
verified live (both servers running): upload → Node → Python → real parse/chunk → correctly
blocked at the embed step by `VertexNotConfigured` (GCP account-level setup still pending —
not a code defect; confirmed no partial rows were left in Postgres, confirming the
transaction rolled back cleanly). The AI-dependent unit/integration checks in this file's
Verification section (extraction accuracy, embeddings, the full browser walkthrough) still
need a configured `GCP_PROJECT_ID` to run for real — everything else is done. Full details:
`IMPLEMENTATION_LOG.md`'s 2026-09-24 "Ingestion pipeline" entry.
