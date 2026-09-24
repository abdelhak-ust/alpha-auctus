"""HTTP-layer tests for the ingestion routes: request/response shapes and error handling.
The pipeline itself (parse/chunk/extract/embed) is mocked here since it needs a configured
Vertex AI project — see plans/ingestion.md's Verification section for the full live-integration
checks to run once GCP_PROJECT_ID is set.
"""

from httpx import ASGITransport, AsyncClient

import app.api.routes.ingestion as ingestion_routes
from app.main import app
from app.schemas.ingestion import CitationOut, IngestItemOut, VerdictDetailOut


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _sample_item(candidate_id: str = "ingest-abc123") -> IngestItemOut:
    return IngestItemOut(
        id=candidate_id,
        title="Add SSO for enterprise clients",
        description="Enterprise clients want SSO via their own IdP.",
        area="auth",
        priority="P1",
        source_id="src-xyz",
        source_snippet="we need SSO for our enterprise customers",
        verdict=VerdictDetailOut(
            type="conflict",
            confidence=88,
            message="Conflicts with Decision #4 (Use customer IdP)",
            candidates=[],
            citation=CitationOut(id="4", type="decision", title="Use customer IdP", snippet="..."),
        ),
    )


async def test_upload_text_returns_the_extracted_candidates(monkeypatch):
    async def fake_ingest_source(_db, **_kwargs):
        return object(), [_sample_item()]

    monkeypatch.setattr(ingestion_routes, "ingest_source", fake_ingest_source)

    async with await _client() as client:
        resp = await client.post(
            "/api/sources/upload",
            json={"fileName": "brief.txt", "fileContent": "we need SSO", "projectId": "proj-1"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert body["items"][0]["sourceId"] == "src-xyz"  # camelCase on the wire
    assert body["items"][0]["verdict"]["type"] == "conflict"


async def test_upload_text_unsupported_type_is_422(monkeypatch):
    from app.ingest.parse import UnsupportedSourceType

    async def fake_ingest_source(_db, **_kwargs):
        raise UnsupportedSourceType("video/mp4", "call.mp4")

    monkeypatch.setattr(ingestion_routes, "ingest_source", fake_ingest_source)

    async with await _client() as client:
        resp = await client.post(
            "/api/sources/upload",
            json={"fileName": "call.mp4", "fileContent": "x", "projectId": "proj-1"},
        )

    assert resp.status_code == 422
    assert "call.mp4" in resp.json()["detail"]


async def test_resolve_approve_returns_item_for_node_to_build(monkeypatch):
    from app.models import IngestCandidate

    async def fake_resolve_candidate(_db, *, candidate_id, action):
        return IngestCandidate(
            id=candidate_id,
            project_id="proj-1",
            title="Add SSO",
            description="desc",
            entity_tags=["auth"],
            priority="P1",
            source_id="src-1",
            snippet="we need SSO",
            status="approved" if action == "approve" else "dismissed",
            verdict={},
        )

    monkeypatch.setattr(ingestion_routes, "resolve_candidate", fake_resolve_candidate)

    async with await _client() as client:
        resp = await client.post(
            "/api/ingest/resolve",
            json={"id": "ingest-abc", "action": "approve", "projectId": "proj-1"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["item"]["area"] == "auth"
    assert body["item"]["title"] == "Add SSO"


async def test_resolve_dismiss_returns_no_item(monkeypatch):
    from app.models import IngestCandidate

    async def fake_resolve_candidate(_db, *, candidate_id, action):
        return IngestCandidate(
            id=candidate_id,
            project_id="proj-1",
            title="Add SSO",
            entity_tags=[],
            priority="P2",
            source_id="src-1",
            snippet="x",
            status="dismissed",
            verdict={},
        )

    monkeypatch.setattr(ingestion_routes, "resolve_candidate", fake_resolve_candidate)

    async with await _client() as client:
        resp = await client.post(
            "/api/ingest/resolve",
            json={"id": "ingest-abc", "action": "dismiss", "projectId": "proj-1"},
        )

    assert resp.status_code == 200
    assert resp.json()["item"] is None


async def test_resolve_unknown_id_is_404(monkeypatch):
    async def fake_resolve_candidate(_db, *, candidate_id, action):
        return None

    monkeypatch.setattr(ingestion_routes, "resolve_candidate", fake_resolve_candidate)

    async with await _client() as client:
        resp = await client.post(
            "/api/ingest/resolve",
            json={"id": "does-not-exist", "action": "approve", "projectId": "proj-1"},
        )

    assert resp.status_code == 404


async def test_resolve_invalid_action_is_422():
    async with await _client() as client:
        resp = await client.post(
            "/api/ingest/resolve",
            json={"id": "ingest-abc", "action": "explode", "projectId": "proj-1"},
        )

    assert resp.status_code == 422


async def test_source_status_unknown_id_is_404():
    async with await _client() as client:
        resp = await client.get("/api/sources/does-not-exist/status")

    assert resp.status_code == 404
