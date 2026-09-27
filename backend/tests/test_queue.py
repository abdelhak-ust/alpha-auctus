"""app.queue — enqueue (arq pool mocked, no Redis), worker registration, readiness stub."""

import sys
import types
import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app import queue
from app.models import AuditEvent


class FakePool:
    def __init__(self, result=..., exc=None):
        self.calls: list[tuple[str, dict]] = []
        self._result = result
        self._exc = exc

    async def enqueue_job(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if self._exc:
            raise self._exc
        if self._result is None:
            return None
        return types.SimpleNamespace(job_id=kwargs.get("_job_id") or "generated")

    async def aclose(self):
        pass


@pytest.fixture
def pool(monkeypatch):
    fake = FakePool()

    async def get_pool():
        return fake

    monkeypatch.setattr(queue, "_get_pool", get_pool)
    return fake


async def test_enqueue_returns_job_id_and_passes_kwargs(pool):
    job_id = await queue.enqueue("ingest_document", document_id="d1", _job_id="ingest_document:d1")
    assert job_id == "ingest_document:d1"
    assert pool.calls == [
        ("ingest_document", {"document_id": "d1", "_job_id": "ingest_document:d1"})
    ]


async def test_enqueue_duplicate_job_returns_none(monkeypatch):
    async def get_pool():
        return FakePool(result=None)

    monkeypatch.setattr(queue, "_get_pool", get_pool)
    assert await queue.enqueue("readiness_run", feature_id="f", project_id="p") is None


async def test_enqueue_unknown_job_rejected(pool):
    with pytest.raises(ValueError, match="Unknown job"):
        await queue.enqueue("nope")


@pytest.mark.parametrize("exc", [ConnectionRefusedError("refused"), OSError("down")])
async def test_enqueue_raises_queue_unavailable_when_redis_down(monkeypatch, exc):
    async def get_pool():
        return FakePool(exc=exc)

    monkeypatch.setattr(queue, "_get_pool", get_pool)
    with pytest.raises(queue.QueueUnavailable, match="Redis"):
        await queue.enqueue("readiness_run", feature_id="f", project_id="p")


async def test_enqueue_maps_redis_connection_error(monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError

    async def get_pool():
        return FakePool(exc=RedisConnectionError("gone"))

    monkeypatch.setattr(queue, "_get_pool", get_pool)
    with pytest.raises(queue.QueueUnavailable):
        await queue.enqueue("ingest_document", document_id="d")


async def test_enqueue_against_unreachable_redis_is_queue_unavailable(monkeypatch):
    """Real pool creation, nothing listening on the port — fails fast, no retries."""
    from app.config import get_settings

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    get_settings.cache_clear()
    await queue.reset_pool()
    try:
        with pytest.raises(queue.QueueUnavailable):
            await queue.enqueue("ingest_document", document_id="d")
    finally:
        await queue.reset_pool()
        get_settings.cache_clear()


def test_worker_registers_jobs_by_name(monkeypatch):
    """The pipeline's job module may not exist yet — stand in a fake so the string import
    resolves, and check registration + startup hook."""
    fake_jobs = types.ModuleType("app.ingest.jobs")

    async def ingest_document(ctx, document_id):
        return None

    fake_jobs.ingest_document = ingest_document
    monkeypatch.setitem(sys.modules, "app.ingest.jobs", fake_jobs)
    monkeypatch.delitem(sys.modules, "app.queue.worker", raising=False)

    from app.queue import worker
    from app.vector import ensure_collections

    names = {f.name: f.coroutine for f in worker.WorkerSettings.functions}
    assert set(names) == {"ingest_document", "readiness_run"}
    assert names["ingest_document"] is ingest_document
    assert worker.WorkerSettings.on_startup is worker.on_startup
    assert worker.ensure_collections is ensure_collections
    monkeypatch.delitem(sys.modules, "app.queue.worker", raising=False)


async def test_readiness_run_stub_writes_audit_row(db_session):
    @asynccontextmanager
    async def factory():
        yield db_session

    from app.queue.jobs import readiness_run

    fid = uuid.uuid4()
    await readiness_run({"session_factory": factory}, str(fid), "proj-1", extra="ignored")

    rows = (await db_session.execute(
        select(AuditEvent).where(AuditEvent.feature_id == fid)
    )).scalars().all()
    assert len(rows) == 1
    assert (rows[0].graph, rows[0].node, rows[0].project_id) == (
        "readiness", "readiness_run", "proj-1"
    )
