---
feature: Feature pipeline shared contract (ingestion → registry → task generation)
phase: P6
status: draft
created: 2026-09-26
completed:
---

# Feature pipeline — shared contract

The three pipeline plans are the new standard (owner decision, 2026-09-26):

1. [`ingestion.md`](ingestion.md) — documents → **Feature Registry** (deduplicated, versioned, cited).
2. [`FEATURE_REGISTRY.md`](FEATURE_REGISTRY.md) — registry feature → **dev-ready** via the clarification chat.
3. [`Devevloper_tasks_factory.md`](Devevloper_tasks_factory.md) — dev-ready feature → **developer tasks**.

This file is the single definition of what flows between them. If a plan disagrees with this
file, this file wins and the plan is the one to fix.

## 1. Stack (all three stages)

| Concern | Choice |
| --- | --- |
| Canonical records | Postgres (features, versions, readiness, tasks, audit, LangGraph checkpoints) |
| Vectors | **Qdrant** — collections `features`, `chunks`, `historical_tasks`; every payload carries `project_id` |
| LLM + embeddings | **Gemini via Vertex AI**, one shared client in `backend/app/ai/` (ADC auth, no API keys) |
| Orchestration | **LangGraph** — three graphs: `ingest`, `readiness`, `breakdown`; deterministic steps are plain nodes |
| Code location | `backend/app/<package>/` per CLAUDE.md (`ingest/`, `readiness/`, `tasks/`), tests in `backend/tests/` |

## 2. The Feature record (owned by ingestion, extended downstream)

```
features
├── feature_id (stable UUID)            ← also the Qdrant point id in `features`
├── project_id
├── name
├── current_version_id
├── lifecycle_state                     (§3)
├── classification jsonb                ← written by registry (Router/Classifier)
├── readiness jsonb                     ← written by registry: fields{}, open_gaps[], schema_version
├── override jsonb                      ← {applied, by, reason, unresolved_fields[]}
├── created_at / updated_at

feature_versions
├── version_id
├── feature_id (FK)
├── version_no (int, monotonic)         ← the factory's `spec_version`
├── description                         ← the registry's `raw_description`
├── source_refs [source_ref]            (§5)
├── created_from (ingest:<doc_id> | chat:<doc_id> | manual:<user_id>)
├── created_at

feature_relations                        ← the only feature-to-feature relation table
├── feature_id_a, feature_id_b
├── relation_type (depends_on | extends | conflicts_with)
```

Rules:
- The factory's former `business_goal`, `target_persona` and `constraints` are **readiness schema
  fields**, not columns.
- The registry's `dependencies_on_other_features` and the factory's `feature.dependencies` are
  read from `feature_relations (depends_on)`.

## 3. One lifecycle (`features.lifecycle_state`)

```
extracted → consolidated ─┬─▶ classified → assessing ⇄ awaiting_answers → answered ─┐
            conflicted ◀──┘                     │                                    │
   (blocked until a human                        ├─▶ dev_ready ──┐                   │
    resolves; resolution =                       └─▶ overridden ─┤  ◀────────────────┘
    new version → consolidated)                                  ▼
                                               in_breakdown → needs_review → broken_down
any state after consolidated ── new feature_version ──▶ stale → (re-enters classified)
```

| Handoff | Trigger | Owner |
| --- | --- | --- |
| ingestion → registry | feature reaches `consolidated` | ingest graph enqueues a `readiness` run |
| registry blocked | feature is `conflicted` | human resolves in the review queue |
| registry → factory | feature reaches `dev_ready` or `overridden` | readiness graph enqueues a `breakdown` run |
| re-run | new `feature_version` (ingestion UPDATE, chat answer, manual edit) | sets `stale`; if tasks exist, factory runs diff-aware regeneration |

## 4. Versioning

- A new `feature_versions` row is the **only** way a feature's content changes. That covers an
  ingestion UPDATE, conflict resolution, an extracted chat answer, and a manual edit.
- The factory's `feature_spec_version` on each task = `version_no` it was generated from.

## 5. Citations — `source_ref`

```json
{ "doc_id": "doc_…", "doc_type": "upload | chat | …", "chunk_id": "chk_…",
  "section": "2.3 Auth", "char_start": 1042, "char_end": 1180, "snippet": "…" }
```

- Chat answers are stored as documents with `doc_type: "chat"` (one per reply), chunked like any
  other doc. So a readiness field's `source` is always a `source_ref` (or `"inherited"`), never a bare
  `chat:msg_204` string.
- Chain: **task AC → readiness field or description sentence → source_ref → chunk offset**. No
  source_ref ⇒ the claim is not made (CLAUDE.md "cite or stay silent").
- Rendered in the UI through the existing `VerdictDetail.citation` / `sourceSnippet` shapes
  (`client/src/types.ts`).

## 6. Shared LangGraph conventions

- One Postgres checkpointer for all three graphs, with thread id = `feature_id` (plus
  `document_id` for ingest). This is also the per-feature lock: one active run per feature.
- One append-only `audit_events` table `{ts, project_id, feature_id, graph, node, type, detail}`.
  It replaces the registry's `audit_trail[]` and the factory's audit log.
- Human steps are LangGraph `interrupt`s: conflict resolution, answering questions, override, and
  task-set approval.
- Loop caps come from one config: `max_question_rounds` (registry, 5) and `max_critic_loops`
  (factory, 2).
- Graphs never call each other directly. They hand off through §3 lifecycle transitions plus a
  queued job.

## 7. Non-negotiables applied

- **Human is the final approver:** no auto-resolve of conflicts, no auto-override, no auto-publish.
- **Never silently miss / never cry wolf:** low-confidence items (completeness-sweep leftovers,
  below-threshold readiness fields, low-confidence estimates) surface tinted "please review" and are
  excluded from bulk actions.
- **Tier names:** readiness field tiers are `blocking | planning | optional`, so they never collide
  with board `Priority 'P0'..'P3'`.

## 8. Decisions

Resolved (owner, 2026-09-26):
- **Features only — no DecisionRecord extraction** in ingestion. Conflict detection in this
  pipeline is feature-vs-feature (ingestion §6/§7). The board's decision-conflict verdicts
  (architecture.md Path B) are out of this pipeline's scope and stay as they are today.
- **Feature is a new entity** (`features` / `feature_versions` / `feature_relations`, §2). The
  architecture's `Entity` stays the lightweight area/component tag.
- **Human review = the existing review queue** (ingest review queue / Verdicts inbox,
  `VerdictRow.tsx`), for both ingestion conflicts and generated-task approval. No new screen.
- **The frontend calls `backend/` directly** for pipeline endpoints (no Node proxy). This
  needs CORS on the FastAPI app for the dev origin (`http://localhost:3000`) and a backend base
  URL for the client (Vite env, e.g. `VITE_BACKEND_URL=http://localhost:8000`). Board data
  endpoints stay on `client/server.ts`.

Still open:
1. Task publishing target: Nexus board only (master plan: Jira read-only, two-way sync out), or
   also Jira / Linear / Azure DevOps. *(Needed before stage 3.)*
2. Board Items: stay in Node SQLite (`client/db/`) for now, with approved tasks written through the
   Node API, or move Items to Postgres as part of this pipeline. *(Needed before stage 3.)*
