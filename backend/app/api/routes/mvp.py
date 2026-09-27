"""MVP HTTP API — plans/mvp-v0.md.

All routes sit under ``/api/projects/{projectId}``. This module starts graphs; it does
not call Gemini. Errors are ``{"detail": {"problem", "cause", "fix"}}``.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
import uuid
import zipfile
from typing import Any

import anyio
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.graphs._persist import error_json
from app.config import get_settings
from app.db.session import get_db, get_session_factory
from app.models import AuditEvent, ChatMessage, Document, Feature, FeatureQuestion, Task
from app.schemas.mvp import (
    AgentActivity,
    AskRequest,
    AskResponse,
    AuthorRequest,
    AuthorResponse,
    ChatMessageOut,
    ClarificationAnswerRequest,
    ClarificationAnswerResponse,
    ClarificationNext,
    ClarificationSkipRemainingRequest,
    ClarificationSkipRequest,
    ClarificationState,
    DocumentMarkdown,
    DocumentProgress,
    FeatureOut,
    FeaturePatch,
    FeatureQuestionOut,
    GeneratedTaskOut,
    ImpactExplainRequest,
    ImpactExplainResponse,
    MemoryAskRequest,
    MvpDocument,
    TaskPatch,
    VerdictCheckRequest,
    VerdictDetail,
    WorkflowState,
    details_to_api,
    quotes_to_api,
)

router = APIRouter(tags=["mvp"])

_SAFE_PROJECT_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_ALLOWED: dict[str, tuple[str, str]] = {
    ".pdf": ("pdf", "application/pdf"),
    ".docx": (
        "docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".md": ("text", "text/markdown"),
    ".markdown": ("text", "text/markdown"),
}
_RUNNING = {"converting", "extracting", "analysing"}
_background: set[asyncio.Task] = set()
_ROUTE = {"response_model_by_alias": True, "response_model_exclude_none": True}


def _error(status: int, problem: str, cause: str, fix: str) -> HTTPException:
    return HTTPException(
        status_code=status, detail={"problem": problem, "cause": cause, "fix": fix}
    )


def _check_project_id(project_id: str) -> None:
    if not _SAFE_PROJECT_ID.match(project_id):
        raise _error(
            404,
            f"Project {project_id!r} not found.",
            "Project ids contain only letters, digits, '-' and '_'.",
            "Open the project from the project switcher and retry.",
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


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Keep unmatched routes and other HTTP errors on the {problem, cause, fix} contract."""
    detail = exc.detail
    if isinstance(detail, dict) and {"problem", "cause", "fix"} <= set(detail):
        body = detail
    elif isinstance(detail, dict):
        body = {
            "problem": str(detail.get("problem") or "The request failed."),
            "cause": str(
                detail.get("cause") or detail.get("message") or "An HTTP error was raised."
            ),
            "fix": str(detail.get("fix") or "Retry, or check the request and try again."),
        }
    else:
        text = str(detail) if detail else "Not found."
        body = {
            "problem": text if text != "Not Found" else "This URL was not found.",
            "cause": f"No route matches {request.url.path}.",
            "fix": "Open the project from the project switcher and retry.",
        }
    return JSONResponse(status_code=exc.status_code, content={"detail": body})


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
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
                "fix": "Check the request body and upload a PDF, DOCX or Markdown file.",
            }
        },
    )


def spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def start_document_graph(document_id: str) -> None:
    """Runner boundary — tests mock this. The real graph is started as a background task."""
    from app.agents.graphs.document import run_document_graph

    spawn(run_document_graph(document_id))


async def start_task_graph(feature_id: str) -> None:
    from app.agents.graphs.tasks import run_task_graph

    spawn(run_task_graph(feature_id))


def _sniff_kind(content: bytes) -> str | None:
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
    from pathlib import Path

    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED:
        raise _error(
            415,
            f"{filename!r} is not a supported document type.",
            f"Only PDF, DOCX and Markdown are ingested (got {ext or 'no extension'!r}).",
            "Export the document as PDF, DOCX or Markdown and upload it again.",
        )
    expected, mime = _ALLOWED[ext]
    if not content:
        raise _error(
            415,
            f"{filename!r} is empty.",
            "An empty file has no content to extract.",
            "Upload the document with its content.",
        )
    actual = _sniff_kind(content)
    if actual != expected:
        seen = f"is {actual.upper()}" if actual else "matches none of PDF, DOCX, Markdown"
        raise _error(
            415,
            f"{filename!r} does not look like a {ext} file.",
            f"The extension says {ext}, but the content {seen}.",
            "Re-export the document in one of the supported formats and upload it again.",
        )
    return ext, mime


