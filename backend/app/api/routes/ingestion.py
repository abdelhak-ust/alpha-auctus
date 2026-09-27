"""Ingestion HTTP API — plans/ingestion.md §11.1 + §11.3 amendments, phase P6.

Six project-scoped endpoints under ``/api/projects/{projectId}/…``:

- ``POST documents``                        upload (validate → hash → store blob → enqueue)
- ``GET  documents`` / ``documents/{id}``   ingestion status
- ``GET  features``                         the Feature Registry (current version joined)
- ``GET  review-queue``                     open conflicts + sweep flags as ``IngestItem``
- ``POST review-queue/{itemId}/resolve``    human approve/dismiss (contract §3, ingestion §7)

This module runs no pipeline logic: it validates, reads, records the human's resolution and
hands work to the queue. Collaborators are called through their modules (``queue.enqueue``,
``store.reindex_feature``, ``graph.record_audit``) so tests can monkeypatch them; the
``app.graph`` / ``app.ingest`` imports are deferred to call time so this router (and therefore
``app.main``) imports without pulling in LangGraph, Qdrant or Docling.

Errors follow ui_ux_design.md §7: ``{"detail": {"problem", "cause", "fix"}}``.
"""

from __future__ import annotations

import hashlib
import io
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any

import anyio
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import queue
from app.config import get_settings
from app.db.session import get_db
from app.models import AuditEvent, Document, Feature, FeatureVersion, ReviewItem
from app.schemas.ingestion import (
    Candidate,
    Citation,
    IngestDocument,
    IngestItem,
    RegistryFeature,
    ResolveRequest,
    ResolveResponse,
    SourceRef,
    VerdictDetail,
)

router = APIRouter(tags=["ingestion"])

# There is no auth on the backend yet, so every resolution is attributed to this placeholder.
RESOLVER = "user"
AUDIT_GRAPH = "ingest"
AUDIT_NODE = "review_resolve"
# Sweep flags are low-confidence by definition (§11.3): always below the "please review" line.
SWEEP_FLAG_MAX_CONFIDENCE = 49
# IngestItem.priority is required by the existing TS type but ingestion has no priority signal.
DEFAULT_PRIORITY = "P2"

# extension -> (sniffed kind, mime type)
_ALLOWED: dict[str, tuple[str, str]] = {
    ".pdf": ("pdf", "application/pdf"),
    ".docx": (
        "docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".md": ("text", "text/markdown"),
    ".markdown": ("text", "text/markdown"),
    ".txt": ("text", "text/plain"),
}
_SAFE_PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


# ---------------------------------------------------------------------------------------------
# Errors & helpers
# ---------------------------------------------------------------------------------------------


def _error(status: int, problem: str, cause: str, fix: str) -> HTTPException:
    return HTTPException(
        status_code=status, detail={"problem": problem, "cause": cause, "fix": fix}
    )


def _check_project_id(project_id: str) -> None:
    # Projects live in the Node SQLite store (no FK here), so all we can verify is that the id
    # is well-formed. It is also a blob sub-directory, so this doubles as the traversal guard.
    if not _SAFE_PROJECT_ID.match(project_id):
        raise _error(
            404,
            f"Project {project_id!r} not found.",
            "Project ids contain only letters, digits, '-' and '_'.",
            "Open the project from the project switcher and retry.",
        )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422s in the problem + cause + fix shape. main.py registers this app-wide; paths outside
    this router keep FastAPI's default body."""
    if "/projects/" not in request.url.path:
        from fastapi.exception_handlers import request_validation_exception_handler

        return await request_validation_exception_handler(request, exc)
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(part) for part in first.get("loc", ()) if part != "body") or "request"
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "problem": "The request was not understood.",
                "cause": f"Invalid {where}: {first.get('msg', 'validation failed')}.",
                "fix": "Resolve with action 'approve' or 'dismiss', or upload one file "
                "in the 'file' field.",
            }
        },
    )


