---
name: nexus-new-phase
description: Scaffold a new Nexus backend phase (P1-P9) — models, schemas, API routes, tests — following the conventions already established in backend/app/, and update the build plan's status. Use when starting implementation of any phase from the plan.
---

# nexus-new-phase

Args: the phase id (e.g. `P1`, `P5`) or a short name (e.g. "conflict engine").

## 1. Ground it in the plan first

1. Open `.claude/plans/we-want-nexus-to-sorted-shell.md`.
2. Read the phase's row in the §4 phased-plan table (goal, depends-on, backend/frontend
   scope, key files) and, if it exists, its own detailed section (e.g. §5 for Ingestion).
3. Confirm the phase's dependencies are actually done (check the "Status" notes in §3/§4) —
   if a listed dependency isn't real yet, say so before scaffolding on top of a mock.
4. If anything about scope is ambiguous, use `nexus-spec` (or read `ui_ux_design.md` /
   `architecture.md` directly) rather than guessing.

## 2. Scaffold, following existing conventions exactly

- **Models** (`backend/app/models/`): SQLAlchemy models via `app.db.base.Base`
  (`DeclarativeBase`), async-compatible. Add an Alembic migration
  (`cd backend && poetry run alembic revision --autogenerate -m "<phase>: <what>"`).
- **Schemas** (`backend/app/schemas/`): Pydantic models that mirror the matching type in
  [client/src/types.ts](client/src/types.ts) field-for-field — this is the API contract the
  frontend already assumes (see the plan's "Key reuse" principle). If a shape doesn't have a
  frontend counterpart yet, check whether it should (most do).
- **Routes** (`backend/app/api/routes/`): one router per resource area, prefixed under
  `settings.api_prefix`, registered in `backend/app/main.py` — follow the pattern in
  `app/api/routes/health.py`.
- **Package docstring**: the phase's package under `backend/app/` already has a docstring
  naming it (e.g. `app/contracts/__init__.py`) — implement inside that package, don't create
  a new one.
- **Tests** (`backend/tests/`): `pytest-asyncio` + `httpx.ASGITransport` against `app.main.app`
  — see `tests/test_health.py` for the exact pattern. Cover the phase's own "Verification"
  bullets from the plan, not just a generic happy path.
- **AI calls**: always through `backend/app/ai/` (Vertex AI — `AnthropicVertex` for
  generation, Vertex embeddings) — never instantiate a provider client directly in a route
  or service.

## 3. Close the loop

1. Run `nexus-verify`.
2. Update the plan file: the phase's row in §4 (and its detailed section, if any) — mark
   what's now real vs. still open, the way §3's "P0 status" note does.
