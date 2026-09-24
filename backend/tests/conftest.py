"""Shared test fixtures.

`app.db.session.engine` is a module-level singleton (correct for the real app: one process,
one long-lived event loop, one pooled connection set). Under pytest, each test can end up
running on its own event loop, and a connection checked out under a *previous* test's loop
fails with "Future attached to a different loop" when reused — a well-known SQLAlchemy-async +
pytest-asyncio interaction, not an application bug. Disposing the pool before each test forces
fresh connections bound to whatever loop is current, sidestepping the whole class of failure.
"""

import pytest_asyncio

from app.db.session import engine


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db_pool():
    await engine.dispose()
    yield
