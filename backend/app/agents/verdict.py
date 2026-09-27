"""Task-vs-task verdict — duplicate / conflict / impact / net-new (plans/manual-add-verdict.md).

Uses `get_chat_model()` only. Never imports the Vertex/Gemini SDK.
Does not persist (board verdicts stay on Node/SQLite; chat_messages is the workflow thread).
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.llm import get_chat_model
from app.agents.prompts import VERDICT
from app.models import Task
from app.schemas.mvp import (
    VerdictBoardItem,
    VerdictCandidate,
    VerdictCheckItem,
    VerdictCheckRequest,
    VerdictCitation,
    VerdictDetail,
    VerdictResult,
)

_DRAFT_STATUSES = ("draft", "approved")
_NET_NEW = VerdictDetail(
    type="net-new",
    confidence=100,
    message="Net-new — nothing like this yet",
    candidates=[],
)


def item_id(value: str) -> str:
    return str(value)


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


async def load_unpublished_tasks(db: AsyncSession, *, project_id: str) -> list[Task]:
    """Generated tasks not yet on the board. `on_board` is excluded."""
    stmt = (
        select(Task)
        .where(Task.project_id == project_id, Task.status.in_(_DRAFT_STATUSES))
        .options(selectinload(Task.feature))
        .order_by(Task.ordinal, Task.id)
    )
    return list((await db.execute(stmt)).scalars().all())


def assemble_verdict_context(
    *,
    item: VerdictCheckItem,
    board_items: list[VerdictBoardItem],
    drafts: list[Task],
) -> tuple[str, dict[str, tuple[str, str]]]:
    """Build the prompt block and the candidate ids the model may emit.

    Allowed map: canonical id → (kind, title). kind is ``board`` or ``draft``.
    """
    subject_id = item_id(item.id)
    others = [b for b in board_items if item_id(b.id) != subject_id]
    allowed: dict[str, tuple[str, str]] = {}

    parts: list[str] = [
        "## New card",
        f"- id: {subject_id}",
        f"- title: {item.title}",
        f"- description: {item.description or '(none)'}",
        f"- area: {item.area or '(none)'}",
        "",
        "## Other board cards",
    ]
    if not others:
        parts.append("(none)")
    for card in others:
        cid = item_id(card.id)
        allowed[cid] = ("board", card.title)
        parts.append(
            f"- id: {cid} title: {card.title!r} area: {card.area or '(none)'} "
            f"status: {card.status or '(none)'} description: {card.description or '(none)'}"
        )

    parts.extend(["", "## Unpublished generated tasks (draft or approved — not on the board)"])
    if not drafts:
        parts.append("(none)")
    for task in drafts:
        tid = str(task.id)
        allowed[tid] = ("draft", task.title)
        feature = task.feature
        fname = feature.name if feature is not None else ""
        fsum = feature.summary if feature is not None else ""
        parts.append(
            f"- id: {tid} status: {task.status} title: {task.title!r} "
            f"area: {task.area or '(none)'} description: {task.description or '(none)'}"
        )
        parts.append(f"  feature: {fname} — {fsum}")
        parts.append(f"  acceptance_criteria: {task.acceptance_criteria or []}")
        parts.append(f"  traces_to: {list(task.traces_to or [])}")

    catalog = "\n".join(
        f"- type=item id={cid} kind={kind} title={title!r}"
        for cid, (kind, title) in allowed.items()
    ) or "(none)"
    prompt = (
        "Allowed candidates (use these ids; do not invent):\n"
        f"{catalog}\n\n"
        + "\n".join(parts)
    )
    return prompt, allowed


def _canonical_id(raw_id: str, allowed: dict[str, tuple[str, str]]) -> str | None:
    if raw_id in allowed:
        return raw_id
    stripped = raw_id.lstrip("#")
    if stripped in allowed:
        return stripped
    digits = _digits(raw_id)
    if digits and digits in allowed:
        return digits
    return None


def filter_verdict(
    parsed: VerdictResult,
    *,
    allowed: dict[str, tuple[str, str]],
) -> VerdictDetail:
    """Drop fabricated decision ids and anything not in the assembled catalog.

    Cite or stay silent: a flag with no remaining cited candidate becomes net-new.
    Confidence below 70 is kept — never dropped.
    """
    kept: list[VerdictCandidate] = []
    seen: set[str] = set()
    for raw in parsed.candidates:
        if raw.type == "decision":
            continue
        cid = _canonical_id(raw.id, allowed)
        if cid is None or cid in seen:
            continue
        seen.add(cid)
        kept.append(
            VerdictCandidate(
                id=cid,
                type="item",
                title=raw.title or allowed[cid][1],
                reason=raw.reason,
                confidence=int(raw.confidence),
            )
        )
        if len(kept) == 3:
            break

    citation: VerdictCitation | None = None
    if parsed.citation is not None and parsed.citation.type != "decision":
        cid = _canonical_id(parsed.citation.id, allowed)
        if cid is not None:
            citation = VerdictCitation(
                id=cid,
                type="item" if parsed.citation.type == "source" else parsed.citation.type,
                title=parsed.citation.title or allowed[cid][1],
                snippet=parsed.citation.snippet,
            )

    vtype = parsed.type
    if vtype == "net-new" or not kept:
        return VerdictDetail(
            type="net-new",
            confidence=int(parsed.confidence) if vtype == "net-new" else 100,
            message=parsed.message or _NET_NEW.message,
            candidates=[],
            citation=None,
        )
    return VerdictDetail(
        type=vtype,
        confidence=int(parsed.confidence),
        message=parsed.message,
        candidates=kept,
        citation=citation,
    )


def _parse_result(result: object) -> VerdictResult:
    if isinstance(result, VerdictResult):
        return result
    if isinstance(result, dict):
        return VerdictResult.model_validate(result)
    return VerdictResult(type="net-new", confidence=100, message=_NET_NEW.message)


async def check_verdict(
    db: AsyncSession, *, project_id: str, body: VerdictCheckRequest
) -> VerdictDetail:
    drafts = await load_unpublished_tasks(db, project_id=project_id)
    context, allowed = assemble_verdict_context(
        item=body.item, board_items=list(body.board_items or []), drafts=drafts
    )
    if not allowed:
        return _NET_NEW.model_copy()

    model = get_chat_model().with_structured_output(VerdictResult)
    result = await model.ainvoke(
        [
            SystemMessage(content=VERDICT),
            HumanMessage(content=context),
        ]
    )
    return filter_verdict(_parse_result(result), allowed=allowed)
