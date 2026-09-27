"""LangGraph infrastructure shared by every pipeline graph (ingest, readiness, breakdown).

Filled in by the ingestion stage (plans/ingestion.md §11.1 / §11.3,
plans/feature-pipeline-contract.md §6):

- `get_checkpointer()` — process-wide LangGraph `AsyncPostgresSaver` on the same Postgres
  database as the app (its `checkpoint*` tables are created by `setup()` on first use, not by
  Alembic).
- `record_audit(session, ...)` — one `audit_events` row per graph node transition / decision.

`app.models` never imports this package (it's the other way round).
"""

from app.graph.audit import record_audit
from app.graph.checkpointer import close_checkpointer, get_checkpointer, to_psycopg_dsn

__all__ = ["close_checkpointer", "get_checkpointer", "record_audit", "to_psycopg_dsn"]
