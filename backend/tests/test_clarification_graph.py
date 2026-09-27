"""Clarification graph: interrupt / resume, PM-cited writes, follow-up cap."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.agents.graphs.clarification import build_clarification_graph
from app.agents.llm import set_chat_model_override
from app.agents.tools import ClarifierScratch, bind_clarifier_tools
from app.config import get_settings
from tests.fakes import FakeChatModel


def test_follow_up_tool_is_capped():
    scratch = ClarifierScratch(follow_up_count=0, max_follow_ups=2)
    _update, ask, _done = bind_clarifier_tools(scratch)
    ask.invoke({"question": "First?", "why": "a"})
    ask.invoke({"question": "Second?", "why": "b"})
    third = ask.invoke({"question": "Third?", "why": "c"})
    assert scratch.follow_up_count == 2
    assert len(scratch.follow_ups) == 2
    assert "cap" in third.lower()
    assert get_settings().max_follow_ups_per_feature == 2


def test_update_field_records_pm_write():
    scratch = ClarifierScratch()
    update, _ask, resolve = bind_clarifier_tools(scratch)
    update.invoke({"field": "user_roles", "value": "admins only"})
    resolve.invoke({})
    assert scratch.updates == [{"field": "user_roles", "value": "admins only"}]
    assert scratch.resolved is True


async def test_graph_pauses_at_interrupt_and_resumes(make_feature, db_session):
    feature = await make_feature(
        questions=[
            {"question": "Who is the primary user?", "why": "roles", "target_field": "user_roles"}
        ]
    )
    fake = FakeChatModel(script=[{}])
    set_chat_model_override(fake)
    graph = build_clarification_graph().compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": f"clarify:{feature.project_id}"}}
    try:
        await graph.ainvoke({"project_id": feature.project_id}, config)
        state = await graph.aget_state(config)
        assert state.next == ("wait_for_pm",) or "wait_for_pm" in (state.next or ())
        interrupts = []
        for task in state.tasks:
            interrupts.extend(getattr(task, "interrupts", ()) or ())
        assert interrupts, "expected interrupt() to pause for the PM"

        await graph.ainvoke(Command(resume={"answer": "The admin"}), config)
        await db_session.refresh(feature)
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.models import Feature

        feat = (
            await db_session.execute(
                select(Feature)
                .options(selectinload(Feature.questions))
                .where(Feature.id == feature.id)
            )
        ).scalar_one()
        q = feat.questions[0]
        assert q.status in {"answered", "open"}
        if q.status == "answered":
            assert q.answer == "The admin"
            assert any(sq.get("origin") == "pm" for sq in (feat.source_quotes or []))
    finally:
        set_chat_model_override(None)


async def test_graph_resumes_on_skip(make_feature):
    feature = await make_feature(
        questions=[{"question": "Skip me?", "why": "n/a", "target_field": "description"}]
    )
    set_chat_model_override(FakeChatModel())
    graph = build_clarification_graph().compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": f"clarify-skip:{feature.project_id}"}}
    try:
        await graph.ainvoke({"project_id": feature.project_id}, config)
        await graph.ainvoke(Command(resume={"skip": True}), config)
        from sqlalchemy import select

        from app.db.session import get_session_factory
        from app.models import FeatureQuestion

        async with get_session_factory()() as db:
            q = (
                await db.execute(
                    select(FeatureQuestion).where(FeatureQuestion.feature_id == feature.id)
                )
            ).scalar_one()
            assert q.status == "skipped"
    finally:
        set_chat_model_override(None)
