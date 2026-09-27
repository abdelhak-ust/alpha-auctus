"""Startup recovery: stuck running documents are marked failed."""

from app.agents.graphs._persist import error_json
from app.api.routes.mvp import recover_stuck_documents


async def test_stuck_documents_marked_failed_on_startup(make_document, db_session):
    converting = await make_document(status="converting")
    extracting = await make_document(status="extracting")
    analysing = await make_document(status="analysing")
    ready = await make_document(status="ready")
    await recover_stuck_documents()
    for doc in (converting, extracting, analysing):
        await db_session.refresh(doc)
        assert doc.status == "failed"
        err = (doc.error or "").lower()
        assert "server restarted" in err or "restarted" in err
    await db_session.refresh(ready)
    assert ready.status == "ready"


async def test_error_json_shape():
    raw = error_json("Processing stopped.", "The server restarted.", "Re-upload.")
    assert "Processing stopped" in raw
    assert "Re-upload" in raw
