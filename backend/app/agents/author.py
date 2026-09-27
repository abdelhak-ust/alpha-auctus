"""Author documents — cited BRD / tech spec / task tree (plans/author-documents.md).

Uses `get_chat_model()` only. Never imports the Vertex/Gemini SDK.
Does not persist the draft. Does not write chat_messages.
Does not dump full document markdown into the prompt — keyword passages only.
Reuses Memory Ask loaders and `keyword_passages`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import get_chat_model
from app.agents.memory import (
    _add_allowed,
    _append_document_passages,
    _append_features,
    _append_tasks,
    _digits,
    _item_id,
    load_features,
    load_ready_documents,
    load_tasks,
)
from app.agents.prompts import AUTHOR
from app.models import Feature, Task
from app.schemas.mvp import (
    AskCitation,
    AskLlmCitation,
    AuthorBoardItem,
    AuthorConflict,
    AuthorDecision,
    AuthorRequest,
    AuthorResponse,
    AuthorResult,
)

_TYPE_LABEL = {"brd": "BRD", "spec": "tech spec", "tree": "task tree"}


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def _is_all(area: str) -> bool:
    return _norm(area) in {"", "all"}


def _matches_area(value: str, area: str) -> bool:
    if _is_all(area):
        return True
    needle = _norm(area)
    hay = _norm(value)
    if not hay:
        return False
    return hay == needle or needle in hay or hay in needle


def _parse_created(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def within_time_frame(created_at: str | None, time_frame: str) -> bool:
    """Keep items with no parseable date; otherwise last `time_frame` days."""
    dt = _parse_created(created_at)
    if dt is None:
        return True
    try:
        days = int(str(time_frame).strip())
    except ValueError:
        return True
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return dt >= cutoff


def filter_features_and_tasks(
    features: list[Feature],
    tasks: list[Task],
    *,
    area: str,
) -> tuple[list[Feature], list[Task]]:
    """Features whose name or a child task area matches; all tasks of those features."""
    by_feat: dict[UUID, list[Task]] = {}
    for task in tasks:
        by_feat.setdefault(task.feature_id, []).append(task)
    if _is_all(area):
        return list(features), list(tasks)
    kept: list[Feature] = []
    for feature in features:
        feat_tasks = by_feat.get(feature.id, [])
        if _matches_area(feature.name, area) or any(
            _matches_area(task.area, area) for task in feat_tasks
        ):
            kept.append(feature)
    kept_ids = {feature.id for feature in kept}
    return kept, [task for task in tasks if task.feature_id in kept_ids]


def filter_board_items(
    board_items: list[AuthorBoardItem],
    *,
    area: str,
    time_frame: str,
) -> list[AuthorBoardItem]:
    return [
        item
        for item in board_items
        if _matches_area(item.area, area) and within_time_frame(item.created_at, time_frame)
    ]


def filter_decisions(
    decisions: list[AuthorDecision], *, area: str
) -> list[AuthorDecision]:
    return [d for d in decisions if _matches_area(d.area, area)]


def conflicts_in_scope(board_items: list[AuthorBoardItem]) -> list[AuthorConflict]:
    return [
        AuthorConflict(id=str(item.id), title=item.title)
        for item in board_items
        if (item.verdict_type or "").strip().lower() == "conflict"
    ]


def _decision_id(raw: str) -> str:
    digits = _digits(raw)
    if digits:
        return f"decision-{digits}"
    stripped = raw.strip()
    if stripped.startswith("decision-"):
        return stripped
    return f"decision-{stripped}" if stripped else stripped


def _passage_query(
    *,
    area: str,
    features: list[Feature],
    tasks: list[Task],
    board_items: list[AuthorBoardItem],
) -> str:
    parts: list[str] = []
    if not _is_all(area):
        parts.append(area)
    parts.extend(feature.name for feature in features if feature.name)
    parts.extend(task.title for task in tasks if task.title)
    parts.extend(item.title for item in board_items if item.title)
    return " ".join(parts)


def _append_board(
    parts: list[str], allowed: list[AskCitation], *, board_items: list[AuthorBoardItem]
) -> None:
    parts.extend(["", "## Board snapshot (client-owned cards, including hand-created)"])
    if not board_items:
        parts.append("(none)")
        return
    for card in board_items:
        cid = _item_id(_digits(card.id) or card.id)
        parts.append(
            f"- id: {cid} title: {card.title!r} area: {card.area or '(none)'} "
            f"status: {card.status or '(none)'} created_at: {card.created_at or '(none)'} "
            f"verdict: {card.verdict_type or '(none)'} "
            f"description: {card.description or '(none)'}"
        )
        snippet = card.description.strip() or None
        _add_allowed(
            allowed,
            AskCitation(id=cid, type="item", title=card.title, snippet=snippet),
        )


def _append_decisions(
    parts: list[str], allowed: list[AskCitation], *, decisions: list[AuthorDecision]
) -> None:
    parts.extend(["", "## Decisions (client-supplied only — do not invent others)"])
    if not decisions:
        parts.append("(none)")
        return
    for decision in decisions:
        cid = _decision_id(decision.id)
        parts.append(
            f"- id: {cid} title: {decision.title!r} area: {decision.area or '(none)'} "
            f"description: {decision.description or '(none)'}"
        )
        snippet = decision.description.strip() or None
        _add_allowed(
            allowed,
            AskCitation(id=cid, type="decision", title=decision.title, snippet=snippet),
        )


def assemble_author_context(
    *,
    query: str,
    documents: list,
    features: list[Feature],
    tasks: list[Task],
    board_items: list[AuthorBoardItem],
    decisions: list[AuthorDecision],
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
    _append_decisions(parts, allowed, decisions=decisions)

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
    """Keep item/source ids from the catalog. Decisions only if the client supplied them."""
    by_key = {(c.type, c.id): c for c in allowed}
    item_by_digits = {_digits(c.id): c for c in allowed if c.type == "item" and _digits(c.id)}
    decision_by_digits = {
        _digits(c.id): c for c in allowed if c.type == "decision" and _digits(c.id)
    }
    source_ids = {c.id for c in allowed if c.type == "source"}

    kept: list[AskCitation] = []
    seen: set[tuple[str, str]] = set()
    for raw in emitted:
        out: AskCitation | None
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
        elif raw.type == "decision":
            cit = by_key.get(("decision", raw.id))
            if cit is None:
                cit = by_key.get(("decision", _decision_id(raw.id)))
            if cit is None:
                cit = decision_by_digits.get(_digits(raw.id))
            if cit is None:
                continue
            out = AskCitation(
                id=cit.id,
                type="decision",
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


def _parse_result(result: object) -> AuthorResult:
    if isinstance(result, AuthorResult):
        return result
    if isinstance(result, dict):
        return AuthorResult.model_validate(result)
    return AuthorResult()


def scope_is_empty(
    *,
    features: list[Feature],
    tasks: list[Task],
    board_items: list[AuthorBoardItem],
    decisions: list[AuthorDecision],
    allowed: list[AskCitation],
) -> bool:
    return (
        not features
        and not tasks
        and not board_items
        and not decisions
        and not allowed
    )


async def author_document(
    db: AsyncSession, *, project_id: str, body: AuthorRequest
) -> AuthorResponse:
    documents = await load_ready_documents(db, project_id=project_id)
    features = await load_features(db, project_id=project_id)
    tasks = await load_tasks(db, project_id=project_id)

    area = (body.area or "all").strip() or "all"
    scoped_features, scoped_tasks = filter_features_and_tasks(
        features, tasks, area=area
    )
    scoped_board = filter_board_items(
        list(body.board_items or []), area=area, time_frame=body.time_frame
    )
    scoped_decisions = filter_decisions(list(body.decisions or []), area=area)
    conflicts = conflicts_in_scope(scoped_board)

    query = _passage_query(
        area=area,
        features=scoped_features,
        tasks=scoped_tasks,
        board_items=scoped_board,
    )
    context, allowed = assemble_author_context(
        query=query,
        documents=documents,
        features=scoped_features,
        tasks=scoped_tasks,
        board_items=scoped_board,
        decisions=scoped_decisions,
    )

    label = _TYPE_LABEL.get(body.type, body.type)
    empty_note = ""
    if scope_is_empty(
        features=scoped_features,
        tasks=scoped_tasks,
        board_items=scoped_board,
        decisions=scoped_decisions,
        allowed=allowed,
    ):
        empty_note = (
            "\n\nThe assembled scope is empty. Say so. Do not invent work. "
            "Do not emit an SSO/CSV sample or Decision #4."
        )

    model = get_chat_model().with_structured_output(AuthorResult)
    result = await model.ainvoke(
        [
            SystemMessage(content=AUTHOR),
            HumanMessage(
                content=(
                    f"Document type: {label} ({body.type})\n"
                    f"Area: {area}\n"
                    f"Time frame: last {body.time_frame} days\n\n"
                    f"{context}{empty_note}"
                )
            ),
        ]
    )
    parsed = _parse_result(result)
    return AuthorResponse(
        document=parsed.document,
        unresolved_conflicts_count=len(conflicts),
        conflicts=conflicts,
        citations=filter_citations(parsed.citations, allowed=allowed),
    )
