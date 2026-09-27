"""Ask-a-task: published card, stay-silent, Vertex missing, hand-created card."""

from app.agents.ask import assemble_ask_context
from app.agents.llm import set_chat_model_override
from app.agents.prompts import ASK
from app.config import get_settings
from app.schemas.mvp import AskItemSnapshot, AskLlmCitation, AskResult
from tests.fakes import FakeChatModel


def _item(**overrides) -> dict:
    body = {
        "title": "Implement sign-in",
        "description": "Add email sign-in.",
        "area": "auth",
        "priority": "P1",
    }
    body.update(overrides)
    return body


def _ask_payload(query: str, board_item_id: int, item: dict | None = None) -> dict:
    return {
        "query": query,
        "boardItemId": board_item_id,
        "item": item or _item(),
        "history": [],
    }


def test_ask_prompt_cite_or_stay_silent():
    assert "Answer only from the supplied context" in ASK
    assert "never invent" in ASK
    assert "No citation" in ASK
    assert "Never fabricate a decision id" in ASK


async def test_published_task_cites_source_quote(
    api_client, make_feature, make_task, db_session
):
    feat = await make_feature(
        questions=[
            {
                "question": "Which domains?",
                "why": "scope",
                "target_field": "constraints",
                "status": "answered",
            }
        ]
    )
    from sqlalchemy import select

    from app.models import FeatureQuestion

    q = (
        await db_session.execute(
            select(FeatureQuestion).where(FeatureQuestion.feature_id == feat.id)
        )
    ).scalar_one()
    q.answer = "Work email only."
    await db_session.commit()

    await make_task(
        feat,
        board_item_id=71,
        status="on_board",
        description="Implement email sign-in for work domains. Do not add SSO.",
        subtasks=["Add the form", "Validate work email"],
        definition_of_done=["Tests cover accepted emails"],
    )

    ctx, allowed = assemble_ask_context(
        board_item_id=71,
        item=AskItemSnapshot.model_validate(_item()),
        task=await _reload_task(db_session, 71),
    )
    assert "Users can sign in with their work email." in ctx
    assert "Generated task" in ctx
    assert "Work email only." in ctx
    assert any(c.type == "source" and c.id == "quote-0" for c in allowed)

    fake = FakeChatModel(
        script=[
            AskResult(
                answer="This card implements email sign-in for work domains.",
                citations=[
                    AskLlmCitation(
                        id="quote-0",
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
            "/api/projects/proj-test/ask",
            json=_ask_payload("what does this include?", 71),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert "email sign-in" in body["answer"]
    assert body["citations"]
    cite = body["citations"][0]
    assert cite["type"] == "source"
    assert "work email" in (cite.get("snippet") or "")


async def test_stay_silent_outside_context(api_client, make_feature, make_task):
    feat = await make_feature()
    await make_task(feat, board_item_id=71, status="on_board")
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
            "/api/projects/proj-test/ask",
            json=_ask_payload("why did we reject custom SSO?", 71),
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
            "/api/projects/proj-test/ask",
            json=_ask_payload("what is this?", 5, _item(title="A card")),
        )
    finally:
        get_settings.cache_clear()
    assert 400 <= resp.status_code < 500
    detail = resp.json()["detail"]
    assert {"problem", "cause", "fix"} <= set(detail)
    assert "GCP_PROJECT_ID" in detail["cause"]


async def test_hand_created_card_uses_item_snapshot_only(api_client):
    snapshot = AskItemSnapshot(
        title="Write release notes",
        description="Draft the changelog.",
        area="docs",
        priority="P2",
    )
    ctx, allowed = assemble_ask_context(board_item_id=5, item=snapshot, task=None)
    assert "Write release notes" in ctx
    assert "Draft the changelog." in ctx
    assert "Generated task" not in ctx
    assert "Parent feature" not in ctx
    assert all(c.type == "item" for c in allowed)

    fake = FakeChatModel(
        script=[
            AskResult(
                answer="This card is titled Write release notes and covers drafting the changelog.",
                citations=[
                    AskLlmCitation(
                        id="item-5",
                        type="item",
                        title="Write release notes",
                        snippet="Draft the changelog.",
                    )
                ],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/ask",
            json=_ask_payload(
                "what is this?",
                5,
                {
                    "title": "Write release notes",
                    "description": "Draft the changelog.",
                    "area": "docs",
                    "priority": "P2",
                },
            ),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert "release notes" in body["answer"].lower()
    assert body["citations"]
    assert body["citations"][0]["type"] == "item"
    assert body["citations"][0]["id"] == "item-5"


async def _reload_task(db_session, board_item_id: int):
    from app.agents.ask import load_published_task

    return await load_published_task(
        db_session, project_id="proj-test", board_item_id=board_item_id
    )
