"""Trace impact Explain — cited summary of a selected subgraph (plans/trace-impact-graph.md).

Uses `get_chat_model()` only. Never imports the Vertex/Gemini SDK.
Does not persist (no Edge table; chat_messages is the project workflow thread).
The client sends the subgraph; this module does not load the rest of the project.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import get_chat_model
from app.agents.prompts import IMPACT_EXPLAIN
from app.schemas.mvp import (
    AskCitation,
    AskLlmCitation,
    ImpactExplainRequest,
    ImpactExplainResponse,
    ImpactExplainResult,
    ImpactNeighbor,
    ImpactNode,
)

CitationKind = Literal["item", "decision", "source"]


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _citation_type(node_type: str) -> CitationKind:
    if node_type == "decision":
        return "decision"
    if node_type == "item":
        return "item"
    return "source"


def _as_citation(node: ImpactNode | ImpactNeighbor) -> AskCitation:
    return AskCitation(
        id=node.id,
        type=_citation_type(node.type),
        title=node.label,
        snippet=None,
    )


def _add_allowed(allowed: list[AskCitation], citation: AskCitation) -> None:
    key = (citation.type, citation.id)
    if any((c.type, c.id) == key for c in allowed):
        return
    allowed.append(citation)


def assemble_impact_context(body: ImpactExplainRequest) -> tuple[str, list[AskCitation]]:
    """Build the prompt block and the citations the model may emit.

    Only the selected node, its neighbors, and the optional verdict snippet.
    """
    allowed: list[AskCitation] = []
    _add_allowed(allowed, _as_citation(body.node))

    parts: list[str] = [
        "## Selected node",
        f"- id: {body.node_id}",
        f"- type: {body.node.type}",
        f"- label: {body.node.label}",
        "",
        "## Neighbors",
    ]
    if not body.neighbors:
        parts.append("(none)")
    for neighbor in body.neighbors:
        parts.append(
            f"- id: {neighbor.id} type: {neighbor.type} "
            f"label: {neighbor.label!r} edge: {neighbor.edge_type}"
        )
        _add_allowed(allowed, _as_citation(neighbor))

    snippet = (body.verdict_snippet or "").strip()
    parts.extend(["", "## Verdict snippet"])
    parts.append(snippet if snippet else "(none)")

    catalog = "\n".join(
        f"- type={c.type} id={c.id} title={c.title!r}"
        + (f" snippet={c.snippet!r}" if c.snippet else "")
        for c in allowed
    ) or "(none)"
    prompt = (
        "Allowed citations (use these ids; do not invent):\n"
        f"{catalog}\n\n"
        + "\n".join(parts)
    )
    return prompt, allowed


def filter_citations(
    emitted: list[AskLlmCitation],
    *,
    allowed: list[AskCitation],
) -> list[AskCitation]:
    """Keep only ids in the supplied subgraph. Fabricated decisions are dropped."""
    by_key = {(c.type, c.id): c for c in allowed}
    item_by_digits = {_digits(c.id): c for c in allowed if c.type == "item" and _digits(c.id)}
    decision_by_digits = {
        _digits(c.id): c for c in allowed if c.type == "decision" and _digits(c.id)
    }
    source_ids = {c.id for c in allowed if c.type == "source"}

    kept: list[AskCitation] = []
    seen: set[tuple[str, str]] = set()
    for raw in emitted:
        if raw.type == "item":
            cit = by_key.get(("item", raw.id))
            if cit is None:
                cit = item_by_digits.get(_digits(raw.id))
            if cit is None:
                continue
            out = AskCitation(
                id=cit.id,
                type="item",
                title=raw.title or cit.title,
                snippet=raw.snippet or cit.snippet,
            )
        elif raw.type == "decision":
            cit = by_key.get(("decision", raw.id))
            if cit is None:
                cit = decision_by_digits.get(_digits(raw.id))
            if cit is None:
                continue
            out = AskCitation(
                id=cit.id,
                type="decision",
                title=raw.title or cit.title,
                snippet=raw.snippet or cit.snippet,
            )
        elif raw.type == "source" and raw.id in source_ids:
            catalog = by_key[("source", raw.id)]
            out = AskCitation(
                id=raw.id,
                type="source",
                title=raw.title or catalog.title,
                snippet=raw.snippet or catalog.snippet,
            )
        else:
            continue
        key = (out.type, out.id)
        if key in seen:
            continue
        seen.add(key)
        kept.append(out)
    return kept


def _parse_result(result: object) -> ImpactExplainResult:
    if isinstance(result, ImpactExplainResult):
        return result
    if isinstance(result, dict):
        return ImpactExplainResult.model_validate(result)
    return ImpactExplainResult()


async def explain_impact(body: ImpactExplainRequest) -> ImpactExplainResponse:
    context, allowed = assemble_impact_context(body)
    model = get_chat_model().with_structured_output(ImpactExplainResult)
    result = await model.ainvoke(
        [
            SystemMessage(content=IMPACT_EXPLAIN),
            HumanMessage(
                content=(
                    f"Explain the impact of changing node {body.node_id}.\n\n{context}"
                )
            ),
        ]
    )
    parsed = _parse_result(result)
    return ImpactExplainResponse(
        headline=parsed.headline,
        text=parsed.text,
        citations=filter_citations(parsed.citations, allowed=allowed),
    )