def _progress(doc: Document) -> DocumentProgress | None:
    raw = doc.progress
    if not isinstance(raw, dict):
        return None
    return DocumentProgress(
        step=str(raw.get("step") or doc.status),
        done=int(raw.get("done") or 0),
        total=int(raw.get("total") or 0),
    )


def _error_text(doc: Document) -> str | None:
    if not doc.error:
        return None
    try:
        data = json.loads(doc.error)
        if isinstance(data, dict) and "problem" in data:
            return (
                f"{data.get('problem', '')} ({data.get('cause', '')}). {data.get('fix', '')}"
            ).strip()
    except json.JSONDecodeError:
        pass
    return doc.error


def _doc_out(doc: Document, feature_count: int, *, duplicate: bool = False) -> MvpDocument:
    return MvpDocument(
        id=str(doc.id),
        project_id=doc.project_id,
        filename=doc.filename,
        mime_type=doc.mime_type,
        size_bytes=doc.size_bytes,
        status=doc.status,  # type: ignore[arg-type]
        progress=_progress(doc),
        error=_error_text(doc),
        duplicate=True if duplicate else None,
        feature_count=feature_count,
        uploaded_at=doc.created_at,
    )


def _question_out(q: FeatureQuestion) -> FeatureQuestionOut:
    return FeatureQuestionOut(
        id=str(q.id),
        feature_id=str(q.feature_id),
        question=q.question,
        why=q.why,
        target_field=q.target_field,
        is_follow_up=q.is_follow_up,
        status=q.status,  # type: ignore[arg-type]
        answer=q.answer,
        answered_at=q.answered_at,
        ordinal=q.ordinal,
    )


def _task_out(t: Task) -> GeneratedTaskOut:
    return GeneratedTaskOut(
        id=str(t.id),
        feature_id=str(t.feature_id),
        title=t.title,
        description=t.description,
        area=t.area,
        priority=t.priority,  # type: ignore[arg-type]
        acceptance_criteria=[
            {
                "given": str(c.get("given", "")),
                "when": str(c.get("when", "")),
                "then": str(c.get("then", "")),
                "quote": c.get("quote"),
            }
            if isinstance(c, dict)
            else c
            for c in (t.acceptance_criteria or [])
        ],
        estimate=t.estimate,  # type: ignore[arg-type]
        traces_to=list(t.traces_to or []),
        subtasks=list(t.subtasks or []),
        definition_of_done=list(t.definition_of_done or []),
        review_notes=t.review_notes,
        status=t.status,  # type: ignore[arg-type]
        board_item_id=t.board_item_id,
        ordinal=t.ordinal,
    )


