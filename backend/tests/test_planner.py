"""Planner listing + reviewer path for thin vs rich task contracts."""

from app.agents.llm import set_chat_model_override
from app.agents.planner import draft_listing, review_tasks
from app.agents.prompts import PLANNER, REVIEWER
from app.schemas.mvp import CitedAC, PlannedTask, ReviewIssue, ReviewVerdict
from tests.fakes import FakeChatModel


def _thin() -> PlannedTask:
    return PlannedTask(
        title="Do the thing",
        description="Build it.",
        traces_to=["Accept work email"],
        acceptance_criteria=[CitedAC(given="a user", when="they act", then="it works")],
        subtasks=[],
        definition_of_done=[],
    )


def test_prompts_require_rich_contracts():
    assert "subtasks" in PLANNER
    assert "definition_of_done" in PLANNER
    assert "Several sentences" in PLANNER
    assert "at least 3 concrete subtasks" in REVIEWER
    assert "at least 2 Given/When/Then" in REVIEWER
    assert "at least 3 definition_of_done" in REVIEWER
    assert "non-empty traces_to" in REVIEWER


def test_draft_listing_shows_empty_subtasks_and_dod():
    listing = draft_listing([_thin()])
    assert "[0] Do the thing" in listing
    assert "Build it." in listing
    assert "subtasks: []" in listing
    assert "definition_of_done: []" in listing
    assert "traces_to: ['Accept work email']" in listing


async def test_review_tasks_can_fail_thin_draft():
    fake = FakeChatModel(
        script=[
            ReviewVerdict(
                passed=False,
                issues=[ReviewIssue(task_index=0, problem="empty subtasks and definition_of_done")],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        verdict = await review_tasks(
            name="Email sign-in",
            summary="Users can sign in with their work email.",
            details={"functional_requirements": [{"text": "Accept work email"}]},
            pm_answers=[],
            tasks=[_thin()],
        )
    finally:
        set_chat_model_override(None)
    assert verdict.passed is False
    assert verdict.issues
    assert "subtasks" in verdict.issues[0].problem
