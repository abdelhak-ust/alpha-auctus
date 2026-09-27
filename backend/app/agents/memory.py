"""Project Memory Ask — cited answer over docs, features, and tasks (plans/project-memory-ask.md).

Uses `get_chat_model()` only. Never imports the Vertex/Gemini SDK.
Does not persist turns (chat_messages is the project workflow thread).
Does not dump full document markdown into the prompt — keyword passages only.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.llm import get_chat_model
from app.agents.prompts import MEMORY_ASK
from app.agents.tools import keyword_passages
from app.models import Document, Feature, Task
from app.schemas.mvp import (
    AskCitation,
    AskLlmCitation,
    AskResponse,
    AskResult,
    AskTurn,
    MemoryAskRequest,
    MemoryBoardItem,
)

_HISTORY_LIMIT = 8
_MAX_PASSAGES_PER_DOC = 3
_MAX_TOTAL_PASSAGE_CHARS = 8000


async def load_ready_documents(db: AsyncSession, *, project_id: str) -> list[Document]:
    stmt = (
        select(Document)
        .where(
            Document.project_id == project_id,
            Document.status == "ready",
            Document.markdown.is_not(None),
        )
        .order_by(Document.created_at, Document.id)
    )
    return [d for d in (await db.execute(stmt)).scalars().all() if (d.markdown or "").strip()]


async def load_features(db: AsyncSession, *, project_id: str) -> list[Feature]:
    stmt = (
        select(Feature)
        .where(Feature.project_id == project_id)
        .options(selectinload(Feature.questions), selectinload(Feature.document))
        .order_by(Feature.position, Feature.created_at)
    )
    return list((await db.execute(stmt)).scalars().all())


async def load_tasks(db: AsyncSession, *, project_id: str) -> list[Task]:
    """All generated tasks — draft, approved, and on_board."""
    stmt = (
        select(Task)
        .where(Task.project_id == project_id)
        .options(selectinload(Task.feature))
        .order_by(Task.ordinal, Task.id)
    )
    return list((await db.execute(stmt)).scalars().all())


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _item_id(board_item_id: int | str) -> str:
    return f"item-{board_item_id}"


def _add_allowed(allowed: list[AskCitation], citation: AskCitation) -> None:
    key = (citation.type, citation.id)
    if any((c.type, c.id) == key for c in allowed):
        return
    allowed.append(citation)


def _format_history(history: list[AskTurn]) -> str:
    recent = history[-_HISTORY_LIMIT:]
    if not recent:
        return "(none)"
    return "\n".join(f"{turn.role}: {turn.text}" for turn in recent)


def _append_document_passages(
    parts: list[str],
    allowed: list[AskCitation],
    *,
    documents: list[Document],
    query: str,
) -> None:
    parts.extend(["", "## Documents (keyword passages — not the full file)"])
    used = 0
    any_passages = False
    for doc in documents:
        markdown = doc.markdown or ""
        hits = keyword_passages(markdown, query, max_hits=_MAX_PASSAGES_PER_DOC)
        if not hits:
            continue
        kept: list[tuple[int, int, int, str]] = []
        for score, start, end, passage in hits:
            text = passage.strip()
            if not text:
                continue
            if used + len(text) > _MAX_TOTAL_PASSAGE_CHARS:
                break
            kept.append((score, start, end, text))
            used += len(text)
        if not kept:
            continue
        any_passages = True
        doc_id = str(doc.id)
        parts.append(f"### {doc.filename} id={doc_id}")
        for score, start, end, text in kept:
            parts.append(f"  [{start}:{end}] (score {score}): {text}")
        _add_allowed(
            allowed,
            AskCitation(
                id=doc_id,
                type="source",
                title=doc.filename,
                snippet=kept[0][3],
            ),
        )
        if used >= _MAX_TOTAL_PASSAGE_CHARS:
            break
    if not any_passages:
        parts.append("(none)")


def _append_features(
    parts: list[str], allowed: list[AskCitation], *, features: list[Feature]
) -> None:
    parts.extend(["", "## Features"])
    if not features:
        parts.append("(none)")
        return
    for feature in features:
        feat_id = f"feat-{feature.id}"
        filename = feature.document.filename if feature.document is not None else ""
        parts.append(f"### {feature.name} id={feat_id}")
        parts.append(f"- summary: {feature.summary}")
        details = feature.details if isinstance(feature.details, dict) else {}
        if details:
            parts.append(f"- details: {details}")
        _add_allowed(
            allowed,
            AskCitation(
                id=feat_id,
                type="source",
                title=feature.name,
                snippet=feature.summary.strip() or None,
            ),
        )

        quotes = feature.source_quotes if isinstance(feature.source_quotes, list) else []
        parts.append("- source quotes:")
        quoted = False
        for i, raw in enumerate(quotes):
            if not isinstance(raw, dict):
                continue
            quote = str(raw.get("quote") or "").strip()
            if not quote:
                continue
            quoted = True
            origin = raw.get("origin") if raw.get("origin") in ("document", "pm") else "document"
            verified = bool(raw.get("verified"))
            label = filename or feature.name or "Source quote"
            cid = f"quote-{feature.id}-{i}"
            parts.append(
                f"  [{cid}] origin={origin} verified={verified} file={label!r}: {quote}"
            )
            _add_allowed(
                allowed,
                AskCitation(id=cid, type="source", title=label, snippet=quote),
            )
        if not quoted:
            parts.append("  (none)")

        answered: list[str] = []
        for q in feature.questions or []:
            if q.status == "answered" and (q.answer or "").strip():
                answered.append(f"  Q: {q.question}\n  A: {q.answer}")
            elif q.status == "skipped":
                answered.append(f"  Q: {q.question}\n  A: (skipped)")
        parts.append("- answered/skipped questions:")
        parts.extend(answered or ["  (none)"])


def _append_tasks(parts: list[str], allowed: list[AskCitation], *, tasks: list[Task]) -> None:
    parts.extend(["", "## Generated tasks (all statuses)"])
    if not tasks:
        parts.append("(none)")
        return
    for task in tasks:
        cite_type: Literal["item", "source"]
        if task.board_item_id is not None:
            cid = _item_id(task.board_item_id)
            cite_type = "item"
        else:
            cid = str(task.id)
            cite_type = "source"
        fname = task.feature.name if task.feature is not None else ""
        parts.append(
            f"- id: {cid} status: {task.status} title: {task.title!r} "
            f"area: {task.area or '(none)'} board_item_id: {task.board_item_id} "
            f"feature: {fname!r}"
        )
        parts.append(f"  description: {task.description or '(none)'}")
        parts.append(f"  acceptance_criteria: {task.acceptance_criteria or []}")
        parts.append(f"  traces_to: {list(task.traces_to or [])}")
        snippet = (task.description or "").strip() or None
        _add_allowed(
            allowed,
            AskCitation(id=cid, type=cite_type, title=task.title, snippet=snippet),
        )


def _append_board(
    parts: list[str], allowed: list[AskCitation], *, board_items: list[MemoryBoardItem]
) -> None:
    parts.extend(["", "## Board snapshot (client-owned cards, including hand-created)"])
    if not board_items:
        parts.append("(none)")
        return
    for card in board_items:
        cid = _item_id(_digits(card.id) or card.id)
        parts.append(
            f"- id: {cid} title: {card.title!r} area: {card.area or '(none)'} "
            f"status: {card.status or '(none)'} description: {card.description or '(none)'}"
        )
        snippet = card.description.strip() or None
        _add_allowed(
            allowed,
            AskCitation(id=cid, type="item", title=card.title, snippet=snippet),
        )


def assemble_memory_context(
    *,
    query: str,
    documents: list[Document],
    features: list[Feature],
    tasks: list[Task],
    board_items: list[MemoryBoardItem],
) -> tuple[str, list[AskCitation]]:
    """Build the prompt block and the citations the model may emit.

    Full document markdown is never included — only scored passage windows.
    """
    allowed: list[AskCitation] = []
    parts: list[str] = []
    _append_document_passages(parts, allowed, documents=documents, query=query)
    _append_features(parts, allowed, features=features)
    _append_tasks(parts, allowed, tasks=tasks)
    _append_board(parts, allowed, board_items=board_items)

    catalog = "\n".join(
        f"- type={c.type} id={c.id} title={c.title!r}"
        + (f" snippet={c.snippet!r}" if c.snippet else "")
        for c in allowed
    ) or "(none)"
    body = "\n".join(parts).lstrip()
    prompt = f"Allowed citations (use these ids; do not invent):\n{catalog}\n\n{body}"
    return prompt, allowed


def filter_citations(
    emitted: list[AskLlmCitation],
    *,
    allowed: list[AskCitation],
) -> list[AskCitation]:
    """Drop fabricated decision ids and anything not in the assembled catalog."""
    by_key = {(c.type, c.id): c for c in allowed}
    item_by_digits = {_digits(c.id): c for c in allowed if c.type == "item" and _digits(c.id)}
    source_ids = {c.id for c in allowed if c.type == "source"}

    kept: list[AskCitation] = []
    seen: set[tuple[str, str]] = set()
    for raw in emitted:
        if raw.type == "decision":
            continue
        if raw.type == "item":
            cit = by_key.get(("item", raw.id))
            if cit is None:
                cit = item_by_digits.get(_digits(raw.id))
            if cit is None:
                continue
            out = AskCitation(
                id=cit.id,
                type="item",
                title=raw.title or cit.title,
                snippet=raw.snippet or cit.snippet,
            )
        elif raw.type == "source" and raw.id in source_ids:
            catalog = by_key[("source", raw.id)]
            out = AskCitation(
                id=raw.id,
                type="source",
                title=raw.title or catalog.title,
                snippet=raw.snippet or catalog.snippet,
            )
        else:
            continue
        key = (out.type, out.id)
        if key in seen:
            continue
        seen.add(key)
        kept.append(out)
    return kept


def _parse_result(result: object) -> AskResult:
    if isinstance(result, AskResult):
        return result
    if isinstance(result, dict):
        return AskResult.model_validate(result)
    return AskResult(answer="", citations=[])


async def ask_project_memory(
    db: AsyncSession, *, project_id: str, body: MemoryAskRequest
) -> AskResponse:
    documents = await load_ready_documents(db, project_id=project_id)
    features = await load_features(db, project_id=project_id)
    tasks = await load_tasks(db, project_id=project_id)
    context, allowed = assemble_memory_context(
        query=body.query.strip(),
        documents=documents,
        features=features,
        tasks=tasks,
        board_items=list(body.board_items or []),
    )
    history_text = _format_history(list(body.history or []))
    model = get_chat_model().with_structured_output(AskResult)
    result = await model.ainvoke(
        [
            SystemMessage(content=MEMORY_ASK),
            HumanMessage(
                content=(
                    f"Query: {body.query.strip()}\n\n{context}\n\n"
                    f"Recent conversation:\n{history_text}"
                )
            ),
        ]
    )
    parsed = _parse_result(result)
    return AskResponse(
        answer=parsed.answer,
        citations=filter_citations(parsed.citations, allowed=allowed),
    )
