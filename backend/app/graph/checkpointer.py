"""Process-wide LangGraph Postgres checkpointer.

Uses the same database as the app (`settings.database_url`), but through psycopg 3 — which is
what `langgraph-checkpoint-postgres` requires — so the SQLAlchemy `postgresql+asyncpg://` DSN is
converted to a plain `postgresql://` one. LangGraph is imported lazily so importing
`app.graph` stays cheap (e.g. for the API process).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from app.config import get_settings

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

_saver: AsyncPostgresSaver | None = None
_pool: Any = None
_lock = asyncio.Lock()


def to_psycopg_dsn(database_url: str) -> str:
    """`postgresql+asyncpg://…` (or `+psycopg`) → `postgresql://…` for psycopg 3."""
    scheme, sep, rest = database_url.partition("://")
    if not sep:
        return database_url
    base = scheme.split("+", 1)[0]
    if base == "postgres":
        base = "postgresql"
    return f"{base}://{rest}"


async def get_checkpointer() -> AsyncPostgresSaver:
    """Return the process-wide `AsyncPostgresSaver`, creating its tables (`setup()`) once."""
    global _saver, _pool
    if _saver is not None:
        return _saver
    async with _lock:
        if _saver is not None:
            return _saver

        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=to_psycopg_dsn(get_settings().database_url),
            max_size=10,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            open=False,
        )
        await pool.open()
        saver = AsyncPostgresSaver(pool)
        try:
            await saver.setup()
        except BaseException:
            await pool.close()
            raise
        _pool, _saver = pool, saver
        return saver


async def close_checkpointer() -> None:
    """Close the checkpointer's connection pool (worker shutdown / tests)."""
    global _saver, _pool
    pool, _saver, _pool = _pool, None, None
    if pool is not None:
        await pool.close()
