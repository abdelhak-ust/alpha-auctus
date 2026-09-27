---
feature: Chat-orchestrated project workflow
phase: MVP
status: done
created: 2026-09-27
completed: 2026-09-27
note: automated verify passed (pytest 58, ruff, tsc, npm test 37). Live review API exercised after alembic d7f1c4e82b19. Browser path was not driven — no preview tool; browser MCP tabs did not stay open.
---

# Chat-orchestrated project workflow

> Branch `mpv_v01`. Replaces the tab-hopping Sources → Features → Tasks → Board path
> with Chat as the orchestrator. Existing tabs remain inspection surfaces.

## Spec gap

`ui_ux_design.md` §4.10–4.11 still specifies: New Project takeover → generic clarification
chat → task generation → verdict queue → Board. That chat was hardcoded and not wired to
MVP ingestion. This feature is an **approved spec gap** of the same class as the MVP
Features view: keep design tokens and existing components; Chat is now the workflow.

Non-negotiables stay: cite or stay silent; questions are never auto-answered; tasks reach
the board only on an explicit human click (bulk “Add N to board” counts).

**Product rule:** a feature cannot be approved for task generation while it has open
questions. Approve is disabled in the UI and `PATCH reviewStatus: approved` returns 409
until every question is answered or skipped.

## What landed

- **Backend:** `features.review_status` (`pending|approved|rejected`), `PATCH /features/{id}`,
  `POST /clarification/skip-remaining`, `GET /workflow`, `chat_messages.kind`
  (`progress|decision|question|text`). Reject does not start the task graph.
- **Frontend:** New Project skips `ClarificationChat` and lands on Chat. `ProjectChat` +
  `ChatBlocks` + `WorkflowStepper` + `FeatureCards`. Generation mode lives in client
  `sessionStorage` only.

## Verification (from the build plan)

Automated contract tests and typecheck passed. Live 409 / skip / approve / reject / workflow
history confirmed on `nexus_dev` after `alembic upgrade head`. Full browser walkthrough was
not run in the verify session.

---

**Completed 2026-09-27.** Implemented on `mpv_v01`. See
[IMPLEMENTATION_LOG.md](../IMPLEMENTATION_LOG.md) 2026-09-27 — Chat-orchestrated project workflow.
