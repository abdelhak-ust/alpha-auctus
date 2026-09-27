"""Shared test fixtures.

Test database
-------------
Tests run against a separate database, `TEST_DATABASE_URL` (default
`postgresql+asyncpg://localhost/nexus_test`, create it once with `createdb nexus_test`), never
`nexus_dev`. `DATABASE_URL` is pointed at it *before* any `app.*` import so the app's own engine
(`app.db.session.engine`) and Alembic's env.py both use it too. Alembic `upgrade head` runs once
per session, the first time a test asks for the DB.

Fixtures (stable — other agents' test files depend on these names)
-------------------------------------------------------------------
- `db_session`: an `AsyncSession` inside an outer transaction that is rolled back after the
  test. Code under test may call `session.commit()` — it only releases a SAVEPOINT — so no rows
  leak between tests (`rollback()` likewise only rolls back to the savepoint).
- `api_client`: an `httpx.AsyncClient` on `app.main.app` (ASGITransport, base_url
  `http://test`) with `get_db` overridden to yield `db_session`, so route writes are visible to
  the test through `db_session` and rolled back afterwards. `app.main` is imported lazily inside
  this fixture — never at module level — so one missing module can't break collection for all.
- Factories `commit()` what they create (in savepoint mode that only releases the savepoint), so
  seeded rows behave like already-committed data: a route's `rollback()` can't wipe them, and
  they are still discarded when the test ends.
- `make_document(**overrides) -> Document`: inserts a `documents` row (unique hash by default).
- `make_feature(**overrides) -> Feature`: inserts a feature + its version 1 and sets
  `current_version_id`. Accepts `description`, `source_refs`, `version_no`, `created_from`.
- `make_source_ref(**overrides) -> dict`: a contract §5 `source_ref` dict (snake_case).

Event loops
-----------
`app.db.session.engine` is a module-level singleton; under pytest each test may run on its own
event loop, and a pooled connection from a previous loop fails with "Future attached to a
different loop". `_fresh_db_pool` disposes the pool before each test. `db_session` uses its own
NullPool engine per test for the same reason.
"""

import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://localhost/nexus_test")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import pool  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db.session import engine  # noqa: E402
from app.models import Document, Feature, FeatureVersion  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db_pool():
    await engine.dispose()
    yield


@pytest.fixture(scope="session")
def _migrated_test_db() -> str:
    """Run `alembic upgrade head` on the test DB once per session."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    try:
        command.upgrade(cfg, "head")
    except Exception as exc:  # DB missing / Postgres down — say how to fix it
        pytest.fail(
            f"Could not migrate the test database at {TEST_DATABASE_URL}: {exc}. "
            "Create it with `createdb nexus_test` (or set TEST_DATABASE_URL).",
            pytrace=False,
        )
    return TEST_DATABASE_URL


@pytest_asyncio.fixture
async def db_session(_migrated_test_db: str) -> AsyncIterator[AsyncSession]:
    test_engine = create_async_engine(_migrated_test_db, poolclass=pool.NullPool)
    async with test_engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            if outer.is_active:
                await outer.rollback()
    await test_engine.dispose()


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession) -> AsyncIterator[Any]:
    from httpx import ASGITransport, AsyncClient

    from app.db.session import get_db
    from app.main import app

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def make_source_ref() -> Callable[..., dict[str, Any]]:
    def _make(**overrides: Any) -> dict[str, Any]:
        ref: dict[str, Any] = {
            "doc_id": str(uuid.uuid4()),
            "doc_type": "upload",
            "chunk_id": str(uuid.uuid4()),
            "section": "1. Overview",
            "char_start": 0,
            "char_end": 42,
            "snippet": "Users can sign in with their work email.",
        }
        ref.update(overrides)
        return ref

    return _make


@pytest.fixture
def make_document(db_session: AsyncSession) -> Callable[..., Awaitable[Document]]:
    async def _make(**overrides: Any) -> Document:
        fields: dict[str, Any] = {
            "project_id": "proj-test",
            "doc_type": "upload",
            "content_hash": uuid.uuid4().hex + uuid.uuid4().hex,  # 64 hex chars, unique
            "filename": "spec.md",
            "mime_type": "text/markdown",
            "ingestion_status": "pending",
        }
        fields.update(overrides)
        doc = Document(**fields)
        db_session.add(doc)
        await db_session.commit()  # seeded rows survive a route's rollback(); see module doc
        return doc

    return _make


@pytest.fixture
def make_feature(
    db_session: AsyncSession, make_source_ref: Callable[..., dict[str, Any]]
) -> Callable[..., Awaitable[Feature]]:
    async def _make(
        *,
        description: str = "Users can sign in with their work email.",
        source_refs: list[dict[str, Any]] | None = None,
        version_no: int = 1,
        created_from: str | None = None,
        **overrides: Any,
    ) -> Feature:
        fields: dict[str, Any] = {
            "project_id": "proj-test",
            "name": "Email sign-in",
            "lifecycle_state": "consolidated",
        }
        fields.update(overrides)
        feature = Feature(**fields)
        db_session.add(feature)
        await db_session.flush()
        refs = source_refs if source_refs is not None else [make_source_ref()]
        version = FeatureVersion(
            feature_id=feature.feature_id,
            version_no=version_no,
            description=description,
            source_refs=refs,
            created_from=created_from or f"ingest:{refs[0]['doc_id'] if refs else 'test'}",
        )
        db_session.add(version)
        await db_session.flush()
        feature.current_version_id = version.version_id
        await db_session.commit()  # seeded rows survive a route's rollback(); see module doc
        return feature

    return _make
