"""Planner / Reviewer retry loop; regenerating keeps on_board tasks."""

from langgraph.checkpoint.memory import MemorySaver

from app.agents.graphs._persist import persist_task_drafts
from app.agents.graphs.tasks import build_task_graph, route_after_review
from app.agents.llm import set_chat_model_override
from app.agents.planner import draft_listing
from app.schemas.mvp import CitedAC, PlannedTask, PlannedTasks, ReviewIssue, ReviewVerdict
from tests.fakes import FakeChatModel

_RICH_DESCRIPTION = (
    "This task implements the Email sign-in feature's 'Accept work email' requirement. "
    "Build the sign-in form and server check that only work-domain emails can authenticate. "
    "It does not include password reset, SSO, or session expiry policy."
)


def _task(title: str = "Implement sign-in") -> PlannedTask:
    return PlannedTask(
        title=title,
        description=_RICH_DESCRIPTION,
        area="auth",
        priority="P1",
        acceptance_criteria=[
            CitedAC(
                given="a visitor with a work email",
                when="they submit the sign-in form",
                then="they are authenticated",
            ),
            CitedAC(
                given="a visitor with a personal email",
                when="they submit the sign-in form",
                then="sign-in is rejected",
            ),
        ],
        estimate="M",
        traces_to=["Accept work email"],
        subtasks=[
            "Add the email sign-in form on the login page",
            "Validate work-domain emails on the server",
            "Reject personal domains with a cited error",
        ],
        definition_of_done=[
            "Tests cover accepted work email and rejected personal email",
            "Cited acceptance criteria are met",
            "No invented scope beyond the feature or PM answers",
        ],
    )


def _thin_task(title: str = "Implement sign-in") -> PlannedTask:
    """Missing subtasks, DoD, and a detailed description — reviewer must fail."""
    return PlannedTask(
        title=title,
        description="Build it.",
        area="auth",
        priority="P1",
        acceptance_criteria=[CitedAC(given="a user", when="they sign in", then="they are in")],
        estimate="M",
        traces_to=["Accept work email"],
        subtasks=[],
        definition_of_done=[],
    )


def test_reviewer_retries_planner_once_then_persists():
    assert route_after_review({"passed": False, "attempt": 1}) == "planner"
    assert route_after_review({"passed": False, "attempt": 2}) == "persist_drafts"
    assert route_after_review({"passed": True, "attempt": 1}) == "persist_drafts"


def test_draft_listing_exposes_subtasks_and_dod():
    listing = draft_listing([_thin_task(), _task()])
    assert "subtasks: []" in listing
    assert "definition_of_done: []" in listing
    assert "Add the email sign-in form on the login page" in listing
    assert "Cited acceptance criteria are met" in listing
    assert "traces_to: ['Accept work email']" in listing


async def test_task_graph_retries_then_saves(make_feature, db_session):
    feature = await make_feature(status="clarified")
    drafts = PlannedTasks(tasks=[_task()])
    fake = FakeChatModel(
        script=[
            drafts,
            ReviewVerdict(passed=False, issues=[ReviewIssue(task_index=0, problem="weak AC")]),
            drafts,
            ReviewVerdict(passed=True, issues=[]),
        ]
    )
    set_chat_model_override(fake)
    graph = build_task_graph().compile(checkpointer=MemorySaver())
    try:
        await graph.ainvoke(
            {
                "feature_id": str(feature.id),
                "project_id": feature.project_id,
                "name": feature.name,
                "summary": feature.summary,
                "details": feature.details or {},
                "pm_answers": [],
                "attempt": 0,
                "drafts": [],
                "issues": [],
            },
            {"configurable": {"thread_id": f"tasks:{feature.id}"}},
        )
    finally:
        set_chat_model_override(None)
    await db_session.refresh(feature)
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import Feature

    feat = (
        await db_session.execute(
            select(Feature).options(selectinload(Feature.tasks)).where(Feature.id == feature.id)
        )
    ).scalar_one()
    assert feat.status == "tasks_ready"
    assert len(feat.tasks) >= 1
    saved = feat.tasks[0]
    assert len(saved.subtasks) >= 3
    assert len(saved.definition_of_done) >= 3
    assert len(saved.acceptance_criteria) >= 2
    assert saved.traces_to


async def test_reviewer_fails_empty_subtasks_and_dod(make_feature, db_session):
    feature = await make_feature(status="clarified")
    thin = PlannedTasks(tasks=[_thin_task()])
    rich = PlannedTasks(tasks=[_task("Email sign-in form")])
    fake = FakeChatModel(
        script=[
            thin,
            ReviewVerdict(
                passed=False,
                issues=[
                    ReviewIssue(
                        task_index=0,
                        problem="empty subtasks and definition_of_done; description is trivial",
                    )
                ],
            ),
            rich,
            ReviewVerdict(passed=True, issues=[]),
        ]
    )
    set_chat_model_override(fake)
    graph = build_task_graph().compile(checkpointer=MemorySaver())
    try:
        await graph.ainvoke(
            {
                "feature_id": str(feature.id),
                "project_id": feature.project_id,
                "name": feature.name,
                "summary": feature.summary,
                "details": feature.details or {},
                "pm_answers": [],
                "attempt": 0,
                "drafts": [],
                "issues": [],
            },
            {"configurable": {"thread_id": f"tasks-thin:{feature.id}"}},
        )
    finally:
        set_chat_model_override(None)

    from sqlalchemy import select

    from app.models import Task

    await db_session.refresh(feature)
    tasks = (
        await db_session.execute(select(Task).where(Task.feature_id == feature.id))
    ).scalars().all()
    assert feature.status == "tasks_ready"
    saved = next(t for t in tasks if t.title == "Email sign-in form")
    assert saved.subtasks == [
        "Add the email sign-in form on the login page",
        "Validate work-domain emails on the server",
        "Reject personal domains with a cited error",
    ]
    assert len(saved.definition_of_done) >= 3
    assert "Build it." not in saved.description


async def test_regen_keeps_on_board_tasks(make_feature, make_task, db_session):
    feature = await make_feature(status="tasks_ready")
    kept = await make_task(feature, status="on_board", title="Already on board", board_item_id=99)
    await make_task(feature, status="draft", title="Old draft", ordinal=1)
    await persist_task_drafts(
        db_session,
        feature=feature,
        drafts=[_task("New draft")],
        review_notes=None,
    )
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import Feature, Task

    feat = (
        await db_session.execute(
            select(Feature).options(selectinload(Feature.tasks)).where(Feature.id == feature.id)
        )
    ).scalar_one()
    titles = {t.title: t.status for t in feat.tasks}
    assert titles.get("Already on board") == "on_board"
    assert "Old draft" not in titles
    assert any(t.status == "draft" for t in feat.tasks)
    still = await db_session.get(Task, kept.id)
    assert still is not None and still.board_item_id == 99
    new = next(t for t in feat.tasks if t.title == "New draft")
    assert len(new.subtasks) >= 3
    assert len(new.definition_of_done) >= 3
