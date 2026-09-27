"""Task-vs-task verdict: board dup, draft conflict, net-new, Vertex missing, on_board excluded."""

from app.agents.llm import set_chat_model_override
from app.agents.prompts import VERDICT
from app.agents.verdict import assemble_verdict_context, load_unpublished_tasks
from app.config import get_settings
from app.schemas.mvp import (
    VerdictCheckItem,
    VerdictLlmCandidate,
    VerdictLlmCitation,
    VerdictResult,
)
from tests.fakes import FakeChatModel


def _item(item_id: int | str = 99, **overrides) -> dict:
    body = {
        "id": item_id,
        "title": "Export CSV of invoices",
        "description": "Let finance download invoices as CSV.",
        "area": "billing",
    }
    body.update(overrides)
    return body


def _check_payload(item: dict | None = None, board_items: list[dict] | None = None) -> dict:
    return {
        "item": item or _item(),
        "boardItems": board_items if board_items is not None else [],
    }


def test_verdict_prompt_cite_or_stay_silent():
    assert "Cite or stay silent" in VERDICT
    assert "net-new" in VERDICT
    assert "Never invent a decision id" in VERDICT
    assert "Never emit fabricated decision citations" in VERDICT
    assert "Confidence below 70 still returns the flag" in VERDICT


async def test_board_duplicate_cites_item(api_client):
    fake = FakeChatModel(
        script=[
            VerdictResult(
                type="duplicate",
                confidence=91,
                message="Looks like a duplicate of #88 (Export invoices)",
                candidates=[
                    VerdictLlmCandidate(
                        id="88",
                        type="item",
                        title="Export invoices",
                        reason="Covers the same CSV export already on the board.",
                        confidence=91,
                    )
                ],
                citation=VerdictLlmCitation(
                    id="88",
                    type="item",
                    title="Export invoices",
                    snippet="Download invoices as a spreadsheet.",
                ),
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/verdicts/check",
            json=_check_payload(
                _item(99, title="CSV export of invoices"),
                [
                    {
                        "id": 88,
                        "title": "Export invoices",
                        "description": "Download invoices as a spreadsheet.",
                        "area": "billing",
                        "status": "inbox",
                    }
                ],
            ),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "duplicate"
    assert body["candidates"]
    assert body["candidates"][0]["type"] == "item"
    assert body["candidates"][0]["id"] == "88"
    assert body["citation"]["type"] == "item"
    assert body["citation"]["id"] == "88"


async def test_draft_conflict_cites_task(api_client, make_feature, make_task):
    feat = await make_feature()
    draft = await make_task(
        feat,
        status="draft",
        title="Rely on the customer IdP",
        description="Do not add custom SSO. Use the customer's identity provider only.",
        traces_to=["No in-house credential store"],
        acceptance_criteria=[
            {
                "given": "a user",
                "when": "they sign in",
                "then": "they use the customer IdP",
            }
        ],
    )

    fake = FakeChatModel(
        script=[
            VerdictResult(
                type="conflict",
                confidence=88,
                message="Conflicts with an unpublished generated task (Rely on the customer IdP)",
                candidates=[
                    VerdictLlmCandidate(
                        id=str(draft.id),
                        type="item",
                        title="Rely on the customer IdP",
                        reason="The draft task forbids a custom credential store.",
                        confidence=88,
                    )
                ],
                citation=VerdictLlmCitation(
                    id=str(draft.id),
                    type="item",
                    title="Rely on the customer IdP",
                    snippet="Do not add custom SSO.",
                ),
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/verdicts/check",
            json=_check_payload(
                _item(
                    12,
                    title="Build custom SSO",
                    description="In-house username and password store.",
                    area="auth",
                ),
                [],
            ),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "conflict"
    assert body["candidates"]
    assert body["candidates"][0]["id"] == str(draft.id)
    assert body["candidates"][0]["type"] == "item"
    assert "SSO" in (body["citation"]["snippet"] or "")


async def test_unique_title_is_net_new(api_client):
    fake = FakeChatModel(
        script=[
            VerdictResult(
                type="net-new",
                confidence=100,
                message="Net-new — nothing like this yet",
                candidates=[],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/verdicts/check",
            json=_check_payload(
                _item(
                    5,
                    title="Write release notes",
                    description="Draft the changelog.",
                    area="docs",
                ),
                [
                    {
                        "id": 1,
                        "title": "Export invoices",
                        "description": "CSV download.",
                        "area": "billing",
                        "status": "done",
                    }
                ],
            ),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "net-new"
    assert body["candidates"] == []
    assert body.get("citation") is None


async def test_vertex_missing_structured_4xx(api_client, monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "")
    get_settings.cache_clear()
    set_chat_model_override(None)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/verdicts/check",
            json=_check_payload(
                _item(5, title="A card"),
                [
                    {
                        "id": 1,
                        "title": "Other card",
                        "description": "",
                        "area": "auth",
                        "status": "inbox",
                    }
                ],
            ),
        )
    finally:
        get_settings.cache_clear()
    assert 400 <= resp.status_code < 500
    detail = resp.json()["detail"]
    assert {"problem", "cause", "fix"} <= set(detail)
    assert "GCP_PROJECT_ID" in detail["cause"]


async def test_on_board_tasks_excluded_from_drafts(
    api_client, make_feature, make_task, db_session
):
    feat = await make_feature()
    draft = await make_task(
        feat, status="draft", title="Draft: email sign-in", ordinal=0
    )
    await make_task(
        feat,
        status="on_board",
        title="On board: already published sign-in",
        board_item_id=71,
        ordinal=1,
    )
    approved = await make_task(
        feat, status="approved", title="Approved: MFA later", ordinal=2
    )

    unpublished = await load_unpublished_tasks(db_session, project_id="proj-test")
    ids = {t.id for t in unpublished}
    assert draft.id in ids
    assert approved.id in ids
    assert all(t.status != "on_board" for t in unpublished)
    assert all("already published" not in t.title for t in unpublished)

    ctx, allowed = assemble_verdict_context(
        item=VerdictCheckItem.model_validate(_item(5, title="Unique thing")),
        board_items=[],
        drafts=unpublished,
    )
    assert str(draft.id) in allowed
    assert str(approved.id) in allowed
    assert "already published" not in ctx
    assert "On board:" not in ctx

    # Route: only an on_board row + empty boardItems → empty compare set → net-new,
    # no Vertex. A leak of on_board into the draft query would call the model.
    other = await make_feature(project_id="proj-onboard-only")
    await make_task(
        other,
        status="on_board",
        title="On board: already published sign-in",
        board_item_id=71,
    )
    set_chat_model_override(None)
    resp = await api_client.post(
        "/api/projects/proj-onboard-only/verdicts/check",
        json=_check_payload(_item(5, title="Unique thing"), []),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "net-new"
    assert body["candidates"] == []


async def test_empty_compare_set_is_net_new_without_model(api_client):
    set_chat_model_override(None)
    resp = await api_client.post(
        "/api/projects/proj-test/verdicts/check",
        json=_check_payload(_item(5, title="Brand new idea"), []),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "net-new"
    assert body["candidates"] == []