def _feature_out(f: Feature) -> FeatureOut:
    return FeatureOut(
        id=str(f.id),
        project_id=f.project_id,
        document_id=str(f.document_id),
        name=f.name,
        summary=f.summary,
        details=details_to_api(f.details),
        source_quotes=quotes_to_api(f.source_quotes),
        status=f.status,  # type: ignore[arg-type]
        review_status=getattr(f, "review_status", None) or "pending",  # type: ignore[arg-type]
        position=f.position,
        questions=[_question_out(q) for q in (f.questions or [])],
        tasks=[_task_out(t) for t in (f.tasks or [])],
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


_CHAT_KINDS = {"progress", "decision", "question", "text"}


def _chat_out(m: ChatMessage) -> ChatMessageOut:
    kind = getattr(m, "kind", None)
    return ChatMessageOut(
        id=str(m.id),
        project_id=m.project_id,
        role=m.role,  # type: ignore[arg-type]
        text=m.text,
        question_id=str(m.question_id) if m.question_id else None,
        feature_id=str(m.feature_id) if m.feature_id else None,
        kind=kind if kind in _CHAT_KINDS else None,  # type: ignore[arg-type]
        created_at=m.created_at,
    )


def _append_chat(
    db: AsyncSession,
    *,
    project_id: str,
    role: str,
    text: str,
    kind: str,
    feature_id: uuid.UUID | None = None,
    question_id: uuid.UUID | None = None,
) -> None:
    db.add(
        ChatMessage(
            project_id=project_id,
            role=role,
            text=text,
            kind=kind,
            feature_id=feature_id,
            question_id=question_id,
        )
    )


def _feature_load():
    return selectinload(Feature.questions), selectinload(Feature.tasks)


async def _counts(db: AsyncSession, project_id: str, doc_ids: list[uuid.UUID]) -> dict[str, int]:
    if not doc_ids:
        return {}
    rows = await db.execute(
        select(Feature.document_id, func.count())
        .where(Feature.project_id == project_id, Feature.document_id.in_(doc_ids))
        .group_by(Feature.document_id)
    )
    return {str(did): n for did, n in rows.all()}


async def _find_by_hash(db: AsyncSession, project_id: str, content_hash: str) -> Document | None:
    stmt = select(Document).where(
        Document.project_id == project_id, Document.content_hash == content_hash
    )
    return (await db.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------------------------


@router.post(
    "/projects/{projectId}/documents", status_code=202, response_model=MvpDocument, **_ROUTE
)
async def upload_document(
    projectId: str,
    response: Response,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> MvpDocument:
    _check_project_id(projectId)
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    from pathlib import Path

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

    existing = await _find_by_hash(db, projectId, content_hash)
    if existing is not None and existing.status == "failed":
        return await _restart_failed(db, existing, content)
    if existing is not None:
        response.status_code = 200
        counts = await _counts(db, projectId, [existing.id])
        return _doc_out(existing, counts.get(str(existing.id), 0), duplicate=True)

    blob_path = f"{projectId}/{content_hash}{ext}"
    blob_file = anyio.Path(settings.blob_dir) / blob_path
    await blob_file.parent.mkdir(parents=True, exist_ok=True)
    await blob_file.write_bytes(content)

    doc = Document(
        project_id=projectId,
        filename=filename,
        mime_type=mime,
        size_bytes=len(content),
        content_hash=content_hash,
        blob_path=blob_path,
        status="uploaded",
        progress={"step": "uploaded", "done": 0, "total": 1},
    )
    db.add(doc)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _find_by_hash(db, projectId, content_hash)
        if existing is None:
            raise
        if existing.status == "failed":
            return await _restart_failed(db, existing, content)
        response.status_code = 200
        counts = await _counts(db, projectId, [existing.id])
        return _doc_out(existing, counts.get(str(existing.id), 0), duplicate=True)
    await db.refresh(doc)
    await start_document_graph(str(doc.id))
    return _doc_out(doc, 0)


async def _restart_failed(db: AsyncSession, doc: Document, content: bytes) -> MvpDocument:
    settings = get_settings()
    from pathlib import Path

    blob_file = anyio.Path(settings.blob_dir) / (doc.blob_path or "")
    if not doc.blob_path or not await blob_file.is_file():
        ext = Path(doc.filename).suffix.lower()
        doc.blob_path = f"{doc.project_id}/{doc.content_hash}{ext}"
        blob_file = anyio.Path(settings.blob_dir) / doc.blob_path
        await blob_file.parent.mkdir(parents=True, exist_ok=True)
        await blob_file.write_bytes(content)
    doc.status = "uploaded"
    doc.error = None
    doc.markdown = None
    doc.progress = {"step": "uploaded", "done": 0, "total": 1}
    await db.commit()
    await start_document_graph(str(doc.id))
    return _doc_out(doc, 0)


@router.get(
    "/projects/{projectId}/documents", response_model=list[MvpDocument], **_ROUTE
)
async def list_documents(
    projectId: str, db: AsyncSession = Depends(get_db)
) -> list[MvpDocument]:
    _check_project_id(projectId)
    docs = (
        await db.execute(
            select(Document)
            .where(Document.project_id == projectId)
            .order_by(Document.created_at.desc())
        )
    ).scalars().all()
    counts = await _counts(db, projectId, [d.id for d in docs])
    return [_doc_out(d, counts.get(str(d.id), 0)) for d in docs]


@router.get(
    "/projects/{projectId}/documents/{documentId}", response_model=MvpDocument, **_ROUTE
)
async def get_document(
    projectId: str, documentId: str, db: AsyncSession = Depends(get_db)
) -> MvpDocument:
    _check_project_id(projectId)
    doc_id = _as_uuid(documentId)
    doc = None
    if doc_id is not None:
        doc = (
            await db.execute(
                select(Document).where(Document.project_id == projectId, Document.id == doc_id)
            )
        ).scalar_one_or_none()
    if doc is None:
        raise _not_found(
            "Document", documentId, projectId, "Refresh the Sources view for the current list."
        )
    counts = await _counts(db, projectId, [doc.id])
    return _doc_out(doc, counts.get(str(doc.id), 0))


@router.get(
    "/projects/{projectId}/documents/{documentId}/markdown",
    response_model=DocumentMarkdown,
    **_ROUTE,
)
async def get_document_markdown(
    projectId: str, documentId: str, db: AsyncSession = Depends(get_db)
) -> DocumentMarkdown:
    _check_project_id(projectId)
    doc_id = _as_uuid(documentId)
    doc = None
    if doc_id is not None:
        doc = (
            await db.execute(
                select(Document).where(Document.project_id == projectId, Document.id == doc_id)
            )
        ).scalar_one_or_none()
    if doc is None:
        raise _not_found("Document", documentId, projectId, "Refresh the Sources view.")
    if not doc.markdown:
        raise _error(
            409,
            "Markdown is not ready yet.",
            f"Document status is {doc.status!r}.",
            "Wait until extraction finishes, then open the source again.",
        )
    return DocumentMarkdown(markdown=doc.markdown)


# ---------------------------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------------------------


@router.get("/projects/{projectId}/features", response_model=list[FeatureOut], **_ROUTE)
async def list_features(projectId: str, db: AsyncSession = Depends(get_db)) -> list[FeatureOut]:
    _check_project_id(projectId)
    rows = (
        await db.execute(
            select(Feature)
            .options(*_feature_load())
            .where(Feature.project_id == projectId)
            .order_by(Feature.position, Feature.created_at)
        )
    ).scalars().all()
    return [_feature_out(f) for f in rows]


@router.get("/projects/{projectId}/features/{featureId}", response_model=FeatureOut, **_ROUTE)
async def get_feature(
    projectId: str, featureId: str, db: AsyncSession = Depends(get_db)
) -> FeatureOut:
    _check_project_id(projectId)
    fid = _as_uuid(featureId)
    feature = None
    if fid is not None:
        feature = (
            await db.execute(
                select(Feature)
                .options(*_feature_load())
                .where(Feature.project_id == projectId, Feature.id == fid)
            )
        ).scalar_one_or_none()
    if feature is None:
        raise _not_found("Feature", featureId, projectId, "Refresh the Features view.")
    return _feature_out(feature)


@router.patch("/projects/{projectId}/features/{featureId}", response_model=FeatureOut, **_ROUTE)
async def patch_feature(
    projectId: str, featureId: str, body: FeaturePatch, db: AsyncSession = Depends(get_db)
) -> FeatureOut:
    _check_project_id(projectId)
    fid = _as_uuid(featureId)
    feature = None
    if fid is not None:
        feature = (
            await db.execute(
                select(Feature)
                .options(*_feature_load())
                .where(Feature.project_id == projectId, Feature.id == fid)
            )
        ).scalar_one_or_none()
    if feature is None:
        raise _not_found("Feature", featureId, projectId, "Refresh the Features view.")

    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        name = str(data["name"]).strip()
        if not name:
            raise _error(
                422,
                "A feature name is required.",
                "The name field is empty.",
                "Enter a name, then save.",
            )
        feature.name = name
    if "summary" in data and data["summary"] is not None:
        feature.summary = str(data["summary"]).strip()

    new_review = data.get("review_status")
    if "review_status" in data and new_review is not None:
        if new_review not in {"pending", "approved", "rejected"}:
            raise _error(
                422,
                "Invalid review status.",
                f"{new_review!r} is not a review status.",
                "Use pending, approved, or rejected.",
            )
        if new_review == "approved":
            open_n = sum(1 for q in (feature.questions or []) if q.status == "open")
            if open_n:
                noun = "questions" if open_n != 1 else "question"
                raise _error(
                    409,
                    "This feature still has open questions.",
                    f"{open_n} {noun} still need an answer or a skip.",
                    "Answer or skip the remaining questions, then approve.",
                )
        # Reject (and approve) never start the task graph — generation is a separate POST.
        feature.review_status = new_review

    if "review_status" in data and new_review in {"approved", "rejected"}:
        verb = "approved" if new_review == "approved" else "rejected"
        _append_chat(
            db,
            project_id=projectId,
            role="pm",
            text=f"You {verb}: {feature.name}",
            kind="decision",
            feature_id=feature.id,
        )
    elif "name" in data or "summary" in data:
        _append_chat(
            db,
            project_id=projectId,
            role="pm",
            text=f"You updated: {feature.name}",
            kind="decision",
            feature_id=feature.id,
        )

    await db.commit()
    feature = (
        await db.execute(
            select(Feature).options(*_feature_load()).where(Feature.id == feature.id)
        )
    ).scalar_one()
    return _feature_out(feature)


@router.get(
    "/projects/{projectId}/features/{featureId}/activity",
    response_model=list[AgentActivity],
    **_ROUTE,
)
async def feature_activity(
    projectId: str, featureId: str, db: AsyncSession = Depends(get_db)
) -> list[AgentActivity]:
    _check_project_id(projectId)
    fid = _as_uuid(featureId)
    if fid is None:
        raise _not_found("Feature", featureId, projectId, "Refresh the Features view.")
    exists = await db.scalar(
        select(func.count()).where(Feature.project_id == projectId, Feature.id == fid)
    )
    if not exists:
        raise _not_found("Feature", featureId, projectId, "Refresh the Features view.")
    rows = (
        await db.execute(
            select(AuditEvent)
            .where(AuditEvent.project_id == projectId, AuditEvent.feature_id == fid)
            .order_by(AuditEvent.ts, AuditEvent.id)
        )
    ).scalars().all()
    # Also include document-level extract/merge rows that mention this run — keep it
    # to rows keyed by this feature, plus recent document-graph rows for the project
    # would be noisy. The persist node writes one row per feature.
    out: list[AgentActivity] = []
    for ev in rows:
        detail = ev.detail or {}
        out.append(
            AgentActivity(
                id=str(ev.id),
                ts=ev.ts,
                graph=ev.graph,
                node=ev.node,
                agent=str(detail.get("agent") or ev.type),
                detail=str(detail.get("detail") or ev.type),
            )
        )
    return out


@router.post(
    "/projects/{projectId}/features/{featureId}/tasks/generate",
    status_code=202,
    response_model=FeatureOut,
    **_ROUTE,
)
async def generate_tasks(
    projectId: str, featureId: str, db: AsyncSession = Depends(get_db)
) -> FeatureOut:
    _check_project_id(projectId)
    fid = _as_uuid(featureId)
    feature = None
    if fid is not None:
        feature = (
            await db.execute(
                select(Feature)
                .options(*_feature_load())
                .where(Feature.project_id == projectId, Feature.id == fid)
            )
        ).scalar_one_or_none()
    if feature is None:
        raise _not_found("Feature", featureId, projectId, "Refresh the Features view.")
    if feature.review_status == "rejected":
        raise _error(
            409,
            "Rejected features do not generate tasks.",
            f"{feature.name!r} is rejected.",
            "Approve the feature, or generate tasks from a different one.",
        )
    if feature.status != "planning":
        feature.status = "planning"
        await db.commit()
        feature = (
            await db.execute(
                select(Feature)
                .options(*_feature_load())
                .where(Feature.id == feature.id)
            )
        ).scalar_one()
    await start_task_graph(str(feature.id))
    return _feature_out(feature)


# ---------------------------------------------------------------------------------------------
# Clarification
# ---------------------------------------------------------------------------------------------


async def _history(db: AsyncSession, project_id: str) -> list[ChatMessageOut]:
    rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.project_id == project_id)
            .order_by(ChatMessage.created_at, ChatMessage.id)
        )
    ).scalars().all()
    return [_chat_out(m) for m in rows]


