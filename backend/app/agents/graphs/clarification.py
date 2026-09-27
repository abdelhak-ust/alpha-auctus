"""clarification_graph: next_question → interrupt() → Clarifier → loop.

Thread id `clarify:{project_id}`. The Clarifier runs in-request on resume.
Questions are never auto-answered.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.agents.clarifier import clarify
from app.agents.graphs._persist import apply_field_update, audit
from app.db.session import get_session_factory
from app.models import ChatMessage, Feature, FeatureQuestion

_compiled = None


class ClarifyState(TypedDict, total=False):
    project_id: str
    question_id: str
    feature_id: str
    feature_name: str
    question: str
    why: str
    target_field: str
    resume: dict[str, Any]
    changes: list[str]
    remaining: int
    done: bool


async def _next_open(project_id: str) -> FeatureQuestion | None:
    async with get_session_factory()() as db:
        stmt = (
            select(FeatureQuestion)
            .join(Feature, Feature.id == FeatureQuestion.feature_id)
            .where(
                FeatureQuestion.project_id == project_id,
                FeatureQuestion.status == "open",
            )
            .order_by(Feature.position, FeatureQuestion.ordinal, FeatureQuestion.id)
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()


async def _remaining(project_id: str) -> int:
    async with get_session_factory()() as db:
        n = await db.scalar(
            select(func.count())
            .select_from(FeatureQuestion)
            .where(FeatureQuestion.project_id == project_id, FeatureQuestion.status == "open")
        )
        return int(n or 0)


async def _add_chat(
    project_id: str,
    role: str,
    text: str,
    *,
    question_id: uuid.UUID | None = None,
    feature_id: uuid.UUID | None = None,
    kind: str | None = "question",
) -> None:
    async with get_session_factory()() as db:
        db.add(
            ChatMessage(
                project_id=project_id,
                role=role,
                text=text,
                question_id=question_id,
                feature_id=feature_id,
                kind=kind,
            )
        )
        await db.commit()


async def next_question_node(state: ClarifyState) -> dict[str, Any]:
    project_id = state["project_id"]
    q = await _next_open(project_id)
    remaining = await _remaining(project_id)
    if q is None:
        return {"done": True, "remaining": 0, "question_id": "", "changes": []}
    async with get_session_factory()() as db:
        feature = await db.get(Feature, q.feature_id)
        name = feature.name if feature else ""
        await audit(
            db,
            project_id=project_id,
            feature_id=q.feature_id,
            graph="clarification",
            node="next_question",
            agent="next_question",
            detail=f"Asking “{q.question}” about {name}.",
        )
    text = f"[{name}] {q.question}"
    if q.why:
        text += f"\nWhy this matters: {q.why}"
    await _add_chat(project_id, "ai", text, question_id=q.id, feature_id=q.feature_id)
    return {
        "done": False,
        "remaining": remaining,
        "question_id": str(q.id),
        "feature_id": str(q.feature_id),
        "feature_name": name,
        "question": q.question,
        "why": q.why,
        "target_field": q.target_field,
        "changes": [],
        "resume": {},
    }


def wait_for_pm_node(state: ClarifyState) -> dict[str, Any]:
    """Pause for the PM. Never auto-answers."""
    if state.get("done"):
        return {}
    payload = interrupt(
        {
            "questionId": state["question_id"],
            "featureId": state["feature_id"],
            "featureName": state.get("feature_name") or "",
            "question": state["question"],
            "why": state.get("why") or "",
        }
    )
    return {"resume": payload if isinstance(payload, dict) else {"answer": str(payload)}}


async def clarifier_node(state: ClarifyState) -> dict[str, Any]:
    resume = state.get("resume") or {}
    project_id = state["project_id"]
    qid = uuid.UUID(state["question_id"])
    skip = bool(resume.get("skip"))
    answer = str(resume.get("answer") or "").strip()

    async with get_session_factory()() as db:
        q = await db.get(FeatureQuestion, qid)
        if q is None:
            return {"changes": [], "done": False}
        feature = (
            await db.execute(
                select(Feature)
                .options(selectinload(Feature.questions))
                .where(Feature.id == q.feature_id)
            )
        ).scalar_one()

        changes = []
        if skip:
            q.status = "skipped"
            q.answered_at = datetime.now(UTC)
            await db.flush()
            await _maybe_clarify_feature(db, feature)
            await audit(
                db,
                project_id=project_id,
                feature_id=feature.id,
                graph="clarification",
                node="clarifier",
                agent="Clarifier",
                detail=f"Skipped question on “{feature.name}”.",
            )
            await db.commit()
            changes = ["Skipped"]
        else:
            follow_ups_so_far = sum(1 for x in feature.questions if x.is_follow_up)
            scratch = await clarify(
                feature_name=feature.name,
                feature_summary=feature.summary,
                details=dict(feature.details or {}),
                question=q.question,
                why=q.why,
                target_field=q.target_field,
                answer=answer,
                existing_follow_ups=follow_ups_so_far,
            )
            q.status = "answered"
            q.answer = answer
            q.answered_at = datetime.now(UTC)
            details = dict(feature.details or {})
            quotes = list(feature.source_quotes or [])
            changes: list[str] = []
            for upd in scratch.updates:
                details = apply_field_update(details, upd["field"], upd["value"])
                quotes.append({"quote": upd["value"], "verified": True, "origin": "pm"})
                changes.append(f"Updated {feature.name} → {upd['field']}")
            feature.details = details
            feature.source_quotes = quotes
            next_ord = max((x.ordinal for x in feature.questions), default=-1) + 1
            for i, fu in enumerate(scratch.follow_ups):
                db.add(
                    FeatureQuestion(
                        project_id=project_id,
                        feature_id=feature.id,
                        question=fu["question"],
                        why=fu.get("why") or "",
                        target_field=fu.get("target_field") or q.target_field,
                        is_follow_up=True,
                        status="open",
                        ordinal=next_ord + i,
                    )
                )
                changes.append(f"Follow-up on {feature.name}")
            if not scratch.follow_ups:
                await _maybe_clarify_feature(db, feature)
            await audit(
                db,
                project_id=project_id,
                feature_id=feature.id,
                graph="clarification",
                node="clarifier",
                agent="Clarifier",
                detail="; ".join(changes) or f"Recorded answer on “{feature.name}”.",
            )
            await db.commit()

    await _add_chat(
        project_id,
        "pm",
        "(skipped)" if skip else answer,
        question_id=qid,
        feature_id=uuid.UUID(state["feature_id"]),
    )
    remaining = await _remaining(project_id)
    return {"changes": changes, "remaining": remaining, "done": False}


async def _maybe_clarify_feature(db, feature: Feature) -> None:
    open_left = [x for x in feature.questions if x.status == "open"]
    # newly added follow-ups are in the session but may not be in feature.questions yet
    if not open_left and feature.status in {"needs_clarification", "analysed"}:
        feature.status = "clarified"


def route_after_next(state: ClarifyState) -> str:
    return END if state.get("done") else "wait_for_pm"


def route_after_clarifier(state: ClarifyState) -> str:
    return "next_question"


def build_clarification_graph():
    builder = StateGraph(ClarifyState)
    builder.add_node("next_question", next_question_node)
    builder.add_node("wait_for_pm", wait_for_pm_node)
    builder.add_node("clarifier", clarifier_node)
    builder.add_edge(START, "next_question")
    builder.add_conditional_edges("next_question", route_after_next)
    builder.add_edge("wait_for_pm", "clarifier")
    builder.add_conditional_edges("clarifier", route_after_clarifier)
    return builder


async def get_clarification_graph():
    global _compiled
    if _compiled is None:
        from app.graph.checkpointer import get_checkpointer

        saver = await get_checkpointer()
        _compiled = build_clarification_graph().compile(checkpointer=saver)
    return _compiled


def reset_clarification_graph() -> None:
    global _compiled
    _compiled = None


def _thread(project_id: str) -> dict:
    return {"configurable": {"thread_id": f"clarify:{project_id}"}}


async def run_clarification_start(project_id: str) -> Any:
    """Start or read the project thread; pauses at interrupt() with the current question."""
    graph = await get_clarification_graph()
    config = _thread(project_id)
    state = await graph.aget_state(config)
    if state.values and state.next:
        return state
    await graph.ainvoke({"project_id": project_id}, config)
    return await graph.aget_state(config)


async def run_clarification_resume(project_id: str, payload: dict[str, Any]) -> Any:
    """Resume with the PM's answer or skip. Clarifier runs in this call."""
    graph = await get_clarification_graph()
    config = _thread(project_id)
    state = await graph.aget_state(config)
    if not state.next:
        await graph.ainvoke({"project_id": project_id}, config)
    await graph.ainvoke(Command(resume=payload), config)
    return await graph.aget_state(config)


