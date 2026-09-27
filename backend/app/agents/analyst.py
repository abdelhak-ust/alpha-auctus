"""Feature Analyst — tool-using ReAct agent (pass 2 + questions)."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.llm import get_chat_model
from app.agents.prompts import ANALYST
from app.agents.tools import bind_document_tools
from app.config import get_settings
from app.schemas.mvp import FeatureDetails

logger = logging.getLogger(__name__)

# Evidence handed to the forced final answer when the tool budget runs out.
MAX_EVIDENCE_CHARS = 12_000


async def analyse_feature(
    *,
    name: str,
    summary: str,
    quotes: list[str],
    markdown: str,
) -> FeatureDetails:
    """Collect details + questions for one feature. Recursion is bounded by analyst_max_steps.

    If the agent is still calling tools when the budget runs out, it is not an error: the
    passages it already read are handed to one structured-output call that must answer.
    """
    from langgraph.errors import GraphRecursionError
    from langgraph.prebuilt import create_react_agent

    settings = get_settings()
    tools = bind_document_tools(markdown)
    model = get_chat_model()
    agent = create_react_agent(
        model,
        tools,
        prompt=ANALYST.format(max_steps=settings.analyst_max_steps),
        response_format=FeatureDetails,
    )
    quote_block = "\n".join(f"- {q}" for q in quotes) or "(none)"
    request = (
        f"Feature: {name}\nSummary: {summary}\n"
        f"Known quotes:\n{quote_block}\n\n"
        "Gather the relevant information with the tools, then answer."
    )
    # analyst_max_steps bounds *tool rounds*. LangGraph counts every superstep
    # (agent + tools, then structured-output), so 8 as recursion_limit dies after
    # ~3 tool calls.
    limit = settings.analyst_max_steps * 2 + 4
    last: dict[str, Any] = {}
    try:
        async for state in agent.astream(
            {"messages": [HumanMessage(content=request)]},
            {"recursion_limit": limit},
            stream_mode="values",
        ):
            last = state
    except GraphRecursionError:
        logger.warning("Analyst hit its tool budget on %r; forcing a final answer.", name)
        details = await _force_answer(request, list(last.get("messages") or []))
    else:
        details = _coerce(last.get("structured_response"), summary)

    cap = settings.max_questions_per_feature
    if len(details.questions) > cap:
        details = details.model_copy(update={"questions": details.questions[:cap]})
    return details


def _coerce(structured: Any, summary: str) -> FeatureDetails:
    if isinstance(structured, FeatureDetails):
        return structured
    if isinstance(structured, dict):
        return FeatureDetails.model_validate(structured)
    return FeatureDetails(description=summary)


async def _force_answer(request: str, messages: list[BaseMessage]) -> FeatureDetails:
    """Answer from the passages already retrieved — no more tool calls.

    The transcript is flattened to text: a raw replay could end on an AI tool call with no
    tool result, which Gemini rejects.
    """
    evidence = "\n\n---\n\n".join(
        str(m.content) for m in messages if isinstance(m, ToolMessage) and m.content
    )[:MAX_EVIDENCE_CHARS] or "(no passages retrieved)"
    model = get_chat_model().with_structured_output(FeatureDetails)
    result = await model.ainvoke(
        [
            SystemMessage(content=ANALYST.format(max_steps=0)),
            HumanMessage(
                content=(
                    f"{request}\n\nYour tool budget is spent. Answer now using ONLY these "
                    "passages you already retrieved. Omit any claim you cannot quote from "
                    "them; ask a question instead.\n\n"
                    f"Retrieved passages:\n{evidence}"
                )
            ),
        ]
    )
    return _coerce(result, "")
