# Architecture: Decision Memory Layer

One product, all capabilities together. This document describes the full system
as a single cohesive whole — not a build order. Staging (which slice ships
first) is deliberately out of scope here; see the design doc's "Approaches" for
that.

Source of truth for product intent:
`/Users/abdelhak/.gstack/projects/unicorn/abdelhak-unknown-design-20260601-161532.md`

## What the product is

An AI **Decision Memory Layer** for messy, multi-stakeholder projects. It ingests
every project input (tasks, docs, meeting transcripts, feedback, tickets),
maintains a living memory of items AND decisions, and answers the four expensive
judgment questions on top of a frictionless surface:

1. Is this **new**, a **duplicate**, or does it **conflict** with a past decision?
2. What does this task mean / depend on / why was it decided? (ask-a-task)
3. What does this change **impact** — and what should we **deprecate**?
4. What's the **priority**, and can you **author** the BRD / spec / task tree?

It is **not** a task tracker. The tracking surface is a commodity; the memory and
conflict reasoning are the defensible core.

## Locked architectural decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Primary surface | **Kanban board, spreadsheet-easy** — a standalone web app whose home is a dead-simple board (open/add/move a card in ~1s). Heavy views (impact graph, authoring) are additional panes in the same app. Spreadsheet/CSV import + optional two-way sync is an ingestion connector, not the home. |
| D2 | Memory core | **Hybrid** — structured Decision Records (atomic normalized statements + affected entities/areas) in a relational store, **plus** a vector index over items and decision statements for candidate retrieval, **plus** entity/area tags for impact reasoning. LLM does final contradiction classification over retrieved candidates. |
| D3 | Data posture | **BYO-key + no-retention seam as a first-class mode** — pluggable LLM/embeddings endpoint (tenant may supply key/region), strict tenant isolation, no raw content retained outside the tenant's own store, full audit log. A managed default is offered for the no-procurement beachhead. |

## Architectural principles (derived from the constraints)

- **Frictionless or dead.** The surface must feel like a spreadsheet-grade Kanban:
  open, add, move a card in ~1 second, zero structure to learn. Any feature that
  forces structure onto the user is pushed to the background and made optional.
- **Never silently miss a conflict.** A confident false-positive kills the demo
  slower than a silent miss kills trust. The engine surfaces ranked candidate
  matches for human confirmation rather than asserting one answer.
- **Conflict ≠ dedup.** Logical contradiction detection is a *separate* retrieval
  and reasoning path from semantic dedup, because a contradiction can be
  semantically near OR far. They share a pipeline shape, not an assumption.
- **Memory is the moat.** Every ingested artifact and every decision is captured
  with provenance so the system can always cite *why* it said something.
- **Data stays the tenant's.** BYO-key/no-retention is a seam designed in from the
  start, because it's painful to retrofit and it's exactly what unblocks the
  enterprise customer.
- **Cite or stay silent.** Every verdict points to a specific row/decision (by ID
  for structured items; by source doc + quoted snippet for free text). No
  citation ⇒ verdict is "net-new (no match)."

## System context

```
            ┌────────────────────────────────────────────────────────┐
            │                      USERS                              │
            │   Project / tech lead · engineer · consultant           │
            └───────────────┬───────────────────────┬────────────────┘
                            │ (frictionless)         │ (queries / authoring)
                            ▼                         ▼
   ┌─────────────┐   ┌──────────────────────────────────────────────┐
   │  INGESTION  │   │            DECISION MEMORY LAYER              │
   │  SOURCES    │──▶│  (this product — one cohesive system)        │
   │             │   │                                              │
   │ docs/PDFs   │   │  Surface · Ingestion · Memory Core ·         │
   │ transcripts │   │  Conflict Engine · Query · Authoring         │
   │ email/fdbk  │   └───────────────┬──────────────────────────────┘
   │ tickets     │                   │
   │ spreadsheets│                   ▼
   └─────────────┘   ┌──────────────────────────────────────────────┐
                     │   EXTERNAL AI (pluggable / BYO-key)          │
                     │   LLM (Claude) · Embeddings provider         │
                     └──────────────────────────────────────────────┘
```

## Layered component architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. SURFACE LAYER  (web app — spreadsheet-easy Kanban)                 │
│     Board view · Card detail · Verdict inbox · Impact graph pane ·     │
│     Ask-a-task chat · Authoring pane · Spreadsheet/CSV import+sync     │
└───────────────┬───────────────────────────────────────────────────────┘
                │  REST/GraphQL + websocket (live verdicts)