def _interrupt_next(snapshot: Any) -> ClarificationNext | None:
    tasks = getattr(snapshot, "tasks", None) or []
    for task in tasks:
        interrupts = getattr(task, "interrupts", None) or ()
        for item in interrupts:
            value = getattr(item, "value", item)
            if isinstance(value, dict) and value.get("questionId"):
                return ClarificationNext(
                    question_id=str(value["questionId"]),
                    feature_id=str(value.get("featureId") or ""),
                    feature_name=str(value.get("featureName") or ""),
                    question=str(value.get("question") or ""),
                    why=str(value.get("why") or ""),
                )
    values = getattr(snapshot, "values", None) or {}
    if values.get("question_id") and not values.get("done"):
        return ClarificationNext(
            question_id=str(values["question_id"]),
            feature_id=str(values.get("feature_id") or ""),
            feature_name=str(values.get("feature_name") or ""),
            question=str(values.get("question") or ""),
            why=str(values.get("why") or ""),
        )
    return None


async def _clarification_snapshot(project_id: str):
    from app.agents.graphs.clarification import run_clarification_start

    return await run_clarification_start(project_id)


@router.get(
    "/projects/{projectId}/clarification", response_model=ClarificationState, **_ROUTE
)
async def get_clarification(
    projectId: str, db: AsyncSession = Depends(get_db)
) -> ClarificationState:
    _check_project_id(projectId)
    remaining = int(
        await db.scalar(
            select(func.count())
            .select_from(FeatureQuestion)
            .where(FeatureQuestion.project_id == projectId, FeatureQuestion.status == "open")
        )
        or 0
    )
    history = await _history(db, projectId)
    if remaining == 0:
        return ClarificationState(history=history, next=None, remaining=0)
    try:
        snapshot = await _clarification_snapshot(projectId)
        nxt = _interrupt_next(snapshot)
    except Exception as exc:
        raise _error(
            503,
            "Clarification could not start.",
            f"{type(exc).__name__}: {exc}",
            "Check the backend is configured (GCP_PROJECT_ID, Postgres) and retry.",
        ) from exc
    return ClarificationState(history=await _history(db, projectId), next=nxt, remaining=remaining)


