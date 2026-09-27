# Nexus backend

FastAPI + Postgres + Qdrant + arq/Redis + LangGraph backend for Nexus (the merged
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
  ai/               AI adapter — Gemini via Vertex AI (generate_json, embed_texts)
  vector/           Qdrant client: `features` + `chunks` collections
  graph/            LangGraph Postgres checkpointer + audit_events helper
  ingest/           ingestion pipeline (LangGraph: parse -> chunk -> extract -> consolidate)
  engine/           conflict & dedup engine (hero #1)                       — P5
  contracts/        Task Contract drafting + agent-readiness scorer         — P1
  validate/         requirement-validation engine (hero #2, the wedge)      — P2
  runner/           agent sandbox + execution (Claude Code)                 — P3
  mcp/              MCP server (agent's two-way interface)                  — P3
  github_app/       GitHub App (PR/CI/deploy)                               — P4
  registry/         human+agent registry, capacity, learning                — P8
  ws/               websocket manager (live verdicts + live run activity)   — P3
  queue/            arq jobs: enqueue() + worker.WorkerSettings (ingest_document, readiness_run)
migrations/         Alembic
tests/
```

Each empty package's `__init__.py` docstring says which plan phase fills it in.

## Setup

Requires: Python 3.13, [Poetry](https://python-poetry.org/), local Postgres 16
running, and Qdrant + Redis (via Docker, below).

```bash
cd backend
poetry install
cp .env.example .env   # defaults already point at nexus_dev / local redis
poetry run docling-tools models download   # one-time (needs network): Docling's PDF layout models
```

The Docling model download is required before PDFs can be parsed; without it a PDF upload
ends `failed` with a message telling you to run exactly that command.

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

(pgvector is no longer used by the feature pipeline — vectors live in Qdrant — but the
health check still reports it.)

Apply migrations, and create the separate test database once:

```bash
poetry run alembic upgrade head
createdb nexus_test        # tests never touch nexus_dev
```

The LangGraph checkpointer creates its own `checkpoint*` tables in the same database on
first use (not via Alembic).

### Qdrant + Redis

`docker-compose.yml` at the repo root runs both (data under `backend/data/`, gitignored):

```bash
docker compose up -d            # from the repo root: Qdrant :6333, Redis :6379
```

If a Homebrew Redis is already running on :6379, either use it (skip the compose `redis`
service: `docker compose up -d qdrant`) or stop it first (`brew services stop redis`).

### Vertex AI (Gemini)

Generation and embeddings both go through Gemini on Vertex AI (`google-genai`, ADC auth):

```bash
gcloud auth application-default login
# then in backend/.env: GCP_PROJECT_ID=<your project>, VERTEX_LOCATION=us-central1
```

Without `GCP_PROJECT_ID` every AI call raises `VertexNotConfigured` (API → 503; ingestion
marks the document `failed` with a problem/cause/fix message).

## Run

```bash
poetry run uvicorn app.main:app --reload --port 8000
```

- `GET /api/health` — liveness only.
- `GET /api/health/ready` — verifies DB connectivity and the pgvector extension.
- `GET /docs` — Swagger UI.

The background worker (runs `ingest_document` and the `readiness_run` stub):

```bash
poetry run arq app.queue.worker.WorkerSettings
```

(or the `nexus-worker` config in `.claude/launch.json`). On startup it creates the Qdrant
collections if missing. Uploads are accepted without a worker but stay `pending` until one
runs; if Redis is down the upload API returns 503.

## Test

```bash
poetry run pytest
poetry run ruff check .
```

Tests use `nexus_test` (see `tests/conftest.py`), Qdrant's in-memory mode, and mocked
`app.ai` functions — no network, no Vertex, no running Qdrant/Redis needed.