┌───────────────▼───────────────────────────────────────────────────────┐
│  2. APPLICATION / ORCHESTRATION LAYER                                  │
│     API gateway · Auth & tenant isolation · Job queue ·               │
│     Capability services (see §"Capabilities → components")            │
└───────┬───────────────────────┬───────────────────────┬───────────────┘
        │                       │                       │
┌───────▼────────┐   ┌──────────▼──────────┐   ┌────────▼───────────────┐
│ 3a. INGESTION  │   │ 3b. CONFLICT & DEDUP│   │ 3c. REASONING SERVICES │
│     PIPELINE   │   │     ENGINE  (core)  │   │  ask-a-task · impact · │
│  parse·chunk·  │   │  candidate retrieval│   │  prioritize · author · │
│  extract·embed │   │  + LLM classify     │   │  deprecate             │
└───────┬────────┘   └──────────┬──────────┘   └────────┬───────────────┘
        │                       │                       │
┌───────▼───────────────────────▼───────────────────────▼───────────────┐
│  4. MEMORY CORE  (hybrid store)                                        │
│   Relational: Items · DecisionRecords · Entities · Sources · Verdicts │
│   Vector index: item & decision-statement embeddings                  │
│   Tags/edges: entity↔item↔decision (impact graph)                     │
└───────────────┬───────────────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────────────┐
│  5. AI PROVIDER ADAPTER  (pluggable — BYO-key / no-retention)          │
│     LLM adapter · Embeddings adapter · prompt+citation contracts       │
└────────────────────────────────────────────────────────────────────────┘
```

## Capabilities → components

All 8 capabilities from the vision map onto the layers above. None is a separate
app; each is a service over the shared Memory Core.

| # | Capability | Primary component(s) | Reads/writes |
|---|------------|----------------------|--------------|
| 1 | Frictionless surface | Surface Layer (Kanban) | Items |
| 2 | Conflict & dedup engine *(the wedge)* | Conflict & Dedup Engine + Memory Core | Items, DecisionRecords, Verdicts |
| 3 | Ask-a-task | Reasoning Services (query) + Memory Core | Items, Decisions, Sources |
| 4 | Multi-source ingestion | Ingestion Pipeline | Sources → Items/Decision candidates |
| 5 | Impact analysis | Reasoning Services (impact) over entity/edge graph | Entities, edges |
| 6 | Prioritization | Reasoning Services (prioritize) | Items, Verdicts, frequency signals |
| 7 | Authoring (BRD/spec/task tree) | Reasoning Services (author) | Decisions, Items, Sources |
| 8 | Deprecation suggestions | Reasoning Services (deprecate) | Items, Decisions, edges |

## Core data model

The hybrid memory is the heart. Minimal entity set:

```
Source            an ingested artifact (doc, transcript, email, ticket, sheet row)
  id, tenant_id, type, title, raw_ref (tenant-owned blob), ingested_at, checksum

Item              a task / requirement / feedback unit on the board
  id, tenant_id, title, body, status(column), source_id?, entity_tags[],
  embedding_ref, created_at, created_by, assignee(human handle or `agent:<id>`)

DecisionRecord    an atomic, normalized decision statement (the conflict anchor)
  id, tenant_id, statement (canonical "we will / will not X"), polarity,
  affected_entities[], source_id, decided_at, decided_by, supersedes_id?,
  status(active|superseded|deprecated), embedding_ref

Entity            a feature / area / component the project talks about
  id, tenant_id, name, aliases[]                 (drives impact + tagging)

Agent             an assignable AI agent (workspace-wide catalog, shared across projects)
  id, tenant_id, name, kind(design|code|qa|docs|test|security|custom), builtin

Edge              typed relation for the impact graph
  from(Item|Decision|Entity), to(Item|Decision|Entity),
  type(affects|depends_on|contradicts|duplicates|supersedes)

Verdict           the engine's output for a new item
  id, tenant_id, item_id, verdict(net_new|duplicate|conflict|impact),
  citations[{target_id, kind, snippet, score}], confidence, confirmed_by?