def _as_uuid(value: Any) -> uuid.UUID | None:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _not_found(what: str, ident: str, project_id: str, fix: str) -> HTTPException:
    return _error(
        404,
        f"{what} {ident!r} not found.",
        f"No {what.lower()} with that id exists in project {project_id!r}.",
        fix,
    )


async def _enqueue(job_name: str, **kwargs: Any) -> None:
    """Hand a job to the queue; ``QueueUnavailable`` (Redis down) becomes a 503."""
    try:
        await queue.enqueue(job_name, **kwargs)
    except queue.QueueUnavailable as exc:
        raise _error(
            503,
            f"Could not queue the {job_name!r} job.",
            f"The job queue (Redis at {get_settings().redis_url}) can't be reached.",
            "Start Redis and the arq worker (see backend/README.md), then retry.",
        ) from exc


async def _audit(db: AsyncSession, *, node: str = AUDIT_NODE, **kwargs: Any) -> None:
    from app import graph  # deferred: see module docstring

    await graph.record_audit(db, graph=AUDIT_GRAPH, node=node, **kwargs)


async def _reindex(db: AsyncSession, feature_id: uuid.UUID) -> None:
    """Re-embed + upsert the feature's Qdrant point; any failure → rollback + 503 (§11.3)."""
    from app.ingest import store  # deferred: see module docstring

    try:
        await store.reindex_feature(db, feature_id)
    except Exception as exc:  # noqa: BLE001 — VertexNotConfigured, Qdrant errors, …
        await db.rollback()
        raise _error(
            503,
            "Your decision could not be saved.",
            f"Re-indexing the feature failed ({type(exc).__name__}: {exc}). Vertex AI or "
            "Qdrant is unavailable or not configured.",
            "Run `gcloud auth application-default login`, set GCP_PROJECT_ID, start Qdrant "
            "(`docker compose up -d qdrant`), then retry.",
        ) from exc


