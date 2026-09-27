"""Author documents: BRD / spec / tree, empty scope, Vertex missing."""

from datetime import UTC, datetime, timedelta

from app.agents.author import assemble_author_context, filter_features_and_tasks
from app.agents.llm import set_chat_model_override
from app.agents.memory import load_features, load_tasks
from app.agents.prompts import AUTHOR
from app.config import get_settings
from app.schemas.mvp import AskLlmCitation, AuthorBoardItem, AuthorResult
from tests.fakes import FakeChatModel

_SSO_CSV = (
    "Decision #4",
    "Decision #9",
    "Item #120",
    "Item #71",
    "Item #88",
    "CSV Export Reporter",
    "Billing Authorization Security Block",
    "single sign-on redirect",
)


def _board(
    item_id: int = 120,
    *,
    title: str = "Implement sign-in",
    area: str = "auth",
    created_at: str | None = None,
    verdict_type: str | None = None,
    **overrides,
) -> dict:
    body = {
        "id": item_id,
        "title": title,
        "description": "Add email sign-in to the product.",
        "area": area,
        "status": "inbox",
        "createdAt": created_at
            or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    if verdict_type is not None:
        body["verdictType"] = verdict_type
    body.update(overrides)
    return body


def _author_payload(
    doc_type: str = "brd",
    *,
    area: str = "auth",
    time_frame: str = "30",
    board_items: list[dict] | None = None,
    decisions: list[dict] | None = None,
) -> dict:
    return {
        "type": doc_type,
        "area": area,
        "timeFrame": time_frame,
        "boardItems": board_items if board_items is not None else [],
        "decisions": decisions if decisions is not None else [],
    }


def _assert_no_sso_sample(text: str) -> None:
    for marker in _SSO_CSV:
        assert marker not in text, f"SSO/CSV sample leaked: {marker!r}"


def test_author_prompt_cite_or_stay_silent():
    assert "only from the supplied context" in AUTHOR
    assert "never invent" in AUTHOR
    assert "No citation" in AUTHOR
    assert "Never invent Decision #4" in AUTHOR
    assert "Do not emit a sample" in AUTHOR
    assert "SSO" in AUTHOR
    assert "CSV" in AUTHOR


async def test_brd_mentions_auth_feature_and_cites(api_client, make_feature, make_task):
    feat = await make_feature()
    await make_task(feat, area="auth", title="Implement sign-in", board_item_id=120)
    fake = FakeChatModel(
        script=[
            AuthorResult(
                document=(
                    "# BRD — Authentication\n\n"
                    "## Background\n"
                    "Users can sign in with their work email "
                    "(Email sign-in).\n\n"
                    "## Requirements\n"
                    "- Implement sign-in for work email.\n"
                ),
                citations=[
                    AskLlmCitation(
                        id=f"quote-{feat.id}-0",
                        type="source",
                        title="spec.md",
                        snippet="Users can sign in with their work email.",
                    ),
                    AskLlmCitation(
                        id="item-120",
                        type="item",
                        title="Implement sign-in",
                        snippet="Add email sign-in to the product.",
                    ),
                ],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/author",
            json=_author_payload("brd", board_items=[_board(120)]),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert "Email sign-in" in body["document"]
    assert "Implement sign-in" in body["document"]
    types = {c["type"] for c in body["citations"]}
    assert "source" in types
    assert "item" in types
    assert any("work email" in (c.get("snippet") or "") for c in body["citations"])
    assert any(c["id"] == "item-120" for c in body["citations"])


async def test_spec_mentions_auth_feature_and_ac(api_client, make_feature, make_task):
    feat = await make_feature()
    await make_task(feat, area="auth", title="Implement sign-in")
    fake = FakeChatModel(
        script=[
            AuthorResult(
                document=(
                    "# Tech spec — Email sign-in\n\n"
                    "## Interfaces\n"
                    "Accept work email and sign the user in.\n\n"
                    "## Acceptance criteria\n"
                    "Given a user, when they submit email, then they are signed in.\n"
                ),
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
            "/api/projects/proj-test/author",
            json=_author_payload("spec"),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert "Email sign-in" in body["document"]
    assert "signed in" in body["document"]
    assert body["citations"]
    assert body["citations"][0]["type"] == "source"


async def test_tree_lists_only_in_scope_tasks(
    api_client, make_feature, make_task, db_session
):
    feat = await make_feature()
    await make_task(feat, area="auth", title="Implement sign-in")
    billing = await make_feature(name="Invoice export", summary="Export invoices.")
    await make_task(
        billing,
        area="reporting",
        title="Build CSV exporter",
        description="Not in the auth tree.",
    )
    loaded_feats = await load_features(db_session, project_id="proj-test")
    loaded_tasks = await load_tasks(db_session, project_id="proj-test")
    scoped_feats, scoped_tasks = filter_features_and_tasks(
        loaded_feats, loaded_tasks, area="auth"
    )
    ctx, _allowed = assemble_author_context(
        query="auth Email sign-in Implement sign-in",
        documents=[],
        features=scoped_feats,
        tasks=scoped_tasks,
        board_items=[],
        decisions=[],
    )
    assert "Implement sign-in" in ctx
    assert "Build CSV exporter" not in ctx

    fake = FakeChatModel(
        script=[
            AuthorResult(
                document=(
                    "# Task tree — auth\n"
                    "- Email sign-in\n"
                    "  - Implement sign-in\n"
                ),
                citations=[
                    AskLlmCitation(
                        id=f"feat-{feat.id}",
                        type="source",
                        title="Email sign-in",
                        snippet="Users can sign in with their work email.",
                    )
                ],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/author",
            json=_author_payload("tree"),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    document = resp.json()["document"]
    assert "Implement sign-in" in document
    assert "Build CSV exporter" not in document
    assert "OAuth configuration" not in document
    _assert_no_sso_sample(document)


async def test_empty_scope_does_not_emit_sso_sample(api_client):
    ctx, allowed = assemble_author_context(
        query="",
        documents=[],
        features=[],
        tasks=[],
        board_items=[],
        decisions=[],
    )
    _assert_no_sso_sample(ctx)
    assert allowed == []

    fake = FakeChatModel(
        script=[
            AuthorResult(
                document=(
                    "This scope is empty. There are no features, tasks, "
                    "documents, or board cards to author."
                ),
                citations=[],
            )
        ]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/author",
            json=_author_payload("brd", area="all"),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert "empty" in body["document"].lower()
    _assert_no_sso_sample(body["document"])
    assert body["citations"] == []
    assert body["unresolvedConflictsCount"] == 0
    assert body["conflicts"] == []


async def test_vertex_missing_structured_4xx(api_client, monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "")
    get_settings.cache_clear()
    set_chat_model_override(None)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/author",
            json=_author_payload("brd", board_items=[_board(1)]),
        )
    finally:
        get_settings.cache_clear()
    assert 400 <= resp.status_code < 500
    detail = resp.json()["detail"]
    assert {"problem", "cause", "fix"} <= set(detail)
    assert "GCP_PROJECT_ID" in detail["cause"]


async def test_empty_type_is_422(api_client):
    set_chat_model_override(
        FakeChatModel(script=[AuthorResult(document="should not run")])
    )
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/author",
            json={
                "type": "",
                "area": "all",
                "timeFrame": "30",
                "boardItems": [],
                "decisions": [],
            },
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 422


async def test_does_not_dump_full_markdown(make_document):
    marker = "UNIQUE_FULL_MARKDOWN_SENTENCE_THAT_MUST_NOT_APPEAR " * 40
    doc = await make_document(
        status="ready",
        filename="long-spec.md",
        markdown="# Intro\n\nNothing relevant here.\n\n" + marker,
    )
    ctx, _allowed = assemble_author_context(
        query="invoice export spreadsheet",
        documents=[doc],
        features=[],
        tasks=[],
        board_items=[AuthorBoardItem.model_validate(_board(88, title="Export invoices"))],
        decisions=[],
    )
    assert marker.strip() not in ctx
    assert "UNIQUE_FULL_MARKDOWN_SENTENCE_THAT_MUST_NOT_APPEAR" not in ctx
    assert "keyword passages" in ctx
    assert "Export invoices" in ctx


async def test_drops_fabricated_decision_citation(api_client):
    fake = FakeChatModel(
        script=[
            AuthorResult(
                document="We decided this in Decision #4.",
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
            "/api/projects/proj-test/author",
            json=_author_payload("brd", board_items=[_board(88, title="Export invoices")]),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    assert resp.json()["citations"] == []


async def test_keeps_decision_when_client_supplied(api_client):
    fake = FakeChatModel(
        script=[
            AuthorResult(
                document="Rely on the customer IdP (decision-4).",
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
            "/api/projects/proj-test/author",
            json=_author_payload(
                "brd",
                decisions=[
                    {
                        "id": 4,
                        "title": "Rely on customer IdP",
                        "description": "Minimize credentials.",
                        "area": "auth",
                    }
                ],
            ),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    cites = resp.json()["citations"]
    assert cites
    assert cites[0]["type"] == "decision"
    assert cites[0]["id"] == "decision-4"


async def test_conflicts_count_filtered_scope_only(api_client):
    fake = FakeChatModel(
        script=[AuthorResult(document="Draft.", citations=[])]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/author",
            json=_author_payload(
                "brd",
                area="auth",
                board_items=[
                    _board(10, title="Auth conflict", area="auth", verdict_type="conflict"),
                    _board(11, title="Auth ok", area="auth", verdict_type="net-new"),
                    _board(
                        12,
                        title="Reporting conflict",
                        area="reporting",
                        verdict_type="conflict",
                    ),
                ],
            ),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["unresolvedConflictsCount"] == 1
    assert body["conflicts"] == [{"id": "10", "title": "Auth conflict"}]


async def test_time_frame_drops_old_board_cards(api_client):
    old = (datetime.now(UTC) - timedelta(days=200)).isoformat()
    recent = datetime.now(UTC).isoformat()
    fake = FakeChatModel(
        script=[AuthorResult(document="Recent only.", citations=[])]
    )
    set_chat_model_override(fake)
    try:
        resp = await api_client.post(
            "/api/projects/proj-test/author",
            json=_author_payload(
                "brd",
                time_frame="30",
                board_items=[
                    _board(
                        1,
                        title="Old auth card",
                        created_at=old,
                        verdict_type="conflict",
                    ),
                    _board(
                        2,
                        title="Recent auth card",
                        created_at=recent,
                        verdict_type="conflict",
                    ),
                ],
            ),
        )
    finally:
        set_chat_model_override(None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["unresolvedConflictsCount"] == 1
    assert body["conflicts"][0]["id"] == "2"