```

Key idea: a **DecisionRecord** is *not* the same row as the **Item** it came from.
Decisions are extracted and normalized into atomic, polarity-bearing statements
("we will NOT support offline mode") so the engine can reason about contradiction
independently of how the original text was phrased. This is what makes
conflict-detection tractable where pure similarity fails.

An **Item.assignee** is either a human handle or an `agent:<id>` reference into the
**Agent** catalog. That catalog is **workspace-level** (shared across projects, like the
AI/data posture in D3), seeded with built-in agents; users may add or remove custom ones.
Agents are assignment targets only — no agent execution is modeled here (see the deferral
note in the UI spec). Assignment lives in the commodity surface (capability 1), not the
memory core.

## The Conflict & Dedup Engine (the core, detailed)

This is the de-risking heart of the product. Two retrieval paths feed one
classifier, because dedup and logical-conflict have different retrieval physics.

```
NEW ITEM (typed on board, or extracted from an ingested source)
   │
   ├─ normalize → atomic statement(s) + entity tags  (LLM extract)
   │
   ▼
 ┌──────────────── candidate retrieval (parallel) ────────────────┐
 │                                                                 │
 │  PATH A — DEDUP            PATH B — CONFLICT                     │
 │  semantic similarity over │  union of:                          │
 │  existing Items           │   • vector kNN over DecisionRecord  │
 │  (vector kNN)             │     statements (near contradictions)│
 │                           │   • entity-tag match → all decisions │
 │                           │     touching the same entity/area    │
 │                           │     (catches semantically-FAR        │
 │                           │      contradictions similarity misses)│
 └──────────────┬────────────┴───────────────┬─────────────────────┘
                │  top-K dedup cands          │  top-K conflict cands
                ▼                             ▼
        ┌───────────────────────────────────────────────┐
        │   LLM CLASSIFIER  (one structured call)        │
        │   input: new statement + both candidate sets   │
        │   output: verdict ∈ {net_new, duplicate,       │
        │           conflict, impact} + citations +      │
        │           confidence, per candidate            │
        └───────────────────┬───────────────────────────┘
                            ▼
              ┌─────────────────────────────┐
              │  VERDICT INBOX (human-in-loop)│
              │  shows TOP-3 ranked candidates│
              │  user confirms / dismisses    │
              └─────────────┬───────────────┘
                            ▼
            confirmed verdict → writes Edge(s) + updates Verdict
            (duplicate→merge suggestion; conflict→link+flag;
             supersede→mark DecisionRecord superseded)
```

Why two paths, not one: dedup is "are these the same intent?" (similarity is
sufficient). Conflict is "does this contradict a decision?" — and a contradiction
can be worded so differently that kNN never surfaces it. **Path B's entity-tag
join is the safety net** that turns "we decided NOT to do X for area Y" into a
retrievable candidate whenever a new item touches area Y, regardless of wording.

Accuracy posture: optimize recall on conflicts ("never silently miss"), present
ranked top-3 for confirmation, and treat a confident false-positive as the worse
demo failure. Confidence below a threshold ⇒ surface as "possible conflict, please
review," never auto-resolve.

## Ingestion pipeline

```
SOURCE (doc · transcript · email · ticket · sheet)
   │
   ▼  connectors (upload, email-forward inbox, transcript webhook, CSV/Sheets sync)
 parse  ──▶  chunk  ──▶  extract  ──▶  embed  ──▶  write Memory Core
                          │                          │
                          ├─ candidate Items         ├─ Items + embeddings
                          └─ candidate DecisionRecords└─ DecisionRecords + tags
                             (atomic statements,
                              entity tags, provenance)
   │
   └─ every extracted candidate Item is routed through the Conflict & Dedup
      Engine before it lands → ingestion is dedup/conflict-checked, not a dumb
      import. (This is what stops the "messy spreadsheet" failure mode.)
