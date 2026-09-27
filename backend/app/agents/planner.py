"""Task Planner + Task Reviewer — structured-output agents."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import get_chat_model
from app.agents.prompts import PLANNER, REVIEWER
from app.schemas.mvp import PlannedTask, PlannedTasks, ReviewVerdict


def _feature_brief(name: str, summary: str, details: dict, pm_answers: list[str]) -> str:
    answers = "\n".join(f"- {a}" for a in pm_answers) or "(none)"
    return (
        f"Feature: {name}\nSummary: {summary}\n"
        f"Details: {details}\nPM answers:\n{answers}"
    )


def draft_listing(tasks: list[PlannedTask]) -> str:
    """Full contract listing so the reviewer can fail thin drafts."""
    return "\n\n".join(
        (
            f"[{i}] {t.title}\n{t.description}\n"
            f"subtasks: {list(t.subtasks or [])}\n"
            f"traces_to: {list(t.traces_to or [])}\n"
            f"AC: {t.acceptance_criteria}\n"
            f"definition_of_done: {list(t.definition_of_done or [])}"
        )
        for i, t in enumerate(tasks)
    )


async def plan_tasks(
    *,
    name: str,
    summary: str,
    details: dict,
    pm_answers: list[str],
    issues: list[str] | None = None,
) -> list[PlannedTask]:
    model = get_chat_model().with_structured_output(PlannedTasks)
    extra = ""
    if issues:
        extra = "\n\nThe reviewer rejected the previous draft. Fix these issues:\n" + "\n".join(
            f"- {i}" for i in issues
        )
    result = await model.ainvoke(
        [
            SystemMessage(content=PLANNER),
            HumanMessage(content=_feature_brief(name, summary, details, pm_answers) + extra),
        ]
    )
    if isinstance(result, PlannedTasks):
        tasks = result.tasks
    elif isinstance(result, dict):
        tasks = PlannedTasks.model_validate(result).tasks
    else:
        tasks = []
    return tasks[:10]


async def review_tasks(
    *,
    name: str,
    summary: str,
    details: dict,
    pm_answers: list[str],
    tasks: list[PlannedTask],
) -> ReviewVerdict:
    model = get_chat_model().with_structured_output(ReviewVerdict)
    listing = draft_listing(tasks)
    result = await model.ainvoke(
        [
            SystemMessage(content=REVIEWER),
            HumanMessage(
                content=(
                    _feature_brief(name, summary, details, pm_answers)
                    + f"\n\nDraft tasks:\n{listing}"
                )
            ),
        ]
    )
    if isinstance(result, ReviewVerdict):
        return result
    if isinstance(result, dict):
        return ReviewVerdict.model_validate(result)
    return ReviewVerdict(passed=True, issues=[])