@router.get("/projects/{projectId}/workflow", response_model=WorkflowState, **_ROUTE)
async def get_workflow(projectId: str, db: AsyncSession = Depends(get_db)) -> WorkflowState:
    """Full chat history, including decisions — not just the current question."""
    _check_project_id(projectId)
    return WorkflowState(history=await _history(db, projectId))


@router.post(
    "/projects/{projectId}/clarification/answer",
    response_model=ClarificationAnswerResponse,
    **_ROUTE,
)
async def answer_clarification(
    projectId: str,
    body: ClarificationAnswerRequest,
    db: AsyncSession = Depends(get_db),
) -> ClarificationAnswerResponse:
    _check_project_id(projectId)
    qid = _as_uuid(body.question_id)
    q = None
    if qid is not None:
        q = (
            await db.execute(
                select(FeatureQuestion).where(
                    FeatureQuestion.project_id == projectId, FeatureQuestion.id == qid
                )
            )
        ).scalar_one_or_none()
    if q is None:
        raise _not_found("Question", body.question_id, projectId, "Refresh the clarification chat.")
    if q.status != "open":
        raise _error(
            409,
            "This question was already handled.",
            f"It is {q.status}.",
            "Refresh the chat for the next question.",
        )
    if not body.answer.strip():
        raise _error(
            422,
            "An answer is required.",
            "The answer field is empty.",
            "Type an answer, or skip the question.",
        )
    from app.agents.graphs.clarification import run_clarification_resume

    try:
        snapshot = await run_clarification_resume(
            projectId, {"answer": body.answer.strip(), "question_id": body.question_id}
        )
    except Exception as exc:
        raise _error(
            503,
            "The answer could not be applied.",
            f"{type(exc).__name__}: {exc}",
            "Retry. If it keeps failing, check the backend logs.",
        ) from exc
    await db.refresh(q)
    feature = (
        await db.execute(
            select(Feature).options(*_feature_load()).where(Feature.id == q.feature_id)
        )
    ).scalar_one()
    remaining = int(
        await db.scalar(
            select(func.count())
            .select_from(FeatureQuestion)
            .where(FeatureQuestion.project_id == projectId, FeatureQuestion.status == "open")
        )
        or 0
    )
    changes = list((getattr(snapshot, "values", None) or {}).get("changes") or [])
    return ClarificationAnswerResponse(
        feature=_feature_out(feature),
        changes=changes,
        next=_interrupt_next(snapshot),
        remaining=remaining,
    )


