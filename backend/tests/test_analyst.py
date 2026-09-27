"""Analyst tools + question cap."""

from app.agents.analyst import analyse_feature
from app.agents.llm import set_chat_model_override
from app.agents.tools import bind_document_tools, list_document_sections
from app.config import get_settings
from app.schemas.mvp import AnalystQuestion, FeatureDetails
from tests.fakes import FakeChatModel

MD = """# Overview

Users can sign in with their work email.

## Session timeout

Sessions expire after 30 minutes of inactivity.

## Audit log

Admins can export the audit log as CSV.
"""


def test_search_and_read_section_tools():
    search, read, listing = bind_document_tools(MD)
    hits = search.invoke({"query": "session timeout"})
    assert "30 minutes" in hits
    assert "[" in hits
    section = read.invoke({"heading": "Session timeout"})
    assert "Sessions expire after 30 minutes" in section
    outline = listing.invoke({})
    assert "Session timeout" in outline
    assert "Audit log" in outline


def test_list_document_sections_offsets():
    secs = list_document_sections(MD)
    titles = [t for t, _, _ in secs if t]
    assert "Overview" in titles or "Session timeout" in titles


async def test_analyst_caps_questions_and_uses_scripted_tools():
    details = FeatureDetails(
        description="Sign-in with work email.",
        user_roles=["user"],
        functional_requirements=[],
        acceptance_criteria=[],
        questions=[
            AnalystQuestion(question=f"Q{i}?", why="w", target_field="description")
            for i in range(8)
        ],
    )
    fake = FakeChatModel(
        script=[
            {"tool": "search_document", "args": {"query": "sign in"}},
            {"tool": "read_section", "args": {"heading": "Overview"}},
            details,
            details,
        ]
    )
    set_chat_model_override(fake)
    try:
        got = await analyse_feature(
            name="Email sign-in",
            summary="Users sign in.",
            quotes=["Users can sign in with their work email."],
            markdown=MD,
        )
    finally:
        set_chat_model_override(None)
    assert len(got.questions) <= get_settings().max_questions_per_feature


async def test_analyst_budget_exhausted_forces_answer_instead_of_failing():
    """A model that never stops calling tools must not fail the document."""
    from typing import Any
    from uuid import uuid4

    from langchain_core.messages import AIMessage, ToolCall
    from langchain_core.outputs import ChatGeneration, ChatResult

    from tests.fakes import FakeStructured

    final = FeatureDetails(description="Sessions expire after 30 minutes of inactivity.")

    class LoopingFake(FakeChatModel):
        def bind_tools(self, tools: list[Any], **kwargs: Any) -> "LoopingFake":
            return self

        def with_structured_output(self, schema: Any, **kwargs: Any) -> FakeStructured:
            self._script = [final]
            return FakeStructured(self, schema)

        def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None,
                      **kwargs: Any) -> ChatResult:
            msg = AIMessage(
                content="",
                tool_calls=[ToolCall(name="search_document", args={"query": "session"},
                                     id=str(uuid4()))],
            )
            return ChatResult(generations=[ChatGeneration(message=msg)])

    set_chat_model_override(LoopingFake())
    try:
        got = await analyse_feature(
            name="Session timeout", summary="", quotes=[], markdown=MD
        )
    finally:
        set_chat_model_override(None)
    assert got.description == final.description
