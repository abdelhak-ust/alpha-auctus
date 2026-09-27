"""app.graph — audit helper and checkpointer DSN handling (reused by MVP)."""

import uuid

import pytest
from sqlalchemy import select

from app.graph import record_audit, to_psycopg_dsn
from app.models import AuditEvent


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgresql+asyncpg://localhost/nexus_dev", "postgresql://localhost/nexus_dev"),
        ("postgresql+psycopg://u:p@h:5432/db", "postgresql://u:p@h:5432/db"),
        ("postgresql://localhost/x", "postgresql://localhost/x"),
        ("postgres://localhost/x", "postgresql://localhost/x"),
    ],
)
def test_to_psycopg_dsn(given, expected):
    assert to_psycopg_dsn(given) == expected


async def test_record_audit_flushes_without_committing(db_session, monkeypatch):
    async def no_commit():
        raise AssertionError("record_audit must not commit")

    monkeypatch.setattr(db_session, "commit", no_commit)
    fid = uuid.uuid4()

    event = await record_audit(
        db_session,
        project_id="p1",
        feature_id=str(fid),
        graph="document",
        node="persist",
        type="agent_step",
        detail={"k": 1},
    )

    assert event.id is not None
    row = (
        await db_session.execute(select(AuditEvent).where(AuditEvent.id == event.id))
    ).scalar_one()
    assert (row.feature_id, row.detail, row.type) == (fid, {"k": 1}, "agent_step")


async def test_record_audit_allows_no_feature(db_session):
    event = await record_audit(
        db_session, project_id="p1", feature_id=None, graph="document", node="convert", type="x"
    )
    assert event.feature_id is None and event.detail == {}