@router.post(
    "/projects/{projectId}/clarification/skip",
    response_model=ClarificationAnswerResponse,
    **_ROUTE,
)
async def skip_clarification(
    projectId: str,
    body: ClarificationSkipRequest,
    db: AsyncSession = Depends(get_db),
) -> ClarificationAnswerResponse:
    _check_project_id(projectId)
    qid = _as_uuid(body.question_id)
    q = None
    if qid is not None:
        q = (
            await db.execute(
                select(FeatureQuestion).where(
                    FeatureQuestion.project_id == projectId, FeatureQuestion.id == qid
                )
            )
        ).scalar_one_or_none()
    if q is None:
        raise _not_found("Question", body.question_id, projectId, "Refresh the clarification chat.")
    if q.status != "open":
        raise _error(
            409,
            "This question was already handled.",
            f"It is {q.status}.",
            "Refresh the chat for the next question.",
        )
    from app.agents.graphs.clarification import run_clarification_resume

    try:
        snapshot = await run_clarification_resume(
            projectId, {"skip": True, "question_id": body.question_id}
        )
    except Exception as exc:
        raise _error(
            503,
            "The question could not be skipped.",
            f"{type(exc).__name__}: {exc}",
            "Retry. If it keeps failing, check the backend logs.",
        ) from exc
    remaining = int(
        await db.scalar(
            select(func.count())
            .select_from(FeatureQuestion)
            .where(FeatureQuestion.project_id == projectId, FeatureQuestion.status == "open")
        )
        or 0
    )
    return ClarificationAnswerResponse(
        feature=None,
        changes=["Skipped"],
        next=_interrupt_next(snapshot),
        remaining=remaining,
    )


@router.post(
    "/projects/{projectId}/clarification/skip-remaining",
    response_model=ClarificationAnswerResponse,
    **_ROUTE,
)
async def skip_remaining_clarification(
    projectId: str,
    body: ClarificationSkipRemainingRequest,
    db: AsyncSession = Depends(get_db),
) -> ClarificationAnswerResponse:
    """Human skip of every open question on one feature. Never auto-answers."""
    _check_project_id(projectId)
    fid = _as_uuid(body.feature_id)
    feature = None
    if fid is not None:
        feature = (
            await db.execute(
                select(Feature)
                .options(*_feature_load())
                .where(Feature.project_id == projectId, Feature.id == fid)
            )
        ).scalar_one_or_none()
    if feature is None:
        raise _not_found("Feature", body.feature_id, projectId, "Refresh the Features view.")

    open_before = sum(1 for q in (feature.questions or []) if q.status == "open")
    snapshot = None
    if open_before:
        try:
            from app.agents.graphs.clarification import (
                peek_clarification_state,
                run_clarification_resume,
            )

            snapshot = await peek_clarification_state(projectId)
            while snapshot is not None:
                nxt = _interrupt_next(snapshot)
                if nxt is None or nxt.feature_id != str(feature.id):
                    break
                snapshot = await run_clarification_resume(
                    projectId, {"skip": True, "question_id": nxt.question_id}
                )
        except Exception:
            snapshot = None

        from app.agents.graphs.clarification import skip_open_questions_in_db

        await skip_open_questions_in_db(projectId, feature.id)
        _append_chat(
            db,
            project_id=projectId,
            role="pm",
            text=f"You skipped remaining questions on {feature.name}",
            kind="decision",
            feature_id=feature.id,
        )
        await db.commit()

    feature = (
        await db.execute(
            select(Feature).options(*_feature_load()).where(Feature.id == feature.id)
        )
    ).scalar_one()
    remaining = int(
        await db.scalar(
            select(func.count())
            .select_from(FeatureQuestion)
            .where(FeatureQuestion.project_id == projectId, FeatureQuestion.status == "open")
        )
        or 0
    )
    return ClarificationAnswerResponse(
        feature=_feature_out(feature),
        changes=["Skipped remaining"] if open_before else [],
        next=_interrupt_next(snapshot) if snapshot is not None else None,
        remaining=remaining,
    )