def _pct(value: Any) -> int:
    """0–1 confidence (DB/payloads) → the 0–100 integer the UI shows."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, round(v * 100)))


def _short(text: str, limit: int = 120) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _refs(raw: Any) -> list[dict]:
    return [r for r in (raw or []) if isinstance(r, dict)]


def _api_ref(ref: dict) -> SourceRef:
    return SourceRef(
        doc_id=str(ref.get("doc_id", "")),
        doc_type=str(ref.get("doc_type", "")),
        chunk_id=str(ref.get("chunk_id", "")),
        section=str(ref.get("section") or ""),
        char_start=int(ref.get("char_start", 0)),
        char_end=int(ref.get("char_end", 0)),
        snippet=str(ref.get("snippet") or ""),
    )


def _citation(ref: dict | None, filename: str | None) -> Citation | None:
    if not ref:
        return None
    title = filename or str(ref.get("doc_id", ""))
    if ref.get("section"):
        title = f"{title} — {ref['section']}"
    return Citation(
        id=str(ref.get("doc_id", "")), type="source", title=title, snippet=ref.get("snippet", "")
    )


# ---------------------------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------------------------


def _sniff_kind(content: bytes) -> str | None:
    """What the bytes actually are: 'pdf', 'docx', 'text' or None."""
    if content.startswith(b"%PDF-"):
        return "pdf"
    if content.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                return "docx" if "word/document.xml" in zf.namelist() else None
        except zipfile.BadZipFile:
            return None
    if b"\x00" in content:
        return None
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return "text"


def _validate_type(filename: str, content: bytes) -> tuple[str, str]:
    """Return (extension, mime type) or raise 415."""
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED:
        raise _error(
            415,
            f"{filename!r} is not a supported document type.",
            "Only PDF, DOCX, Markdown and TXT are ingested in v1 "
            f"(got {ext or 'no extension'!r}).",
            "Export the document as PDF, DOCX, Markdown or plain text and upload it again.",
        )
    expected, mime = _ALLOWED[ext]
    if not content:
        raise _error(
            415,
            f"{filename!r} is empty.",
            "An empty file has no content to ingest.",
            "Upload the document with its content.",
        )
    actual = _sniff_kind(content)
    if actual != expected:
        seen = f"is {actual.upper()}" if actual else "matches none of PDF, DOCX, Markdown, TXT"
        raise _error(
            415,
            f"{filename!r} does not look like a {ext} file.",
            f"The extension says {ext}, but the content {seen}.",
            "Re-export the document in one of the supported formats and upload it again.",
        )
    return ext, mime


# ---------------------------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------------------------


async def _feature_counts(
    db: AsyncSession, project_id: str, doc_ids: list[uuid.UUID]
) -> dict[str, int]:
    """Distinct features with a version created by ingesting each doc (``ingest:<doc_id>``)."""
    if not doc_ids:
        return {}
    origins = {f"ingest:{d}": str(d) for d in doc_ids}
    rows = await db.execute(
        select(FeatureVersion.created_from, func.count(func.distinct(FeatureVersion.feature_id)))
        .join(Feature, Feature.feature_id == FeatureVersion.feature_id)
        .where(Feature.project_id == project_id, FeatureVersion.created_from.in_(list(origins)))
        .group_by(FeatureVersion.created_from)
    )
    return {origins[origin]: count for origin, count in rows.all()}


def _doc_out(doc: Document, feature_count: int, *, duplicate: bool = False) -> IngestDocument:
    return IngestDocument(
        id=str(doc.doc_id),
        project_id=doc.project_id,
        filename=doc.filename,
        status=doc.ingestion_status,
        error=doc.error or None,
        duplicate=True if duplicate else None,
        feature_count=feature_count,
        uploaded_at=doc.uploaded_at,
    )


async def _doc_with_count(db: AsyncSession, doc: Document, **kw: Any) -> IngestDocument:
    counts = await _feature_counts(db, doc.project_id, [doc.doc_id])
    return _doc_out(doc, counts.get(str(doc.doc_id), 0), **kw)


async def _find_by_hash(db: AsyncSession, project_id: str, content_hash: str) -> Document | None:
    stmt = select(Document).where(
        Document.project_id == project_id, Document.content_hash == content_hash
    )
    return (await db.execute(stmt)).scalar_one_or_none()


_DOC_ROUTE = {"response_model_by_alias": True, "response_model_exclude_none": True}


@router.post(
    "/projects/{projectId}/documents", status_code=202, response_model=IngestDocument, **_DOC_ROUTE
)
async def upload_document(
    projectId: str,
    response: Response,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> IngestDocument:
    project_id = projectId
    _check_project_id(project_id)
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    filename = Path(file.filename or "").name or "untitled"

    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise _error(
            413,
            f"{filename!r} is too large to ingest.",
            f"Uploads are limited to {settings.max_upload_mb} MB.",
            "Split the document into smaller files, or raise MAX_UPLOAD_MB on the backend.",
        )
    ext, mime = _validate_type(filename, content)
    content_hash = hashlib.sha256(content).hexdigest()

    existing = await _find_by_hash(db, project_id, content_hash)
    if existing is not None and existing.ingestion_status == "failed":
        return await _retry_failed(db, existing, content)
    if existing is not None:
        response.status_code = 200
        return await _doc_with_count(db, existing, duplicate=True)

    blob_path = f"{project_id}/{content_hash}{ext}"  # relative to settings.blob_dir (§11.3)
    blob_file = anyio.Path(settings.blob_dir) / blob_path
    await blob_file.parent.mkdir(parents=True, exist_ok=True)
    await blob_file.write_bytes(content)

    doc = Document(
        project_id=project_id,
        doc_type="upload",
        content_hash=content_hash,
        filename=filename,
        mime_type=mime,
        size_bytes=len(content),
        blob_path=blob_path,
        ingestion_status="pending",
    )
    db.add(doc)
    try:
        await db.commit()
    except IntegrityError:
        # Same bytes uploaded concurrently — the other request won; report it as a duplicate.
        await db.rollback()
        existing = await _find_by_hash(db, project_id, content_hash)
        if existing is None:
            raise
        if existing.ingestion_status == "failed":
            return await _retry_failed(db, existing, content)
        response.status_code = 200
        return await _doc_with_count(db, existing, duplicate=True)
    await db.refresh(doc)

    try:
        await _enqueue(
            "ingest_document",
            document_id=str(doc.doc_id),
            _job_id=f"ingest_document:{doc.doc_id}",
        )
    except HTTPException:
        # Don't leave a 'pending' row nothing will ever process — undo so a retry works.
        await db.delete(doc)
        await db.commit()
        await blob_file.unlink(missing_ok=True)
        raise

    return _doc_out(doc, 0)


async def _retry_failed(db: AsyncSession, doc: Document, content: bytes) -> IngestDocument:
    """Re-upload of a `failed` document: reset to pending and re-enqueue (§11.3 sign-off).

    Not a duplicate — the user is retrying. The retry count lives in `upload_meta.retries` and
    makes the arq job id unique (arq drops a job whose id it has already seen)."""
    settings = get_settings()
    blob_file = anyio.Path(settings.blob_dir) / (doc.blob_path or "")
    if not doc.blob_path or not await blob_file.is_file():
        ext = Path(doc.filename).suffix.lower()
        doc.blob_path = f"{doc.project_id}/{doc.content_hash}{ext}"
        blob_file = anyio.Path(settings.blob_dir) / doc.blob_path
        await blob_file.parent.mkdir(parents=True, exist_ok=True)
        await blob_file.write_bytes(content)

    meta = dict(doc.upload_meta or {})
    retry_no = int(meta.get("retries", 0)) + 1
    previous_error = doc.error
    doc.upload_meta = {**meta, "retries": retry_no}
    doc.ingestion_status = "pending"
    doc.error = None
    await _audit(
        db,
        project_id=doc.project_id,
        feature_id=None,
        type="ingest_retried",
        detail={
            "document_id": str(doc.doc_id),
            "retry": retry_no,
            "previous_error": previous_error,
        },
        node="upload",
    )
    await db.flush()
    try:
        await _enqueue(
            "ingest_document",
            document_id=str(doc.doc_id),
            _job_id=f"ingest_document:{doc.doc_id}:retry:{retry_no}",
        )
    except HTTPException:
        await db.rollback()  # stays `failed` with its original error; the user can retry again
        raise
    await db.commit()
    return await _doc_with_count(db, doc)


@router.get(
    "/projects/{projectId}/documents", response_model=list[IngestDocument], **_DOC_ROUTE
)
async def list_documents(
    projectId: str, db: AsyncSession = Depends(get_db)
) -> list[IngestDocument]:
    _check_project_id(projectId)
    stmt = (
        select(Document)
        .where(Document.project_id == projectId)
        .order_by(Document.uploaded_at.desc())
    )
    docs = (await db.execute(stmt)).scalars().all()
    counts = await _feature_counts(db, projectId, [d.doc_id for d in docs])
    return [_doc_out(d, counts.get(str(d.doc_id), 0)) for d in docs]


@router.get(
    "/projects/{projectId}/documents/{documentId}", response_model=IngestDocument, **_DOC_ROUTE
)
async def get_document(
    projectId: str, documentId: str, db: AsyncSession = Depends(get_db)
) -> IngestDocument:
    _check_project_id(projectId)
    doc_id = _as_uuid(documentId)
    doc = None
    if doc_id is not None:
        stmt = select(Document).where(
            Document.project_id == projectId, Document.doc_id == doc_id
        )
        doc = (await db.execute(stmt)).scalar_one_or_none()
    if doc is None:
        raise _not_found(
            "Document", documentId, projectId, "Refresh the Sources view for the current list."
        )
    return await _doc_with_count(db, doc)


# ---------------------------------------------------------------------------------------------
# Feature registry
# ---------------------------------------------------------------------------------------------


@router.get(
    "/projects/{projectId}/features",
    response_model=list[RegistryFeature],
    response_model_by_alias=True,
)
async def list_features(
    projectId: str, db: AsyncSession = Depends(get_db)
) -> list[RegistryFeature]:
    _check_project_id(projectId)
    rows = await db.execute(
        select(Feature, FeatureVersion)
        .outerjoin(FeatureVersion, FeatureVersion.version_id == Feature.current_version_id)
        .where(Feature.project_id == projectId)
        .order_by(Feature.name)
    )
    return [
        RegistryFeature(
            id=str(f.feature_id),
            project_id=f.project_id,
            name=f.name,
            description=v.description if v else "",
            version_no=v.version_no if v else 0,
            lifecycle_state=f.lifecycle_state,
            source_refs=[_api_ref(r) for r in _refs(v.source_refs if v else [])],
            updated_at=f.updated_at,
        )
        for f, v in rows.all()
    ]


# ---------------------------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------------------------


async def _version(db: AsyncSession, version_id: Any) -> FeatureVersion | None:
    vid = _as_uuid(version_id)
    return await db.get(FeatureVersion, vid) if vid else None


async def _conflict_item(
    db: AsyncSession, item: ReviewItem, filename: str | None
) -> IngestItem:
    """payload: {feature_name, reason, confidence, current_version_id, incoming_version_id}."""
    p = item.payload or {}
    current = await _version(db, p.get("current_version_id"))
    incoming = await _version(db, p.get("incoming_version_id"))
    confidence = _pct(p.get("confidence"))
    name = str(p.get("feature_name") or "Feature")
    in_refs = _refs(incoming.source_refs) if incoming else []
    cur_refs = _refs(current.source_refs) if current else []
    source = filename or "the uploaded document"

    # Ranked: the incoming (proposed) version first, the current registry version second.
    # The payload carries a single match confidence, so both candidates show it.
    candidates: list[Candidate] = []
    if incoming:
        candidates.append(
            Candidate(
                id=f"incoming:v{incoming.version_no}",
                type="item",
                title=f"Incoming v{incoming.version_no}: {_short(incoming.description)}",
                reason=f"New description from {source}"
                + (f": “{_short(in_refs[0].get('snippet', ''), 80)}”" if in_refs else "."),
                confidence=confidence,
            )
        )
    if current:
        candidates.append(
            Candidate(
                id=f"current:v{current.version_no}",
                type="item",
                title=f"Current v{current.version_no}: {_short(current.description)}",
                reason="The registry's current version"
                + (f": “{_short(cur_refs[0].get('snippet', ''), 80)}”" if cur_refs else "."),
                confidence=confidence,
            )
        )
    return IngestItem(
        id=str(item.id),
        title=name,
        description=incoming.description if incoming else "",
        area=str(in_refs[0].get("section") or "") if in_refs else "",
        priority=DEFAULT_PRIORITY,
        source_id=str(item.document_id),
        source_snippet=str(in_refs[0].get("snippet") or "") if in_refs else "",
        verdict=VerdictDetail(
            type="conflict",
            confidence=confidence,
            message=str(p.get("reason") or f"{source} contradicts the current “{name}”."),
            candidates=candidates,
            citation=_citation(in_refs[0] if in_refs else None, filename),
        ),
    )


def _sweep_item(item: ReviewItem, filename: str | None) -> IngestItem:
    """payload: {feature_name, description, reason, confidence, source_ref}."""
    p = item.payload or {}
    ref = p.get("source_ref") if isinstance(p.get("source_ref"), dict) else None
    confidence = min(_pct(p.get("confidence")), SWEEP_FLAG_MAX_CONFIDENCE)
    name = str(p.get("feature_name") or "Possible feature")
    reason = str(
        p.get("reason") or "Completeness sweep found this mention with no matching feature."
    )
    return IngestItem(
        id=str(item.id),
        title=name,
        description=str(p.get("description") or ""),
        area=str(ref.get("section") or "") if ref else "",
        priority=DEFAULT_PRIORITY,
        source_id=str(item.document_id),
        source_snippet=str(ref.get("snippet") or "") if ref else "",
        verdict=VerdictDetail(
            type="net-new",
            confidence=confidence,
            message=f"Low confidence — please review. {reason}",
            candidates=[
                Candidate(
                    id=f"flag:{item.id}",
                    type="item",
                    title=name,
                    reason=reason,
                    confidence=confidence,
                )
            ],
            citation=_citation(ref, filename),
        ),
    )


@router.get(
    "/projects/{projectId}/review-queue",
    response_model=list[IngestItem],
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
async def review_queue(projectId: str, db: AsyncSession = Depends(get_db)) -> list[IngestItem]:
    _check_project_id(projectId)
    stmt = (
        select(ReviewItem, Document.filename)
        .outerjoin(Document, Document.doc_id == ReviewItem.document_id)
        .where(ReviewItem.project_id == projectId, ReviewItem.status == "open")
        .order_by(ReviewItem.created_at)
    )
    out: list[IngestItem] = []
    for item, filename in (await db.execute(stmt)).all():
        if item.kind == "conflict":
            out.append(await _conflict_item(db, item, filename))
        else:
            out.append(_sweep_item(item, filename))
    return out


# Lifecycle states the registry stage has already moved a feature into (contract §3).
_PAST_CONSOLIDATED = frozenset(
    {"classified", "assessing", "awaiting_answers", "answered", "dev_ready", "overridden",
     "stale", "in_breakdown", "needs_review", "broken_down"}
)


async def _other_open_conflicts(db: AsyncSession, feature_id: Any, item_id: Any) -> bool:
    stmt = select(func.count()).where(
        ReviewItem.feature_id == feature_id,
        ReviewItem.kind == "conflict",
        ReviewItem.status == "open",
        ReviewItem.id != item_id,
    )
    return bool(await db.scalar(stmt))


async def _state_before_conflict(db: AsyncSession, feature: Feature) -> str | None:
    """The feature's lifecycle state before it went `conflicted`, from the pipeline's
    `conflict_flagged` audit rows (`detail.from_state`); None when not recorded (e.g. a new
    feature that contradicted itself in one document)."""
    stmt = (
        select(AuditEvent.detail)
        .where(AuditEvent.feature_id == feature.feature_id, AuditEvent.type == "conflict_flagged")
        .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc())
    )
    for detail in (await db.execute(stmt)).scalars():
        state = (detail or {}).get("from_state")
        if state and state != "conflicted":
            return state
    if feature.classification or feature.readiness or feature.override:
        return None  # registry touched it, but we can't tell where it was → caller uses stale
    return "consolidated"


@router.post(
    "/projects/{projectId}/review-queue/{itemId}/resolve",
    response_model=ResolveResponse,
    response_model_by_alias=True,
)
async def resolve_review_item(
    projectId: str, itemId: str, body: ResolveRequest, db: AsyncSession = Depends(get_db)
) -> ResolveResponse:
    _check_project_id(projectId)
    item_id = _as_uuid(itemId)
    item = None
    if item_id is not None:
        stmt = (
            select(ReviewItem)
            .where(ReviewItem.project_id == projectId, ReviewItem.id == item_id)
            .with_for_update()
        )
        item = (await db.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise _not_found("Review item", itemId, projectId, "Refresh the review queue.")
    if item.status != "open":
        raise _error(
            409,
            "This review item was already resolved.",
            f"It was {item.status} by {item.resolved_by or 'someone'}.",
            "Refresh the review queue — nothing more to do here.",
        )

    action = body.action
    p = item.payload or {}
    detail: dict[str, Any] = {"review_item_id": str(item.id), "kind": item.kind, "action": action}
    handoff: Feature | None = None  # feature handed to the registry → readiness_run
    reindex = False

    if item.kind == "conflict":
        feature = await db.get(Feature, item.feature_id) if item.feature_id else None
        if feature is None:
            raise _error(
                409,
                "The conflicted feature no longer exists.",
                f"Review item {itemId!r} points at feature {item.feature_id}, which is gone.",
                "Re-ingest the source document.",
            )
        if action == "approve":
            incoming = await _version(db, p.get("incoming_version_id"))
            if incoming is None or incoming.feature_id != feature.feature_id:
                raise _error(
                    409,
                    "The incoming version for this conflict is missing.",
                    "The review item has no stored incoming feature_version, so there is no "
                    "cited description to accept.",
                    "Dismiss it (keep the current version), or re-ingest the source document.",
                )
            detail["previous_version_id"] = str(feature.current_version_id)
            detail["new_current_version_id"] = str(incoming.version_id)
            feature.current_version_id = incoming.version_id
            reindex = True
        else:
            detail["kept_version_id"] = str(feature.current_version_id)
        if await _other_open_conflicts(db, feature.feature_id, item.id):
            # Another conflict is still open: stay blocked, no hand-off (§11.3 sign-off).
            detail["still_conflicted"] = True
        else:
            prior = await _state_before_conflict(db, feature)
            if prior is not None and prior not in _PAST_CONSOLIDATED:
                feature.lifecycle_state = "consolidated"
                handoff = feature
            elif action == "approve":
                # New content on a feature already past consolidated → stale (contract §3).
                feature.lifecycle_state = "stale"
                handoff = feature
            elif prior is not None:
                feature.lifecycle_state = prior  # content unchanged: restore, no re-run
            else:
                feature.lifecycle_state = "stale"  # prior unknown: re-enter readiness safely
                handoff = feature
            detail["prior_state"] = prior
        detail["to_state"] = feature.lifecycle_state
    elif action == "approve":  # sweep_flag → create the feature from the cited fragment
        ref = p.get("source_ref") if isinstance(p.get("source_ref"), dict) else None
        if not ref:
            raise _error(
                422,
                "Can't add this feature without a source.",
                f"Review item {itemId!r} has no cited source_ref, and Nexus never stores an "
                "uncited feature.",
                "Dismiss it, or re-ingest the source document so the fragment is cited.",
            )
        name = str(p.get("feature_name") or _short(ref.get("snippet", ""), 60))
        feature = Feature(project_id=projectId, name=name, lifecycle_state="consolidated")
        db.add(feature)
        await db.flush()
        version = FeatureVersion(
            feature_id=feature.feature_id,
            version_no=1,
            description=str(p.get("description") or ref.get("snippet") or name),
            source_refs=[ref],
            created_from=f"manual:{RESOLVER}",
        )
        db.add(version)
        await db.flush()
        feature.current_version_id = version.version_id
        item.feature_id = feature.feature_id
        detail["created_feature_id"] = str(feature.feature_id)
        handoff = feature
        reindex = True

    item.status = "approved" if action == "approve" else "dismissed"
    item.resolved_by = RESOLVER
    feature_id = item.feature_id
    await _audit(
        db,
        project_id=projectId,
        feature_id=feature_id,
        type=f"{item.kind}_{item.status}",
        detail=detail,
    )
    await db.flush()
    if reindex and item.feature_id is not None:
        await _reindex(db, item.feature_id)
    await db.commit()

    if handoff is not None:
        # Contract §3: consolidated → hand off to the registry stage. The resolution is already
        # committed; if the queue is down, record it (audit row) and tell the caller rather
        # than silently leaving a consolidated feature that never reaches the registry.
        try:
            await _enqueue(
                "readiness_run", feature_id=str(handoff.feature_id), project_id=projectId
            )
        except HTTPException as exc:
            await _audit(
                db,
                project_id=projectId,
                feature_id=handoff.feature_id,
                type="readiness_enqueue_failed",
                detail={**detail, "error": exc.detail},
            )
            await db.commit()
            exc.detail = {
                **exc.detail,
                "problem": "Your decision was saved, but the feature could not be handed to "
                "the registry.",
            }
            raise
    return ResolveResponse()