```

One memory, many sources. Each chunk keeps `source_id` + offset so every
downstream verdict, answer, or authored doc can cite the exact origin snippet.

## Reasoning services (capabilities 3, 5, 6, 7, 8)

All are retrieval-augmented LLM services over the same Memory Core; none holds its
own private store.

- **Ask-a-task (3):** retrieve the Item + its Edges + originating Source snippets +
  related DecisionRecords → LLM answers "what is it / what it depends on / why
  decided," with citations.
- **Impact analysis (5):** given a change, traverse `affects`/`depends_on` Edges
  from the touched Entities → list affected Items + contradicted Decisions. Graph
  traversal first, LLM to explain second.
- **Prioritization (6):** rank incoming Items by frequency of the same theme
  (cluster via embeddings), weight, and conflict/impact signals from Verdicts.
- **Authoring (7):** assemble accumulated Decisions + Items + Source snippets for a
  scope → LLM drafts BRD / tech spec / task tree, every claim cited back to a
  Decision or Source.
- **Deprecation (8):** find Items/Decisions superseded by newer Decisions
  (`supersedes` edges) or with no recent activity touching their Entities → suggest
  retirement.

## Data handling & deployment posture (D3)

```
                 ┌──────────────────────────────────────────┐
                 │  TENANT BOUNDARY (per customer, isolated) │
                 │                                          │
   user data ───▶│  Memory Core (tenant DB + vector + blob) │
                 │            │                             │
                 │            ▼                             │
                 │   AI Provider Adapter ──┐                │
                 └─────────────────────────┼────────────────┘
                                           │
                       ┌───────────────────┴───────────────────┐
                       │  Managed mode: our LLM/embeddings key  │  (beachhead)
                       │  BYO mode: tenant's key + region,      │
                       │            no-retention contract,      │  (enterprise)
                       │            no raw content persisted    │
                       │            outside tenant store        │
                       └────────────────────────────────────────┘
```

- Pluggable adapter means the LLM/embeddings endpoint is configuration, not code —
  a tenant can point at their own key/region.
- No raw project content is retained outside the tenant's own store; provider calls
  are no-retention where the provider supports it.
- Full audit log of every AI call (what was sent, which verdict, who confirmed).
- **Validation-phase constraint (carried from the design doc):** until this posture
  is real and reviewable, demos use **anonymized, synthetic, or the founder's own
  self-owned data — never a client's real confidential backlog.**

## Suggested tech stack (cold read — not load-bearing)

- **Surface:** web app (React/TypeScript), Kanban built for ~1s add/move; CSV +
  Google Sheets / Excel sync as a connector.
- **App layer:** typed API (TypeScript/Node or Python/FastAPI), background job
  queue for ingestion + classification.
- **Memory Core:** Postgres (Items, Decisions, Entities, Edges, Verdicts) +
  `pgvector` (or a managed vector store) for embeddings. Postgres-native keeps the
  hybrid store in one system early.
- **AI adapter:** Claude for extraction/classification/authoring; an embeddings
  provider (e.g. Voyage/OpenAI) behind the adapter interface.

## Cross-cutting concerns

- **Failure modes & responses:**
  - *Silent conflict miss* → mitigated by Path B entity-tag retrieval + recall-first
    ranking + human confirmation inbox.
  - *Confident false positive* → present top-3 ranked, never single-assert; confidence
    gating.
  - *Decision history outgrows context window* → retrieval (vector + tag join) bounds
    what reaches the LLM; never "stuff all decisions into one prompt."
  - *Bad extraction* (wrong atomic statement) → provenance + human confirm; extraction
    is reviewable, not silently trusted.
  - *Provider outage / cost spike* → adapter isolates provider; queue + retry; degrade
    to "needs review" rather than wrong auto-verdict.
- **Observability:** per-verdict trace (candidates retrieved, prompt, scores,
  confirmation) — needed both for trust and for tuning the conflict recall.

## Test strategy

- **Conflict-vs-dedup is the first experiment, tested separately.** Build a labeled
  set: pairs that are (a) duplicates, (b) true logical conflicts — some semantically
  near, some far — (c) same-area-no-conflict, (d) net-new. Measure recall on (b)
  *especially the semantically-far ones*, since that's where vector-only fails.
- **Bounded harness for validation:** backlog ≤200 reasonably-clean items;
  scale/noise (800 messy rows) explicitly out of scope until the core lands.
- **Golden-path UI test:** add a card in ~1s; paste an item that conflicts with a
  seeded decision → top-3 inbox surfaces the right decision with a cited snippet.
- **Ingestion test:** one source type end-to-end (transcript → extracted decisions →
  conflict-checked → board), with citations back to the transcript offset.
- **Data-posture test:** BYO-key mode routes calls through the tenant endpoint; audit
  log records every call; no raw content written outside the tenant store.

## Open architectural risks (carried forward)

- Conflict-detection **recall on semantically-far contradictions** is the make-or-break
  unknown — the entity-tag join is the bet; it must be validated, not assumed.
- Atomic-statement **extraction quality** gates everything downstream.
- **Minimum project-history size** before conflict-detection is useful (defines who is
  a "ready" customer) is still open.
- If the spreadsheet/Sheets sync becomes the main surface, **value capture as a tenant
  on Google/Microsoft** needs a pricing answer.
