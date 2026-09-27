"""The arq job `ingest_document(ctx, document_id, *, session_factory=None)` (§11.3).

Registered by string path in `app.queue.worker` (`app.ingest.jobs.ingest_document`). Runs the
compiled `ingest` graph with the shared Postgres checkpointer (thread id
`ingest:<document_id>`, contract §6). Safe to re-run: a document already `done` is a no-op,
one stopped between store and hand-off only re-does the hand-off, and a run that failed
mid-graph resumes from its last checkpoint. Does not depend on anything in `ctx`.

Any failure sets `documents.ingestion_status = failed` with one "<problem> <cause> <fix>"
string (ui_ux_design.md §7) — never a silent stop.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app import ai
from app import graph as graph_infra
from app.ingest.graph import GRAPH_NAME, SessionFactory, build_ingest_graph, thread_config
from app.ingest.parse import EmptyDocument, UnsupportedDocumentType
from app.models import Document

logger = logging.getLogger(__name__)

JOB_NAME = "ingest_document"


def failure_message(exc: BaseException) -> str:
    """One "<problem> <cause> <fix>" string for `documents.error`."""
    if isinstance(exc, ai.VertexNotConfigured):
        return (
            "The document couldn't be analysed. "
            f"{exc} "
            "Configure Vertex AI (see backend/README.md), then retry the upload."
        )
    if isinstance(exc, UnsupportedDocumentType | EmptyDocument):
        return f"The document couldn't be parsed. {exc}"
    if type(exc).__module__.startswith("huggingface_hub"):
        return (
            "The PDF couldn't be parsed. "
            "Docling's PDF layout models aren't available on this machine "
            f"({type(exc).__name__}). "
            "Run `poetry run docling-tools models download` in backend/ once (needs network), "
            "then retry the upload."
        )
    if isinstance(exc, FileNotFoundError):
        return (
            "The uploaded file couldn't be read. "
            f"{exc}. "
            "Re-upload the document."
        )
    return (
        "Ingestion stopped before finishing. "
        f"{type(exc).__name__}: {exc}. "
        "Retry the upload; if it fails again, check the backend worker logs."
    )


def _default_session_factory() -> SessionFactory:
    from app.db.session import async_session_factory

    return async_session_factory


async def run_ingest(
    document_id: str, *, checkpointer: Any, session_factory: SessionFactory | None = None
) -> dict:
    """Run (or resume) the ingest graph for one document. Returns the final graph state."""
    graph = build_ingest_graph(checkpointer, session_factory=session_factory)
    config = thread_config(document_id)
    resume = False
    if checkpointer is not None:
        snapshot = await graph.aget_state(config)
        resume = bool(snapshot and snapshot.next)
    return await graph.ainvoke(None if resume else {"document_id": document_id}, config)


async def mark_failed(
    document_id: str, exc: BaseException, session_factory: SessionFactory | None = None
) -> None:
    session_factory = session_factory or _default_session_factory()
    async with session_factory() as session:
        await session.rollback()
        doc = await session.get(Document, uuid.UUID(document_id))
        if doc is None:
            return
        doc.ingestion_status = "failed"
        doc.error = failure_message(exc)
        await graph_infra.record_audit(
            session, project_id=doc.project_id, feature_id=None, graph=GRAPH_NAME,
            node="job", type="failed", detail={"document_id": document_id, "error": doc.error},
        )
        await session.commit()


async def ingest_document(
    ctx: Any, document_id: str, *, session_factory: SessionFactory | None = None
) -> None:
    """arq entrypoint. `ctx` is arq's job context (unused)."""
    session_factory = session_factory or _default_session_factory()
    try:
        checkpointer = await graph_infra.get_checkpointer()
        await run_ingest(document_id, checkpointer=checkpointer,
                         session_factory=session_factory)
    except Exception as exc:
        logger.exception("ingest_document failed for %s", document_id)
        await mark_failed(document_id, exc, session_factory)
