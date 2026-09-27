"""Project Memory Ask: feature quote, board item, stay-silent, Vertex missing."""

from app.agents.llm import set_chat_model_override
from app.agents.memory import assemble_memory_context, load_features
from app.agents.prompts import MEMORY_ASK
from app.config import get_settings
from app.schemas.mvp import AskLlmCitation, AskResult, MemoryBoardItem
from tests.fakes import FakeChatModel


def _board(item_id: int = 88, **overrides) -> dict:
    body = {
        "id": item_id,
        "title": "Export invoices",
        "description": "Download invoices as a spreadsheet.",
        "area": "billing",
        "status": "inbox",
    }
    body.update(overrides)
    return body


def _memory_payload(query: str, board_items: list[dict] | None = None) -> dict:
    return {
        "query": query,
        "history": [],
        "boardItems": board_items if board_items is not None else [],
    }


def test_memory_ask_prompt_cite_or_stay_silent():
    assert "Answer only from the supplied context" in MEMORY_ASK
    assert "never invent" in MEMORY_ASK
    assert "No citation" in MEMORY_ASK
    assert "Never fabricate a decision id" in MEMORY_ASK
    assert "Never invent Decision Records" in MEMORY_ASK
    assert "no documents, features, or tasks" in MEMORY_ASK


async def test_feature_quote_cites_source(api_client, make_feature, make_task, db_session):
    feat = await make_feature()
    await make_task(feat, status="draft", title="Implement email sign-in")
    loaded = await load_features(db_session, project_id="proj-test")

    ctx, allowed = assemble_memory_context(
        query="work email sign-in",
        documents=[],
        features=loaded,
        tasks=[],
        board_items=[],
    )
    assert "Users can sign in with their work email." in ctx
    assert any(c.type == "source" and "work email" in (c.snippet or "") for c in allowed)

    fake = FakeChatModel(
        script=[
            AskResult(
                answer="The spec says users can sign in with their work email.",
                citations=[
                    AskLlmCitation(
                        id=f"quote-{feat.id}-0",
                        type="source",
                        title="spec.md",
                        snippet="Users can sign in with their work email.",
                    )
                ],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/memory/ask",
            json=_memory_payload("what did we decide about work email?"),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert "work email" in body["answer"]
    assert body["citations"]
    cite = body["citations"][0]
    assert cite["type"] == "source"
    assert "work email" in (cite.get("snippet") or "")


async def test_board_card_cites_item(api_client):
    fake = FakeChatModel(
        script=[
            AskResult(
                answer="Export invoices is already on the board.",
                citations=[
                    AskLlmCitation(
                        id="item-88",
                        type="item",
                        title="Export invoices",
                        snippet="Download invoices as a spreadsheet.",
                    )
                ],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/memory/ask",
            json=_memory_payload(
                "is anyone already working on invoice export?",
                [_board(88)],
            ),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert "invoice" in body["answer"].lower()
    assert body["citations"]
    assert body["citations"][0]["type"] == "item"
    assert body["citations"][0]["id"] == "item-88"


async def test_stay_silent_unknown(api_client, make_feature):
    await make_feature()
    fake = FakeChatModel(
        script=[
            AskResult(
                answer=(
                    "The supplied context does not say whether custom SSO was decided. "
                    "I will not invent that."
                ),
                citations=[],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/memory/ask",
            json=_memory_payload("why did we reject custom SSO?"),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert "does not say" in body["answer"]
    assert body["citations"] == []


async def test_vertex_missing_structured_4xx(api_client, monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "")
    get_settings.cache_clear()
    set_chat_model_override(None)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/memory/ask",
            json=_memory_payload("what is in memory?", [_board(1)]),
        )
    finally:
        get_settings.cache_clear()
    assert 400 <= resp.status_code < 500
    detail = resp.json()["detail"]
    assert {"problem", "cause", "fix"} <= set(detail)
    assert "GCP_PROJECT_ID" in detail["cause"]


async def test_empty_query_is_422(api_client):
    set_chat_model_override(
        FakeChatModel(script=[AskResult(answer="should not run", citations=[])])
    )
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/memory/ask",
            json=_memory_payload("   "),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert {"problem", "cause", "fix"} <= set(detail)


async def test_does_not_dump_full_markdown(make_document):
    marker = "UNIQUE_FULL_MARKDOWN_SENTENCE_THAT_MUST_NOT_APPEAR " * 40
    doc = await make_document(
        status="ready",
        filename="long-spec.md",
        markdown="# Intro\n\nNothing relevant here.\n\n" + marker,
    )
    ctx, _allowed = assemble_memory_context(
        query="invoice export spreadsheet",
        documents=[doc],
        features=[],
        tasks=[],
        board_items=[
            MemoryBoardItem.model_validate(_board(88)),
        ],
    )
    assert marker.strip() not in ctx
    assert "UNIQUE_FULL_MARKDOWN_SENTENCE_THAT_MUST_NOT_APPEAR" not in ctx
    assert "keyword passages" in ctx
    assert "Export invoices" in ctx


async def test_drops_fabricated_decision_citation(api_client):
    fake = FakeChatModel(
        script=[
            AskResult(
                answer="We decided this in a Decision Record.",
                citations=[
                    AskLlmCitation(
                        id="decision-4",
                        type="decision",
                        title="SSO decision",
                        snippet="Use the customer IdP.",
                    )
                ],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/memory/ask",
            json=_memory_payload("what did we decide?", [_board(88)]),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    assert resp.json()["citations"] == []