async def peek_clarification_state(project_id: str) -> Any | None:
    """Read a running clarify thread without starting one."""
    graph = await get_clarification_graph()
    state = await graph.aget_state(_thread(project_id))
    if state.values and state.next:
        return state
    return None


async def skip_open_questions_in_db(project_id: str, feature_id: uuid.UUID) -> int:
    """Mark every still-open question on this feature skipped. Never writes an answer."""
    async with get_session_factory()() as db:
        feature = (
            await db.execute(
                select(Feature)
                .options(selectinload(Feature.questions))
                .where(Feature.id == feature_id, Feature.project_id == project_id)
            )
        ).scalar_one_or_none()
        if feature is None:
            return 0
        now = datetime.now(UTC)
        skipped = 0
        for q in feature.questions:
            if q.status != "open":
                continue
            q.status = "skipped"
            q.answer = None
            q.answered_at = now
            db.add(
                ChatMessage(
                    project_id=project_id,
                    role="pm",
                    text="(skipped)",
                    question_id=q.id,
                    feature_id=feature.id,
                    kind="question",
                )
            )
            skipped += 1
        if skipped:
            await _maybe_clarify_feature(db, feature)
            await audit(
                db,
                project_id=project_id,
                feature_id=feature.id,
                graph="clarification",
                node="skip_remaining",
                agent="Clarifier",
                detail=f"Skipped {skipped} remaining question(s) on “{feature.name}”.",
            )
        await db.commit()
        return skipped
