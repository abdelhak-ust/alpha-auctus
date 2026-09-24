# Nexus backend

FastAPI + Postgres(pgvector) + arq/Redis backend for Nexus (the merged
Nexus/Alpha Auctus product — see `/ui_ux_design.md` and `/architecture.md`
at the repo root, and the phased build plan referenced in this session).

This is **phase P0 (foundation)**: the real backend substrate, exposing only
a health/readiness check today. `client/` still talks to `client/server.ts`
during the transition — nothing here is wired into the frontend yet.

## Layout

```
app/
  main.py          FastAPI app entrypoint
  config.py        settings (env / .env via pydantic-settings)
  db/              async SQLAlchemy engine/session + declarative Base
  api/routes/       HTTP routes (health today; P1+ adds tasks/contracts/etc.)
  models/           ORM models — empty until P1 (Task Contract)
  schemas/          Pydantic request/response schemas (mirrors client/src/types.ts)
  ai/               AI provider adapter (Claude + embeddings, BYO-key)      — P1+
  ingest/           ingestion pipeline (connectors -> parse -> embed)        — P6
  engine/           conflict & dedup engine (hero #1)                       — P5
  contracts/        Task Contract drafting + agent-readiness scorer         — P1
  validate/         requirement-validation engine (hero #2, the wedge)      — P2
  runner/           agent sandbox + execution (Claude Code)                 — P3
  mcp/              MCP server (agent's two-way interface)                  — P3
  github_app/       GitHub App (PR/CI/deploy)                               — P4
  registry/         human+agent registry, capacity, learning                — P8
  ws/               websocket manager (live verdicts + live run activity)   — P3
  queue/            async background jobs (arq)                             — P0+
migrations/         Alembic
tests/
```

Each empty package's `__init__.py` docstring says which plan phase fills it in.

## Setup

Requires: Python 3.13, [Poetry](https://python-poetry.org/), local Postgres 16
running, local Redis running.

```bash
cd backend
poetry install
cp .env.example .env   # defaults already point at nexus_dev / local redis
```

### Database

A local dev database + pgvector extension are already set up on this
machine:

```bash
createdb nexus_dev
psql -d nexus_dev -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

**Note for this machine specifically:** the Homebrew `pgvector` bottle only
ships prebuilt for postgresql@17/18, but this machine runs postgresql@16.
It was built from source against @16:

```bash
git clone --branch v0.8.6 https://github.com/pgvector/pgvector.git
cd pgvector
export PG_CONFIG=$(brew --prefix postgresql@16)/bin/pg_config
make PG_CONFIG=$PG_CONFIG
make install PG_CONFIG=$PG_CONFIG
```

Migrations (Alembic) will manage schema once P1 adds real models; for now
there's nothing to migrate.

## Run

```bash
poetry run uvicorn app.main:app --reload --port 8000
```

- `GET /api/health` — liveness only.
- `GET /api/health/ready` — verifies DB connectivity and the pgvector extension.
- `GET /docs` — Swagger UI.

## Test

```bash
poetry run pytest
poetry run ruff check .
```