# ---------------------------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------------------------


@router.patch("/projects/{projectId}/tasks/{taskId}", response_model=GeneratedTaskOut, **_ROUTE)
async def patch_task(
    projectId: str, taskId: str, body: TaskPatch, db: AsyncSession = Depends(get_db)
) -> GeneratedTaskOut:
    _check_project_id(projectId)
    tid = _as_uuid(taskId)
    task = None
    if tid is not None:
        task = (
            await db.execute(
                select(Task).where(Task.project_id == projectId, Task.id == tid)
            )
        ).scalar_one_or_none()
    if task is None:
        raise _not_found("Task", taskId, projectId, "Refresh the Features view.")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] is not None:
        if data["status"] not in {"draft", "approved", "on_board"}:
            raise _error(
                422,
                "Invalid task status.",
                f"{data['status']!r} is not a task status.",
                "Use draft, approved, or on_board.",
            )
        task.status = data["status"]
    if "title" in data and data["title"] is not None:
        task.title = data["title"]
    if "description" in data and data["description"] is not None:
        task.description = data["description"]
    if "priority" in data and data["priority"] is not None:
        task.priority = data["priority"]
    if "board_item_id" in data and data["board_item_id"] is not None:
        task.board_item_id = data["board_item_id"]
        task.status = "on_board"
    if "subtasks" in data and data["subtasks"] is not None:
        task.subtasks = list(data["subtasks"])
    if "definition_of_done" in data and data["definition_of_done"] is not None:
        task.definition_of_done = list(data["definition_of_done"])
    await db.commit()
    await db.refresh(task)
    return _task_out(task)


# ---------------------------------------------------------------------------------------------
# Ask-a-task (drawer Ask tab)
# ---------------------------------------------------------------------------------------------


@router.post("/projects/{projectId}/ask", response_model=AskResponse, **_ROUTE)
async def ask_about_item(
    projectId: str, body: AskRequest, db: AsyncSession = Depends(get_db)
) -> AskResponse:
    """Cited answer scoped to one board card. Does not write chat_messages."""
    from app.agents.ask import ask_about_item as run_ask
    from app.agents.llm import VertexNotConfigured

    _check_project_id(projectId)
    if not body.query.strip():
        raise _error(
            422,
            "A question is required.",
            "The query field is empty.",
            "Type a question about this card, then send.",
        )
    try:
        return await run_ask(db, project_id=projectId, body=body)
    except VertexNotConfigured as exc:
        err = exc.as_error()
        raise _error(400, err["problem"], err["cause"], err["fix"]) from exc
    except Exception as exc:
        raise _error(
            503,
            "The question could not be answered.",
            f"{type(exc).__name__}: {exc}",
            "Retry. If it keeps failing, check the backend logs and GCP_PROJECT_ID.",
        ) from exc


# ---------------------------------------------------------------------------------------------
# Project Memory Ask (Memory nav — not the card-drawer Ask tab)
# ---------------------------------------------------------------------------------------------


@router.post("/projects/{projectId}/memory/ask", response_model=AskResponse, **_ROUTE)
async def ask_project_memory(
    projectId: str, body: MemoryAskRequest, db: AsyncSession = Depends(get_db)
) -> AskResponse:
    """Cited answer over docs, features, and tasks. Does not write chat_messages."""
    from app.agents.llm import VertexNotConfigured
    from app.agents.memory import ask_project_memory as run_memory

    _check_project_id(projectId)
    if not body.query.strip():
        raise _error(
            422,
            "A question is required.",
            "The query field is empty.",
            "Type a question about this project's documents, features, or tasks, then send.",
        )
    try:
        return await run_memory(db, project_id=projectId, body=body)
    except VertexNotConfigured as exc:
        err = exc.as_error()
        raise _error(400, err["problem"], err["cause"], err["fix"]) from exc
    except Exception as exc:
        raise _error(
            503,
            "The question could not be answered.",
            f"{type(exc).__name__}: {exc}",
            "Retry. If it keeps failing, check the backend logs and GCP_PROJECT_ID.",
        ) from exc


