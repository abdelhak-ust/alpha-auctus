"""task_graph: Task Planner → Task Reviewer (retry once) → persist_drafts."""

from __future__ import annotations

import logging
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agents.graphs._persist import audit, persist_task_drafts
from app.agents.planner import plan_tasks, review_tasks
from app.db.session import get_session_factory
from app.models import Feature
from app.schemas.mvp import PlannedTask

logger = logging.getLogger(__name__)

_compiled = None


class TaskState(TypedDict, total=False):
    feature_id: str
    project_id: str
    name: str
    summary: str
    details: dict[str, Any]
    pm_answers: list[str]
    drafts: list[dict[str, Any]]
    issues: list[str]
    attempt: int
    review_notes: str
    passed: bool


async def planner_node(state: TaskState) -> dict[str, Any]:
    issues = state.get("issues") or []
    drafts = await plan_tasks(
        name=state["name"],
        summary=state["summary"],
        details=state.get("details") or {},
        pm_answers=state.get("pm_answers") or [],
        issues=issues or None,
    )
    async with get_session_factory()() as db:
        await audit(
            db,
            project_id=state["project_id"],
            feature_id=state["feature_id"],
            graph="tasks",
            node="planner",
            agent="Task Planner",
            detail=f"Drafted {len(drafts)} task(s) (attempt {(state.get('attempt') or 0) + 1}).",
        )
    return {
        "drafts": [t.model_dump() for t in drafts],
        "attempt": (state.get("attempt") or 0) + 1,
    }


async def reviewer_node(state: TaskState) -> dict[str, Any]:
    drafts = [PlannedTask.model_validate(d) for d in (state.get("drafts") or [])]
    verdict = await review_tasks(
        name=state["name"],
        summary=state["summary"],
        details=state.get("details") or {},
        pm_answers=state.get("pm_answers") or [],
        tasks=drafts,
    )
    notes = ""
    if not verdict.passed and verdict.issues:
        notes = "; ".join(f"#{i.task_index}: {i.problem}" for i in verdict.issues)
    async with get_session_factory()() as db:
        await audit(
            db,
            project_id=state["project_id"],
            feature_id=state["feature_id"],
            graph="tasks",
            node="reviewer",
            agent="Task Reviewer",
            detail="Passed." if verdict.passed else f"Issues: {notes}",
        )
    return {
        "passed": verdict.passed,
        "issues": [f"#{i.task_index}: {i.problem}" for i in verdict.issues],
        "review_notes": notes or None,
    }


def route_after_review(state: TaskState) -> str:
    if state.get("passed") or (state.get("attempt") or 0) >= 2:
        return "persist_drafts"
    return "planner"


async def persist_drafts_node(state: TaskState) -> dict[str, Any]:
    drafts = [PlannedTask.model_validate(d) for d in (state.get("drafts") or [])]
    notes = None if state.get("passed") else (state.get("review_notes") or None)
    async with get_session_factory()() as db:
        feature = (
            await db.execute(
                select(Feature)
                .options(selectinload(Feature.tasks))
                .where(Feature.id == uuid.UUID(state["feature_id"]))
            )
        ).scalar_one()
        await persist_task_drafts(db, feature=feature, drafts=drafts, review_notes=notes)
        await audit(
            db,
            project_id=state["project_id"],
            feature_id=feature.id,
            graph="tasks",
            node="persist_drafts",
            agent="persist_drafts",
            detail=f"Saved {len(drafts)} draft task(s); on_board rows kept.",
        )
    return {}


def build_task_graph():
    builder = StateGraph(TaskState)
    builder.add_node("planner", planner_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("persist_drafts", persist_drafts_node)
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "reviewer")
    builder.add_conditional_edges("reviewer", route_after_review)
    builder.add_edge("persist_drafts", END)
    return builder


async def get_task_graph():
    global _compiled
    if _compiled is None:
        from app.graph.checkpointer import get_checkpointer

        saver = await get_checkpointer()
        _compiled = build_task_graph().compile(checkpointer=saver)
    return _compiled


def reset_task_graph() -> None:
    global _compiled
    _compiled = None


async def run_task_graph(feature_id: str) -> None:
    async with get_session_factory()() as db:
        feature = (
            await db.execute(
                select(Feature)
                .options(selectinload(Feature.questions))
                .where(Feature.id == uuid.UUID(feature_id))
            )
        ).scalar_one_or_none()
        if feature is None:
            return
        feature.status = "planning"
        await db.commit()
        pm_answers = [q.answer for q in feature.questions if q.status == "answered" and q.answer]
        payload = {
            "feature_id": str(feature.id),
            "project_id": feature.project_id,
            "name": feature.name,
            "summary": feature.summary,
            "details": dict(feature.details or {}),
            "pm_answers": pm_answers,
            "attempt": 0,
            "drafts": [],
            "issues": [],
        }
    try:
        graph = await get_task_graph()
        await graph.ainvoke(payload, {"configurable": {"thread_id": f"tasks:{feature_id}"}})
    except Exception:
        logger.exception("task_graph failed for %s", feature_id)
        async with get_session_factory()() as db:
            feature = await db.get(Feature, uuid.UUID(feature_id))
            if feature is not None and feature.status == "planning":
                feature.status = "clarified"
                await db.commit()
            await audit(
                db,
                project_id=payload["project_id"],
                feature_id=feature_id,
                graph="tasks",
                node="run",
                agent="task_graph",
                detail="Task generation failed — feature left in its previous status.",
            )
