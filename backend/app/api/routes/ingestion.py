"""Ingestion endpoints (plans/ingestion.md § API surface).

`client/server.ts` forwards its existing `/api/sources/upload` and `/api/ingest/resolve`
handlers here (see plans/ingestion.md "Placement") and merges the result into its own store —
these routes don't need to match the frontend's exact camelCase contract at the Python/Node
boundary beyond what `IngestItemOut`'s alias generator already produces.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.ingest.parse import UnsupportedSourceType
from app.ingest.pipeline import ingest_source, resolve_candidate
from app.models import Source
from app.schemas.ingestion import (
    ResolvedCandidateOut,
    ResolveRequest,
    ResolveResponse,
    SourceStatusResponse,
    UploadResponse,
    UploadTextRequest,
)

router = APIRouter(tags=["ingestion"])


@router.post("/sources/upload", response_model=UploadResponse)
async def upload_text(
    body: UploadTextRequest, db: AsyncSession = Depends(get_db)
) -> UploadResponse:
    """Text/markdown/csv content, same shape client/server.ts has always accepted."""
    try:
        _source, items = await ingest_source(
            db,
            project_id=body.project_id,
            filename=body.file_name or "Untitled document",
            content=body.file_content.encode("utf-8"),
            mime_type="text/plain",
        )
    except UnsupportedSourceType as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UploadResponse(count=len(items), items=items)


@router.post("/sources/upload-file", response_model=UploadResponse)
async def upload_file(
    project_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """PDF/image uploads (plans/ingestion.md's new-this-pass binary path)."""
    content = await file.read()
    mime_type = file.content_type or ""
    try:
        _source, items = await ingest_source(
            db,
            project_id=project_id,
            filename=file.filename or "Untitled upload",
            content=content,
            mime_type=mime_type,
        )
    except UnsupportedSourceType as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UploadResponse(count=len(items), items=items)


@router.get("/sources/{source_id}/status", response_model=SourceStatusResponse)
async def source_status(
    source_id: str, db: AsyncSession = Depends(get_db)
) -> SourceStatusResponse:
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"No source with id {source_id!r}")
    return SourceStatusResponse(id=source.id, status=source.status)


@router.post("/ingest/resolve", response_model=ResolveResponse)
async def resolve(
    body: ResolveRequest, db: AsyncSession = Depends(get_db)
) -> ResolveResponse:
    if body.action not in ("approve", "dismiss"):
        raise HTTPException(
            status_code=422,
            detail=f"action must be 'approve' or 'dismiss', got {body.action!r}",
        )
    candidate = await resolve_candidate(db, candidate_id=body.id, action=body.action)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"No ingest candidate with id {body.id!r}")

    resolved_item = None
    if body.action == "approve":
        resolved_item = ResolvedCandidateOut(
            title=candidate.title,
            description=candidate.description,
            area=(candidate.entity_tags[0] if candidate.entity_tags else "general"),
            priority=candidate.priority,
            source_snippet=candidate.snippet,
        )
    return ResolveResponse(item=resolved_item)
