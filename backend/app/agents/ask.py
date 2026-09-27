"""Ask-a-task — cited answer scoped to one board card (plans/task-ask-ai.md).

Uses `get_chat_model()` only. Never imports the Vertex/Gemini SDK.
Does not persist turns (chat_messages is the project workflow thread).
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.llm import get_chat_model
from app.agents.prompts import ASK
from app.models import Feature, Task
from app.schemas.mvp import (
    AskCitation,
    AskItemSnapshot,
    AskLlmCitation,
    AskRequest,
    AskResponse,
    AskResult,
    AskTurn,
)

_HISTORY_LIMIT = 8


async def load_published_task(
    db: AsyncSession, *, project_id: str, board_item_id: int
) -> Task | None:
    stmt = (
        select(Task)
        .where(Task.project_id == project_id, Task.board_item_id == board_item_id)
        .options(
            selectinload(Task.feature).options(
                selectinload(Feature.questions),
                selectinload(Feature.document),
            )
        )
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _item_citation(board_item_id: int, item: AskItemSnapshot) -> AskCitation:
    snippet = item.description.strip() or None
    return AskCitation(
        id=f"item-{board_item_id}",
        type="item",
        title=item.title,
        snippet=snippet,
    )


def assemble_ask_context(
    *,
    board_item_id: int,
    item: AskItemSnapshot,
    task: Task | None,
) -> tuple[str, list[AskCitation]]:
    """Build the prompt block and the citations the model may emit."""
    allowed: list[AskCitation] = [_item_citation(board_item_id, item)]
    parts: list[str] = [
        "## This card",
        f"- id: item-{board_item_id}",
        f"- title: {item.title}",
        f"- description: {item.description or '(none)'}",
        f"- area: {item.area or '(none)'}",
        f"- priority: {item.priority or '(not set)'}",
    ]

    if task is not None:
        feature = task.feature
        filename = feature.document.filename if feature.document is not None else ""

        parts.extend(
            [
                "",
                "## Generated task",
                f"- title: {task.title}",
                f"- description: {task.description or '(none)'}",
                f"- area: {task.area or '(none)'}",
                f"- priority: {task.priority}",
                f"- estimate: {task.estimate}",
                f"- subtasks: {list(task.subtasks or [])}",
                f"- acceptance_criteria: {task.acceptance_criteria or []}",
                f"- definition_of_done: {list(task.definition_of_done or [])}",
                f"- traces_to: {list(task.traces_to or [])}",
            ]
        )
        if task.description.strip():
            allowed.append(
                AskCitation(
                    id="task-description",
                    type="source",
                    title="Task description",
                    snippet=task.description.strip(),
                )
            )

        parts.extend(["", f"## Parent feature: {feature.name}", f"- summary: {feature.summary}"])
        details = feature.details if isinstance(feature.details, dict) else {}
        if details:
            parts.append(f"- details: {details}")

        quotes = feature.source_quotes if isinstance(feature.source_quotes, list) else []
        parts.append("- source quotes:")
        if not quotes:
            parts.append("  (none)")
        for i, raw in enumerate(quotes):
            if not isinstance(raw, dict):
                continue
            quote = str(raw.get("quote") or "").strip()
            if not quote:
                continue
            origin = raw.get("origin") if raw.get("origin") in ("document", "pm") else "document"
            verified = bool(raw.get("verified"))
            label = filename or "Source quote"
            cid = f"quote-{i}"
            parts.append(
                f"  [{cid}] origin={origin} verified={verified} file={label!r}: {quote}"
            )
            allowed.append(
                AskCitation(id=cid, type="source", title=label, snippet=quote)
            )

        answered: list[str] = []
        for q in feature.questions or []:
            if q.status == "answered" and (q.answer or "").strip():
                answered.append(f"  Q: {q.question}\n  A: {q.answer}")
            elif q.status == "skipped":
                answered.append(f"  Q: {q.question}\n  A: (skipped)")
        parts.append("- answered/skipped questions:")
        parts.extend(answered or ["  (none)"])

    catalog = "\n".join(
        f"- type={c.type} id={c.id} title={c.title!r}"
        + (f" snippet={c.snippet!r}" if c.snippet else "")
        for c in allowed
    )
    prompt = (
        "Allowed citations (use these ids; do not invent):\n"
        f"{catalog}\n\n"
        + "\n".join(parts)
    )
    return prompt, allowed


def _format_history(history: list[AskTurn]) -> str:
    recent = history[-_HISTORY_LIMIT:]
    if not recent:
        return "(none)"
    return "\n".join(f"{turn.role}: {turn.text}" for turn in recent)


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def filter_citations(
    emitted: list[AskLlmCitation],
    *,
    allowed: list[AskCitation],
    board_item_id: int,
) -> list[AskCitation]:
    """Drop fabricated decision ids and anything not in the assembled catalog."""
    allowed_source_ids = {c.id for c in allowed if c.type == "source"}
    kept: list[AskCitation] = []
    seen: set[tuple[str, str]] = set()
    for raw in emitted:
        if raw.type == "decision":
            continue
        if raw.type == "item":
            if _digits(raw.id) != str(board_item_id):
                continue
            cit = AskCitation(
                id=raw.id or f"item-{board_item_id}",
                type="item",
                title=raw.title,
                snippet=raw.snippet or None,
            )
        elif raw.type == "source" and raw.id in allowed_source_ids:
            cit = AskCitation(
                id=raw.id,
                type="source",
                title=raw.title,
                snippet=raw.snippet or None,
            )
        else:
            continue
        key = (cit.type, cit.id)
        if key in seen:
            continue
        seen.add(key)
        kept.append(cit)
    return kept


async def ask_about_item(db: AsyncSession, *, project_id: str, body: AskRequest) -> AskResponse:
    task = await load_published_task(
        db, project_id=project_id, board_item_id=body.board_item_id
    )
    context, allowed = assemble_ask_context(
        board_item_id=body.board_item_id, item=body.item, task=task
    )
    history_text = _format_history(list(body.history or []))
    model = get_chat_model().with_structured_output(AskResult)
    result = await model.ainvoke(
        [
            SystemMessage(content=ASK),
            HumanMessage(
                content=(
                    f"Query: {body.query.strip()}\n\n{context}\n\n"
                    f"Recent conversation:\n{history_text}"
                )
            ),
        ]
    )
    if isinstance(result, AskResult):
        parsed = result
    elif isinstance(result, dict):
        parsed = AskResult.model_validate(result)
    else:
        parsed = AskResult(answer="", citations=[])
    return AskResponse(
        answer=parsed.answer,
        citations=filter_citations(
            parsed.citations, allowed=allowed, board_item_id=body.board_item_id
        ),
    )
