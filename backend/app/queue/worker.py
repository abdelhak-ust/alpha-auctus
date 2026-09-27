"""arq worker entrypoint: `poetry run arq app.queue.worker.WorkerSettings` (from backend/).

Jobs are registered by name (plans/ingestion.md §11.3); `ingest_document` is imported by string
path from `app.ingest.jobs` (owned by the pipeline), so only the worker process pulls in
Docling/LangGraph.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from arq.worker import func

from app.graph import close_checkpointer
from app.queue import redis_settings
from app.queue.jobs import readiness_run
from app.vector import ensure_collections

logger = logging.getLogger(__name__)


async def on_startup(ctx: dict[str, Any]) -> None:
    await ensure_collections()
    logger.info("nexus worker: Qdrant collections ready")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await close_checkpointer()


class WorkerSettings:
    functions: ClassVar[list] = [
        func("app.ingest.jobs.ingest_document", name="ingest_document"),
        func(readiness_run, name="readiness_run"),
    ]
    redis_settings = redis_settings()
    on_startup = on_startup
    on_shutdown = on_shutdown
    # Ingestion is LLM-bound; keep concurrency modest so Vertex quotas hold.
    max_jobs = 4
    job_timeout = 60 * 30
    keep_result = 60 * 60
