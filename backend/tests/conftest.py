"""Shared test fixtures.

Test database
-------------
Tests run against `TEST_DATABASE_URL` (default `postgresql+asyncpg://localhost/nexus_test`).
`DATABASE_URL` is pointed at it *before* any `app.*` import. Alembic `upgrade head` runs
once per session.

Fixtures
--------
- `db_session`: AsyncSession inside an outer transaction rolled back after the test.
- `api_client`: httpx.AsyncClient on `app.main.app` with `get_db` overridden.
- `make_document` / `make_feature`: MVP factories (commit so route rollbacks keep them).
- Graph nodes share `db_session` via `set_session_factory` (autouse).
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

from app.db.session import engine, set_session_factory  # noqa: E402
from app.models import Document, Feature, FeatureQuestion, Task  # noqa: E402
from tests.fakes import ReuseSession  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest_asyncio.fixture(autouse=True)
async def _fresh_db_pool():
    await engine.dispose()
    yield


@pytest.fixture(scope="session")
def _migrated_test_db() -> str:
    from alembic import command
    from alembic.config import Config

    versions = BACKEND_DIR / "migrations" / "versions"
    for sidecar in versions.glob("._*"):
        sidecar.unlink(missing_ok=True)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    try:
        command.upgrade(cfg, "head")
    except Exception as exc:
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
        set_session_factory(lambda: ReuseSession(session))
        try:
            yield session
        finally:
            set_session_factory(None)
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
def make_document(db_session: AsyncSession) -> Callable[..., Awaitable[Document]]:
    async def _make(**overrides: Any) -> Document:
        fields: dict[str, Any] = {
            "project_id": "proj-test",
            "filename": "spec.md",
            "mime_type": "text/markdown",
            "content_hash": uuid.uuid4().hex + uuid.uuid4().hex,
            "status": "uploaded",
            "progress": {"step": "uploaded", "done": 0, "total": 1},
        }
        fields.update(overrides)
        doc = Document(**fields)
        db_session.add(doc)
        await db_session.commit()
        return doc

    return _make


@pytest.fixture
def make_feature(db_session: AsyncSession) -> Callable[..., Awaitable[Feature]]:
    async def _make(
        *,
        document: Document | None = None,
        questions: list[dict[str, Any]] | None = None,
        **overrides: Any,
    ) -> Feature:
        if document is None:
            document = Document(
                project_id=overrides.get("project_id", "proj-test"),
                filename="spec.md",
                mime_type="text/markdown",
                content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                status="ready",
                markdown=overrides.pop("markdown", "# Spec\n\nUsers can sign in with email."),
            )
            db_session.add(document)
            await db_session.flush()
        fields: dict[str, Any] = {
            "project_id": document.project_id,
            "document_id": document.id,
            "name": "Email sign-in",
            "summary": "Users can sign in with their work email.",
            "details": {
                "description": "Users can sign in with their work email.",
                "user_roles": ["user"],
                "functional_requirements": [
                    {"text": "Accept work email", "quote": "sign in with their work email"}
                ],
                "acceptance_criteria": [],
                "constraints": [],
                "dependencies": [],
                "out_of_scope": [],
            },
            "source_quotes": [
                {
                    "quote": "Users can sign in with their work email.",
                    "verified": True,
                    "char_start": 10,
                    "char_end": 50,
                    "origin": "document",
                }
            ],
            "status": "analysed",
            "position": 0,
        }
        fields.update(overrides)
        feature = Feature(**fields)
        db_session.add(feature)
        await db_session.flush()
        for i, q in enumerate(questions or []):
            db_session.add(
                FeatureQuestion(
                    project_id=feature.project_id,
                    feature_id=feature.id,
                    question=q.get("question", "Who is this for?"),
                    why=q.get("why", "Need the role"),
                    target_field=q.get("target_field", "user_roles"),
                    is_follow_up=bool(q.get("is_follow_up", False)),
                    status=q.get("status", "open"),
                    ordinal=q.get("ordinal", i),
                )
            )
        await db_session.commit()
        return feature

    return _make


@pytest.fixture
def make_task(db_session: AsyncSession) -> Callable[..., Awaitable[Task]]:
    async def _make(feature: Feature, **overrides: Any) -> Task:
        fields: dict[str, Any] = {
            "project_id": feature.project_id,
            "feature_id": feature.id,
            "title": "Implement sign-in",
            "description": "Add email sign-in.",
            "area": "auth",
            "priority": "P1",
            "acceptance_criteria": [
                {"given": "a user", "when": "they submit email", "then": "they are signed in"}
            ],
            "estimate": "M",
            "traces_to": ["Accept work email"],
            "status": "draft",
            "ordinal": 0,
        }
        fields.update(overrides)
        task = Task(**fields)
        db_session.add(task)
        await db_session.commit()
        return task

    return _make
