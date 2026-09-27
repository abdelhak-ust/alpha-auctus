"""Async background jobs (arq / Redis) — local dev; deployed environments use Cloud Tasks.

Producers (API routes, graph nodes) enqueue by job **name** only:

    from app import queue
    await queue.enqueue("ingest_document", document_id=..., _job_id=f"ingest_document:{id}")
    await queue.enqueue("readiness_run", feature_id=..., project_id=...)

The worker that runs them is `app.queue.worker.WorkerSettings`
(`poetry run arq app.queue.worker.WorkerSettings`). This module deliberately imports nothing
from `app.ingest` / `app.api` so any layer can enqueue without import cycles
(plans/ingestion.md §11.3).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.config import get_settings

logger = logging.getLogger(__name__)

JOB_NAMES = ("ingest_document", "readiness_run")

_pool: ArqRedis | None = None
_lock = asyncio.Lock()


class QueueUnavailable(RuntimeError):
    """Redis (the arq broker) can't be reached — the API maps this to 503."""

    def __init__(self, cause: str = ""):
        detail = f" ({cause})" if cause else ""
        super().__init__(
            f"The job queue is unavailable: can't reach Redis at {get_settings().redis_url}"
            f"{detail}. Start Redis (`docker compose up -d redis` from the repo root) and "
            "the worker (`poetry run arq app.queue.worker.WorkerSettings`), then retry."
        )


def redis_settings(*, conn_retries: int = 5) -> RedisSettings:
    """arq RedisSettings from `settings.redis_url`."""
    rs = RedisSettings.from_dsn(get_settings().redis_url)
    rs.conn_retries = conn_retries
    return rs


async def _get_pool() -> ArqRedis:
    global _pool
    if _pool is not None:
        return _pool
    async with _lock:
        if _pool is None:
            # Fail fast on the request path: no connection retries.
            _pool = await create_pool(redis_settings(conn_retries=0))
        return _pool


async def reset_pool() -> None:
    """Close and forget the cached Redis pool (tests / after a connection failure)."""
    global _pool
    pool, _pool = _pool, None
    if pool is not None:
        try:
            await pool.aclose()
        except Exception:  # noqa: BLE001 — best effort on an already-broken connection
            pass


async def enqueue(job_name: str, **kwargs: Any) -> str | None:
    """Enqueue `job_name` with `kwargs`; returns the job id, or `None` when a job with the same
    `_job_id` already exists (arq de-duplicates). Raises `QueueUnavailable` if Redis is down."""
    if job_name not in JOB_NAMES:
        raise ValueError(f"Unknown job {job_name!r}; registered jobs: {', '.join(JOB_NAMES)}.")
    try:
        pool = await _get_pool()
        job = await pool.enqueue_job(job_name, **kwargs)
    except (OSError, ConnectionError, TimeoutError) as exc:
        await reset_pool()
        raise QueueUnavailable(str(exc)) from exc
    except Exception as exc:
        # redis-py's ConnectionError/TimeoutError don't subclass the builtins.
        from redis.exceptions import ConnectionError as RedisConnectionError
        from redis.exceptions import TimeoutError as RedisTimeoutError

        if isinstance(exc, RedisConnectionError | RedisTimeoutError):
            await reset_pool()
            raise QueueUnavailable(str(exc)) from exc
        raise
    if job is None:
        logger.info("enqueue %s: job %s already queued", job_name, kwargs.get("_job_id"))
        return None
    return job.job_id


__all__ = ["JOB_NAMES", "QueueUnavailable", "enqueue", "redis_settings", "reset_pool"]
