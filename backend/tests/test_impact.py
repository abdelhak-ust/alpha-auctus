"""Trace impact Explain: cite a neighbor, stay-silent, Vertex missing."""

from app.agents.impact import assemble_impact_context
from app.agents.llm import set_chat_model_override
from app.agents.prompts import IMPACT_EXPLAIN
from app.config import get_settings
from app.schemas.mvp import (
    AskLlmCitation,
    ImpactExplainRequest,
    ImpactExplainResult,
    ImpactNeighbor,
    ImpactNode,
)
from tests.fakes import FakeChatModel


def _node(
    node_id: str = "item-142",
    node_type: str = "item",
    label: str = "Add SSO",
) -> dict:
    return {"id": node_id, "type": node_type, "label": label}


def _neighbor(
    node_id: str = "item-120",
    node_type: str = "item",
    label: str = "Login redirect",
    edge_type: str = "affects",
) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "label": label,
        "edgeType": edge_type,
    }


def _explain_payload(
    node_id: str = "item-142",
    node: dict | None = None,
    neighbors: list[dict] | None = None,
    verdict_snippet: str | None = None,
) -> dict:
    body: dict = {
        "nodeId": node_id,
        "node": node or _node(node_id),
        "neighbors": neighbors if neighbors is not None else [_neighbor()],
    }
    if verdict_snippet is not None:
        body["verdictSnippet"] = verdict_snippet
    return body


def test_impact_explain_prompt_cite_or_stay_silent():
    assert "Answer only from the supplied subgraph" in IMPACT_EXPLAIN
    assert "never invent" in IMPACT_EXPLAIN
    assert "No citation" in IMPACT_EXPLAIN
    assert "Never fabricate a decision id" in IMPACT_EXPLAIN
    assert "Never invent decisions" in IMPACT_EXPLAIN


def test_assemble_includes_neighbor_not_full_project():
    body = ImpactExplainRequest.model_validate(
        _explain_payload(verdict_snippet="Contradicts relying on the customer IdP.")
    )
    ctx, allowed = assemble_impact_context(body)
    assert "item-142" in ctx
    assert "item-120" in ctx
    assert "Login redirect" in ctx
    assert "affects" in ctx
    assert "Contradicts relying on the customer IdP." in ctx
    assert any(c.id == "item-120" and c.type == "item" for c in allowed)
    assert "Add SSO" in ctx
    assert "CSV Reporter" not in ctx


async def test_cites_neighbor(api_client):
    fake = FakeChatModel(
        script=[
            ImpactExplainResult(
                headline="Add SSO touches login redirect",
                text=(
                    "Changing Add SSO affects the login redirect card "
                    "(#120) already on the board."
                ),
                citations=[
                    AskLlmCitation(
                        id="item-120",
                        type="item",
                        title="Login redirect",
                        snippet="Sequence route redirects on success.",
                    )
                ],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/impact/explain",
            json=_explain_payload(),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert "login redirect" in body["text"].lower()
    assert body["headline"]
    assert body["citations"]
    cite = body["citations"][0]
    assert cite["type"] == "item"
    assert cite["id"] == "item-120"


async def test_stay_silent_unknown_subgraph(api_client):
    fake = FakeChatModel(
        script=[
            ImpactExplainResult(
                headline="Nothing to explain",
                text=(
                    "The supplied subgraph does not say whether custom SSO was "
                    "decided. I will not invent that."
                ),
                citations=[],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/impact/explain",
            json=_explain_payload(
                node_id="area-billing",
                node=_node("area-billing", "area", "Billing"),
                neighbors=[],
            ),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert "does not say" in body["text"]
    assert body["citations"] == []


async def test_drops_fabricated_decision_not_in_subgraph(api_client):
    fake = FakeChatModel(
        script=[
            ImpactExplainResult(
                headline="Re-opens the SSO decision",
                text="Changing this re-opens Decision #4.",
                citations=[
                    AskLlmCitation(
                        id="decision-4",
                        type="decision",
                        title="Rely on IdP",
                        snippet="Minimize credentials.",
                    )
                ],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/impact/explain",
            json=_explain_payload(),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    assert resp.json()["citations"] == []


async def test_cites_decision_when_neighbor_is_in_subgraph(api_client):
    fake = FakeChatModel(
        script=[
            ImpactExplainResult(
                headline="Contradicts the IdP decision",
                text="Add SSO contradicts Rely on customer IdP.",
                citations=[
                    AskLlmCitation(
                        id="decision-4",
                        type="decision",
                        title="Rely on IdP",
                        snippet="Minimize credentials.",
                    )
                ],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/impact/explain",
            json=_explain_payload(
                neighbors=[
                    _neighbor(
                        "decision-4",
                        "decision",
                        "Rely on customer IdP",
                        "contradicts",
                    )
                ]
            ),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    cites = resp.json()["citations"]
    assert cites
    assert cites[0]["type"] == "decision"
    assert cites[0]["id"] == "decision-4"


async def test_vertex_missing_structured_4xx(api_client, monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "")
    get_settings.cache_clear()
    set_chat_model_override(None)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/impact/explain",
            json=_explain_payload(),
        )
    finally:
        get_settings.cache_clear()
    assert 400 <= resp.status_code < 500
    detail = resp.json()["detail"]
    assert {"problem", "cause", "fix"} <= set(detail)
    assert "GCP_PROJECT_ID" in detail["cause"]


async def test_empty_node_is_422(api_client):
    set_chat_model_override(
        FakeChatModel(
            script=[ImpactExplainResult(headline="no", text="should not run")]
        )
    )
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/impact/explain",
            json=_explain_payload(node_id="   ", node=_node("   ")),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert {"problem", "cause", "fix"} <= set(detail)


def test_neighbor_schema_roundtrip():
    neighbor = ImpactNeighbor.model_validate(_neighbor())
    node = ImpactNode.model_validate(_node())
    assert neighbor.edge_type == "affects"
    assert node.type == "item"