# ---------------------------------------------------------------------------------------------
# Trace impact Explain (selected subgraph only)
# ---------------------------------------------------------------------------------------------


@router.post(
    "/projects/{projectId}/impact/explain",
    response_model=ImpactExplainResponse,
    **_ROUTE,
)
async def explain_impact(
    projectId: str, body: ImpactExplainRequest
) -> ImpactExplainResponse:
    """Cited summary of a selected subgraph. Does not write chat_messages."""
    from app.agents.impact import explain_impact as run_explain
    from app.agents.llm import VertexNotConfigured

    _check_project_id(projectId)
    if not body.node_id.strip() or not body.node.id.strip():
        raise _error(
            422,
            "A selected node is required.",
            "The nodeId or node snapshot is empty.",
            "Click a node on the Trace graph, then explain.",
        )
    try:
        return await run_explain(body)
    except VertexNotConfigured as exc:
        err = exc.as_error()
        raise _error(400, err["problem"], err["cause"], err["fix"]) from exc
    except Exception as exc:
        raise _error(
            503,
            "The impact could not be explained.",
            f"{type(exc).__name__}: {exc}",
            "Retry. If it keeps failing, check the backend logs and GCP_PROJECT_ID.",
        ) from exc


# ---------------------------------------------------------------------------------------------
# Author documents (BRD / tech spec / task tree — in-memory draft)
# ---------------------------------------------------------------------------------------------


@router.post("/projects/{projectId}/author", response_model=AuthorResponse, **_ROUTE)
async def author_document(
    projectId: str, body: AuthorRequest, db: AsyncSession = Depends(get_db)
) -> AuthorResponse:
    """Cited BRD / spec / task tree from project memory. Does not write chat_messages."""
    from app.agents.author import author_document as run_author
    from app.agents.llm import VertexNotConfigured

    _check_project_id(projectId)
    if not (body.type or "").strip():
        raise _error(
            422,
            "A document type is required.",
            "The type field is empty.",
            "Choose BRD, tech spec, or task tree, then generate.",
        )
    try:
        return await run_author(db, project_id=projectId, body=body)
    except VertexNotConfigured as exc:
        err = exc.as_error()
        raise _error(400, err["problem"], err["cause"], err["fix"]) from exc
    except Exception as exc:
        raise _error(
            503,
            "The document could not be drafted.",
            f"{type(exc).__name__}: {exc}",
            "Retry. If it keeps failing, check the backend logs and GCP_PROJECT_ID.",
        ) from exc


# ---------------------------------------------------------------------------------------------
# Verdict (manual add / edit — task-vs-task)
# ---------------------------------------------------------------------------------------------


@router.post(
    "/projects/{projectId}/verdicts/check", response_model=VerdictDetail, **_ROUTE
)
async def check_item_verdict(
    projectId: str, body: VerdictCheckRequest, db: AsyncSession = Depends(get_db)
) -> VerdictDetail:
    """Classify a new or edited board card. Does not write chat_messages or the board."""
    from app.agents.llm import VertexNotConfigured
    from app.agents.verdict import check_verdict as run_check

    _check_project_id(projectId)
    if not body.item.title.strip():
        raise _error(
            422,
            "A card title is required.",
            "The item title is empty.",
            "Give the card a title, then check again.",
        )
    try:
        return await run_check(db, project_id=projectId, body=body)
    except VertexNotConfigured as exc:
        err = exc.as_error()
        raise _error(400, err["problem"], err["cause"], err["fix"]) from exc
    except Exception as exc:
        raise _error(
            503,
            "The verdict could not be computed.",
            f"{type(exc).__name__}: {exc}",
            "Retry. If it keeps failing, check the backend logs and GCP_PROJECT_ID.",
        ) from exc


# ---------------------------------------------------------------------------------------------
# Startup recovery
# ---------------------------------------------------------------------------------------------


async def recover_stuck_documents() -> None:
    """Mark documents left running across a restart as failed (plans/mvp-v0.md)."""
    import logging

    try:
        async with get_session_factory()() as db:
            rows = (
                await db.execute(select(Document).where(Document.status.in_(list(_RUNNING))))
            ).scalars().all()
            for doc in rows:
                doc.status = "failed"
                doc.error = error_json(
                    "Processing stopped.",
                    "The server restarted while this document was still running.",
                    "Re-upload the file to start again.",
                )
            if rows:
                await db.commit()
    except Exception:
        logging.getLogger(__name__).exception("startup recovery skipped")
