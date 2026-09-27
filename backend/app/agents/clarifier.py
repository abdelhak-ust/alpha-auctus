"""Clarifier — tool-using ReAct agent. Writes only through tools."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.agents.llm import get_chat_model
from app.agents.prompts import CLARIFIER
from app.agents.tools import ClarifierScratch, bind_clarifier_tools
from app.config import get_settings


async def clarify(
    *,
    feature_name: str,
    feature_summary: str,
    details: dict,
    question: str,
    why: str,
    target_field: str,
    answer: str,
    existing_follow_ups: int = 0,
) -> ClarifierScratch:
    """Run the Clarifier on one PM answer. Returns the scratch (updates / follow-ups / resolved)."""
    from langgraph.prebuilt import create_react_agent

    settings = get_settings()
    remaining = max(0, settings.max_follow_ups_per_feature - existing_follow_ups)
    scratch = ClarifierScratch(
        follow_up_count=existing_follow_ups,
        max_follow_ups=settings.max_follow_ups_per_feature,
    )
    tools = bind_clarifier_tools(scratch)
    agent = create_react_agent(get_chat_model(), tools, prompt=CLARIFIER)
    result = await agent.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        f"Feature: {feature_name}\nSummary: {feature_summary}\n"
                        f"Current details (JSON): {details}\n\n"
                        f"Question: {question}\nWhy: {why}\nTarget field: {target_field}\n"
                        f"PM answer: {answer}\n\n"
                        f"Follow-ups already asked: {existing_follow_ups}. "
                        f"You may ask {remaining} more."
                    )
                )
            ]
        },
        {"recursion_limit": 8},
    )
    # If the agent produced no tool writes, treat the answer as a field update + resolved.
    if not scratch.updates and not scratch.follow_ups and not scratch.resolved:
        if answer.strip() and target_field:
            scratch.updates.append({"field": target_field, "value": answer.strip()})
        scratch.resolved = True
    _ = result
    return scratch
