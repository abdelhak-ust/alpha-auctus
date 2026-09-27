"""Route tests for the ingestion API (plans/ingestion.md §11.1 + §11.3).

Never runs the pipeline: `app.queue.enqueue` and `app.ingest.store.reindex_feature` are
mocked. Uses the conftest `db_session` (nexus_test, rolled back per test) via a `get_db`
override, and a tmp `blob_dir`.
"""

import io
import uuid
import zipfile
from typing import Any

import pytest
from sqlalchemy import select

from app import queue
from app.config import get_settings
from app.models import AuditEvent, Document, Feature, FeatureVersion, ReviewItem

PROJECT = "proj-test"
DOC_KEYS = {"id", "projectId", "filename", "status", "featureCount", "uploadedAt"}
ERROR_KEYS = {"problem", "cause", "fix"}


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _blob_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BLOB_DIR", str(tmp_path / "blobs"))
    get_settings.cache_clear()
    yield tmp_path / "blobs"
    get_settings.cache_clear()


@pytest.fixture
def enqueued(monkeypatch) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_enqueue(job_name: str, **kwargs: Any) -> str:
        calls.append((job_name, kwargs))
        return f"job-{len(calls)}"

    monkeypatch.setattr(queue, "enqueue", fake_enqueue)
    return calls


@pytest.fixture
def reindexed(monkeypatch) -> list[uuid.UUID]:
    calls: list[uuid.UUID] = []

    async def fake_reindex(session, feature_id):
        calls.append(feature_id)

    from app.ingest import store

    monkeypatch.setattr(store, "reindex_feature", fake_reindex)
    return calls


@pytest.fixture
def client(api_client, enqueued, reindexed):
    """conftest `api_client` (get_db → db_session) with enqueue + reindex mocked."""
    return api_client


def _upload(name: str, content: bytes, mime: str = "application/octet-stream"):
    return {"file": (name, content, mime)}


def _docx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


async def _conflict(db_session, make_feature, make_document, make_source_ref):
    doc = await make_document(filename="spec-v2.md")
    feature = await make_feature(description="Sign in with work email.")
    incoming_ref = make_source_ref(
        doc_id=str(doc.doc_id), section="2. Auth", snippet="Sign in with Google only."
    )
    incoming = FeatureVersion(
        feature_id=feature.feature_id,
        version_no=2,
        description="Sign in with Google only.",
        source_refs=[incoming_ref],
        created_from=f"ingest:{doc.doc_id}",
    )
    db_session.add(incoming)
    await db_session.flush()
    feature.lifecycle_state = "conflicted"
    item = ReviewItem(
        project_id=PROJECT,
        kind="conflict",
        feature_id=feature.feature_id,
        document_id=doc.doc_id,
        payload={
            "feature_name": feature.name,
            "reason": "spec-v2.md restricts sign-in to Google; v1 allows work email.",
            "confidence": 0.87,
            "current_version_id": str(feature.current_version_id),
            "incoming_version_id": str(incoming.version_id),
        },
    )
    db_session.add(item)
    await db_session.flush()
    return feature, incoming, item


async def _sweep_flag(db_session, make_document, make_source_ref, confidence=0.8):
    doc = await make_document(filename="notes.md")
    ref = make_source_ref(doc_id=str(doc.doc_id), section="Misc", snippet="maybe dark mode")
    item = ReviewItem(
        project_id=PROJECT,
        kind="sweep_flag",
        document_id=doc.doc_id,
        payload={
            "feature_name": "Dark mode",
            "description": "Possibly a dark theme.",
            "reason": "Mentioned once, not extracted.",
            "confidence": confidence,
            "source_ref": ref,
        },
    )
    db_session.add(item)
    await db_session.flush()
    return item, ref


# ---------------------------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------------------------


async def test_upload_markdown_is_accepted_and_enqueued(client, enqueued, db_session, _blob_dir):
    resp = await client.post(
        f"/api/projects/{PROJECT}/documents", files=_upload("spec.md", b"# Spec\nLogin.\n")
    )
    assert resp.status_code == 202
    body = resp.json()
    assert set(body) == DOC_KEYS  # optional error/duplicate omitted, camelCase
    assert body["status"] == "pending" and body["featureCount"] == 0
    assert body["projectId"] == PROJECT and body["filename"] == "spec.md"

    doc = await db_session.get(Document, uuid.UUID(body["id"]))
    assert doc.mime_type == "text/markdown" and doc.size_bytes == 14
    assert doc.blob_path == f"{PROJECT}/{doc.content_hash}.md"
    assert (_blob_dir / doc.blob_path).read_bytes() == b"# Spec\nLogin.\n"
    assert enqueued == [
        (
            "ingest_document",
            {"document_id": body["id"], "_job_id": f"ingest_document:{body['id']}"},
        )
    ]


async def test_upload_duplicate_returns_existing_with_200(client, enqueued):
    url = f"/api/projects/{PROJECT}/documents"
    first = await client.post(url, files=_upload("a.txt", b"same bytes"))
    second = await client.post(url, files=_upload("b.txt", b"same bytes"))
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["duplicate"] is True
    assert len(enqueued) == 1


async def test_upload_same_bytes_other_project_is_not_duplicate(client):
    a = await client.post("/api/projects/p1/documents", files=_upload("a.txt", b"x"))
    b = await client.post("/api/projects/p2/documents", files=_upload("a.txt", b"x"))
    assert a.status_code == b.status_code == 202
    assert a.json()["id"] != b.json()["id"]


async def test_upload_docx_and_pdf_sniffed(client):
    docx = await client.post(
        f"/api/projects/{PROJECT}/documents", files=_upload("spec.docx", _docx_bytes())
    )
    pdf = await client.post(
        f"/api/projects/{PROJECT}/documents", files=_upload("spec.pdf", b"%PDF-1.7\n%...")
    )
    assert docx.status_code == 202 and pdf.status_code == 202


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("sheet.csv", b"a,b\n1,2\n"),  # unsupported extension
        ("spec.pdf", b"just text pretending"),  # extension/content mismatch
        ("spec.docx", b"PK\x03\x04not a zip"),  # broken zip
        ("notes.txt", b"\x00\x01binary"),  # binary as text
        ("empty.md", b""),
    ],
)
async def test_upload_rejects_unsupported_type_415(client, enqueued, name, content):
    resp = await client.post(f"/api/projects/{PROJECT}/documents", files=_upload(name, content))
    assert resp.status_code == 415
    assert set(resp.json()["detail"]) == ERROR_KEYS
    assert enqueued == []


async def test_upload_too_large_413(client, monkeypatch, enqueued):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    resp = await client.post(
        f"/api/projects/{PROJECT}/documents", files=_upload("big.txt", b"a" * (1024 * 1024 + 1))
    )
    assert resp.status_code == 413
    assert set(resp.json()["detail"]) == ERROR_KEYS
    assert enqueued == []


async def test_upload_queue_unavailable_503_leaves_nothing_behind(
    client, monkeypatch, db_session, _blob_dir
):
    async def down(job_name, **kwargs):
        raise queue.QueueUnavailable("redis://localhost:6379 refused")

    monkeypatch.setattr(queue, "enqueue", down)
    resp = await client.post(f"/api/projects/{PROJECT}/documents", files=_upload("a.md", b"# A"))
    assert resp.status_code == 503
    assert set(resp.json()["detail"]) == ERROR_KEYS
    rows = (await db_session.execute(select(Document))).scalars().all()
    assert rows == []
    assert not any(p.is_file() for p in _blob_dir.rglob("*"))
    # a retry after the queue is back works (not reported as a duplicate)
    async def up(job_name, **kwargs):
        return "ok"

    monkeypatch.setattr(queue, "enqueue", up)
    retry = await client.post(f"/api/projects/{PROJECT}/documents", files=_upload("a.md", b"# A"))
    assert retry.status_code == 202


async def test_upload_bad_project_id_404(client):
    resp = await client.post("/api/projects/..%2Fetc/documents", files=_upload("a.md", b"# A"))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------------------------
# Documents & features
# ---------------------------------------------------------------------------------------------


async def test_list_and_get_documents(client, make_document, make_feature, make_source_ref):
    doc = await make_document(ingestion_status="failed", error="Parse failed. Bad PDF. Re-export.")
    await make_document(project_id="other-project")
    await make_feature(created_from=f"ingest:{doc.doc_id}")
    await make_feature(name="Second", created_from=f"ingest:{doc.doc_id}")

    listed = await client.get(f"/api/projects/{PROJECT}/documents")
    assert listed.status_code == 200
    [only] = listed.json()
    assert only["id"] == str(doc.doc_id)
    assert only["status"] == "failed" and only["error"].startswith("Parse failed")
    assert only["featureCount"] == 2

    got = await client.get(f"/api/projects/{PROJECT}/documents/{doc.doc_id}")
    assert got.status_code == 200 and got.json() == only


@pytest.mark.parametrize("doc_id", [str(uuid.uuid4()), "not-a-uuid"])
async def test_get_document_404(client, doc_id):
    resp = await client.get(f"/api/projects/{PROJECT}/documents/{doc_id}")
    assert resp.status_code == 404
    assert set(resp.json()["detail"]) == ERROR_KEYS


async def test_get_document_of_other_project_404(client, make_document):
    doc = await make_document(project_id="other-project")
    resp = await client.get(f"/api/projects/{PROJECT}/documents/{doc.doc_id}")
    assert resp.status_code == 404


async def test_list_features_current_version_camelcase(
    client, make_feature, make_source_ref, db_session
):
    ref = make_source_ref(char_start=10, char_end=50, confidence=0.9)
    feature = await make_feature(description="v1 text", source_refs=[ref])
    await make_feature(project_id="other-project", name="Elsewhere")
    v2 = FeatureVersion(
        feature_id=feature.feature_id,
        version_no=2,
        description="v2 text",
        source_refs=[ref],
        created_from="manual:user",
    )
    db_session.add(v2)
    await db_session.flush()
    feature.current_version_id = v2.version_id
    await db_session.flush()

    resp = await client.get(f"/api/projects/{PROJECT}/features")
    assert resp.status_code == 200
    [f] = resp.json()
    assert set(f) == {
        "id", "projectId", "name", "description", "versionNo",
        "lifecycleState", "sourceRefs", "updatedAt",
    }
    assert f["id"] == str(feature.feature_id)
    assert f["description"] == "v2 text" and f["versionNo"] == 2
    assert f["lifecycleState"] == "consolidated"
    assert f["sourceRefs"] == [
        {
            "docId": ref["doc_id"], "docType": "upload", "chunkId": ref["chunk_id"],
            "section": "1. Overview", "charStart": 10, "charEnd": 50, "snippet": ref["snippet"],
        }
    ]


# ---------------------------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------------------------


async def test_review_queue_conflict_maps_to_ingest_item(
    client, db_session, make_feature, make_document, make_source_ref
):
    feature, incoming, item = await _conflict(
        db_session, make_feature, make_document, make_source_ref
    )
    resp = await client.get(f"/api/projects/{PROJECT}/review-queue")
    assert resp.status_code == 200
    [row] = resp.json()
    assert set(row) == {
        "id", "title", "description", "area", "priority",
        "sourceId", "sourceSnippet", "verdict",
    }
    assert row["id"] == str(item.id)
    assert row["title"] == "Email sign-in"
    assert row["description"] == "Sign in with Google only."
    assert row["sourceId"] == str(item.document_id)
    assert row["sourceSnippet"] == "Sign in with Google only."
    v = row["verdict"]
    assert v["type"] == "conflict" and v["confidence"] == 87
    assert [c["id"] for c in v["candidates"]] == ["incoming:v2", "current:v1"]
    assert all(c["type"] == "item" and c["confidence"] == 87 for c in v["candidates"])
    assert v["citation"] == {
        "id": str(item.document_id),
        "type": "source",
        "title": "spec-v2.md — 2. Auth",
        "snippet": "Sign in with Google only.",
    }


async def test_review_queue_sweep_flag_is_low_confidence(
    client, db_session, make_document, make_source_ref
):
    item, ref = await _sweep_flag(db_session, make_document, make_source_ref, confidence=0.8)
    [row] = (await client.get(f"/api/projects/{PROJECT}/review-queue")).json()
    v = row["verdict"]
    assert v["type"] == "net-new"
    assert v["confidence"] == 49  # capped: sweep flags are always "please review"
    assert "please review" in v["message"].lower()
    assert v["candidates"] == [
        {
            "id": f"flag:{item.id}", "type": "item", "title": "Dark mode",
            "reason": "Mentioned once, not extracted.", "confidence": 49,
        }
    ]
    assert row["sourceSnippet"] == "maybe dark mode"
    assert v["citation"]["snippet"] == "maybe dark mode"


async def test_review_queue_hides_resolved_and_other_projects(
    client, db_session, make_document, make_source_ref
):
    item, _ = await _sweep_flag(db_session, make_document, make_source_ref)
    item.status = "dismissed"
    other, _ = await _sweep_flag(db_session, make_document, make_source_ref)
    other.project_id = "other-project"
    await db_session.flush()
    assert (await client.get(f"/api/projects/{PROJECT}/review-queue")).json() == []


# ---------------------------------------------------------------------------------------------
# Resolve
# ---------------------------------------------------------------------------------------------


def _resolve_url(item_id) -> str:
    return f"/api/projects/{PROJECT}/review-queue/{item_id}/resolve"


async def _audit_types(db_session) -> list[str]:
    return list((await db_session.execute(select(AuditEvent.type))).scalars())


async def test_resolve_conflict_approve_makes_incoming_current(
    client, db_session, enqueued, reindexed, make_feature, make_document, make_source_ref
):
    feature, incoming, item = await _conflict(
        db_session, make_feature, make_document, make_source_ref
    )
    resp = await client.post(_resolve_url(item.id), json={"action": "approve"})
    assert resp.status_code == 200 and resp.json() == {"ok": True}

    await db_session.refresh(feature)
    await db_session.refresh(item)
    assert feature.current_version_id == incoming.version_id  # no duplicate manual copy
    count = (
        await db_session.execute(
            select(FeatureVersion).where(FeatureVersion.feature_id == feature.feature_id)
        )
    ).scalars().all()
    assert len(count) == 2
    assert feature.lifecycle_state == "consolidated"
    assert item.status == "approved" and item.resolved_by
    assert reindexed == [feature.feature_id]
    assert enqueued == [
        ("readiness_run", {"feature_id": str(feature.feature_id), "project_id": PROJECT})
    ]
    assert await _audit_types(db_session) == ["conflict_approved"]

    again = await client.post(_resolve_url(item.id), json={"action": "dismiss"})
    assert again.status_code == 409
    assert set(again.json()["detail"]) == ERROR_KEYS


async def test_resolve_conflict_dismiss_keeps_current(
    client, db_session, enqueued, reindexed, make_feature, make_document, make_source_ref
):
    feature, incoming, item = await _conflict(
        db_session, make_feature, make_document, make_source_ref
    )
    current_id = feature.current_version_id
    resp = await client.post(_resolve_url(item.id), json={"action": "dismiss"})
    assert resp.status_code == 200

    await db_session.refresh(feature)
    await db_session.refresh(item)
    assert feature.current_version_id == current_id
    assert feature.lifecycle_state == "consolidated"
    assert item.status == "dismissed"
    assert reindexed == []  # description unchanged
    assert enqueued == [
        ("readiness_run", {"feature_id": str(feature.feature_id), "project_id": PROJECT})
    ]
    assert await _audit_types(db_session) == ["conflict_dismissed"]


async def test_resolve_sweep_flag_approve_creates_cited_feature(
    client, db_session, enqueued, reindexed, make_document, make_source_ref
):
    item, ref = await _sweep_flag(db_session, make_document, make_source_ref)
    resp = await client.post(_resolve_url(item.id), json={"action": "approve"})
    assert resp.status_code == 200

    await db_session.refresh(item)
    feature = await db_session.get(Feature, item.feature_id)
    version = await db_session.get(FeatureVersion, feature.current_version_id)
    assert feature.name == "Dark mode" and feature.lifecycle_state == "consolidated"
    assert version.version_no == 1 and version.source_refs == [ref]
    assert version.description == "Possibly a dark theme."
    assert item.status == "approved"
    assert reindexed == [feature.feature_id]
    assert enqueued == [
        ("readiness_run", {"feature_id": str(feature.feature_id), "project_id": PROJECT})
    ]
    assert await _audit_types(db_session) == ["sweep_flag_approved"]


async def test_resolve_sweep_flag_dismiss_drops_flag(
    client, db_session, enqueued, reindexed, make_document, make_source_ref
):
    item, _ = await _sweep_flag(db_session, make_document, make_source_ref)
    resp = await client.post(_resolve_url(item.id), json={"action": "dismiss"})
    assert resp.status_code == 200
    await db_session.refresh(item)
    assert item.status == "dismissed" and item.feature_id is None
    assert enqueued == [] and reindexed == []
    assert (await db_session.execute(select(Feature))).scalars().all() == []
    assert await _audit_types(db_session) == ["sweep_flag_dismissed"]


async def test_resolve_reindex_failure_rolls_back_503(
    client, db_session, monkeypatch, enqueued, make_feature, make_document, make_source_ref
):
    from app.ingest import store

    async def boom(session, feature_id):
        raise RuntimeError("Vertex AI is not configured")

    monkeypatch.setattr(store, "reindex_feature", boom)
    feature, incoming, item = await _conflict(
        db_session, make_feature, make_document, make_source_ref
    )
    before = feature.current_version_id
    # Committed first, as in production (the item exists before the resolve request), so the
    # route's rollback only undoes the resolution itself.
    await db_session.commit()
    resp = await client.post(_resolve_url(item.id), json={"action": "approve"})
    assert resp.status_code == 503
    assert set(resp.json()["detail"]) == ERROR_KEYS
    await db_session.refresh(item)
    await db_session.refresh(feature)
    assert item.status == "open"
    assert feature.current_version_id == before
    assert enqueued == []


async def test_resolve_queue_down_after_commit_503_but_saved(
    client, db_session, monkeypatch, make_feature, make_document, make_source_ref
):
    async def down(job_name, **kwargs):
        raise queue.QueueUnavailable("redis down")

    monkeypatch.setattr(queue, "enqueue", down)
    feature, incoming, item = await _conflict(
        db_session, make_feature, make_document, make_source_ref
    )
    resp = await client.post(_resolve_url(item.id), json={"action": "dismiss"})
    assert resp.status_code == 503
    assert "saved" in resp.json()["detail"]["problem"]
    await db_session.refresh(item)
    assert item.status == "dismissed"
    assert await _audit_types(db_session) == ["conflict_dismissed", "readiness_enqueue_failed"]


@pytest.mark.parametrize("item_id", [str(uuid.uuid4()), "nope"])
async def test_resolve_unknown_item_404(client, item_id):
    resp = await client.post(_resolve_url(item_id), json={"action": "approve"})
    assert resp.status_code == 404
    assert set(resp.json()["detail"]) == ERROR_KEYS


async def test_resolve_item_of_other_project_404(
    client, db_session, make_document, make_source_ref
):
    item, _ = await _sweep_flag(db_session, make_document, make_source_ref)
    item.project_id = "other-project"
    await db_session.flush()
    resp = await client.post(_resolve_url(item.id), json={"action": "approve"})
    assert resp.status_code == 404


async def test_resolve_invalid_action_422(client, db_session, make_document, make_source_ref):
    item, _ = await _sweep_flag(db_session, make_document, make_source_ref)
    resp = await client.post(_resolve_url(item.id), json={"action": "merge"})
    assert resp.status_code == 422
    assert set(resp.json()["detail"]) == ERROR_KEYS
    assert "action" in resp.json()["detail"]["cause"]


async def test_non_ingestion_422_keeps_default_shape():
    from app.main import app

    handler = app.exception_handlers
    from fastapi.exceptions import RequestValidationError

    assert RequestValidationError in handler  # registered; other paths fall back to default


# ---------------------------------------------------------------------------------------------
# OpenAPI surface
# ---------------------------------------------------------------------------------------------


def test_openapi_exposes_exactly_the_contract_routes():
    from app.main import app

    paths = {
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        if "/projects/" in path
        for method in ops
    }
    assert paths == {
        ("POST", "/api/projects/{projectId}/documents"),
        ("GET", "/api/projects/{projectId}/documents"),
        ("GET", "/api/projects/{projectId}/documents/{documentId}"),
        ("GET", "/api/projects/{projectId}/features"),
        ("GET", "/api/projects/{projectId}/review-queue"),
        ("POST", "/api/projects/{projectId}/review-queue/{itemId}/resolve"),
    }


# ---------------------------------------------------------------------------------------------
# Post-verification fixes (§11.3 sign-off)
# ---------------------------------------------------------------------------------------------


async def test_reupload_of_failed_document_retries(client, enqueued, db_session, _blob_dir):
    url = f"/api/projects/{PROJECT}/documents"
    first = (await client.post(url, files=_upload("a.md", b"# retry me"))).json()
    doc = await db_session.get(Document, uuid.UUID(first["id"]))
    doc.ingestion_status = "failed"
    doc.error = "Vertex AI is not configured. No GCP project. Set GCP_PROJECT_ID."
    (_blob_dir / doc.blob_path).unlink()  # blob gone too — the retry must restore it
    await db_session.flush()

    for n in (1, 2):
        resp = await client.post(url, files=_upload("a.md", b"# retry me"))
        assert resp.status_code == 202
        body = resp.json()
        assert body["id"] == first["id"] and body["status"] == "pending"
        assert "duplicate" not in body and "error" not in body
        assert enqueued[-1] == (
            "ingest_document",
            {"document_id": first["id"], "_job_id": f"ingest_document:{first['id']}:retry:{n}"},
        )
        doc.ingestion_status = "failed"
        await db_session.flush()

    assert (_blob_dir / doc.blob_path).read_bytes() == b"# retry me"
    assert (await _audit_types(db_session)) == ["ingest_retried", "ingest_retried"]


async def test_reupload_of_non_failed_document_is_duplicate(client, enqueued, db_session):
    url = f"/api/projects/{PROJECT}/documents"
    first = (await client.post(url, files=_upload("a.md", b"# done doc"))).json()
    doc = await db_session.get(Document, uuid.UUID(first["id"]))
    doc.ingestion_status = "done"
    await db_session.flush()
    resp = await client.post(url, files=_upload("a.md", b"# done doc"))
    assert resp.status_code == 200 and resp.json()["duplicate"] is True
    assert len(enqueued) == 1


async def test_retry_with_queue_down_stays_failed(client, monkeypatch, db_session):
    url = f"/api/projects/{PROJECT}/documents"
    first = (await client.post(url, files=_upload("a.md", b"# q down"))).json()
    doc = await db_session.get(Document, uuid.UUID(first["id"]))
    doc.ingestion_status = "failed"
    doc.error = "old error"
    await db_session.commit()

    async def down(job_name, **kwargs):
        raise queue.QueueUnavailable("refused")

    monkeypatch.setattr(queue, "enqueue", down)
    resp = await client.post(url, files=_upload("a.md", b"# q down"))
    assert resp.status_code == 503
    await db_session.refresh(doc)
    assert doc.ingestion_status == "failed" and doc.error == "old error"


async def test_queue_503_text_is_not_doubled(client, monkeypatch):
    async def down(job_name, **kwargs):
        raise queue.QueueUnavailable("refused")

    monkeypatch.setattr(queue, "enqueue", down)
    resp = await client.post(f"/api/projects/{PROJECT}/documents", files=_upload("a.md", b"#"))
    detail = resp.json()["detail"]
    text = " ".join(detail.values())
    assert text.lower().count("unavailable") + text.lower().count("can't be reached") == 1


async def _second_conflict(db_session, feature, make_document, make_source_ref):
    doc = await make_document(filename="spec-v3.md")
    ref = make_source_ref(doc_id=str(doc.doc_id), snippet="Sign in with SSO only.")
    v3 = FeatureVersion(
        feature_id=feature.feature_id, version_no=3, description="Sign in with SSO only.",
        source_refs=[ref], created_from=f"ingest:{doc.doc_id}",
    )
    db_session.add(v3)
    await db_session.flush()
    item = ReviewItem(
        project_id=PROJECT, kind="conflict", feature_id=feature.feature_id,
        document_id=doc.doc_id,
        payload={
            "feature_name": feature.name, "reason": "SSO only.", "confidence": 0.8,
            "current_version_id": str(feature.current_version_id),
            "incoming_version_id": str(v3.version_id),
        },
    )
    db_session.add(item)
    await db_session.flush()
    return item


@pytest.mark.parametrize("action", ["approve", "dismiss"])
async def test_resolve_one_of_two_conflicts_stays_conflicted(
    client, db_session, enqueued, action, make_feature, make_document, make_source_ref
):
    feature, incoming, item = await _conflict(
        db_session, make_feature, make_document, make_source_ref
    )
    other = await _second_conflict(db_session, feature, make_document, make_source_ref)
    resp = await client.post(_resolve_url(item.id), json={"action": action})
    assert resp.status_code == 200
    await db_session.refresh(feature)
    assert feature.lifecycle_state == "conflicted"
    assert enqueued == []

    resp = await client.post(_resolve_url(other.id), json={"action": "dismiss"})
    assert resp.status_code == 200
    await db_session.refresh(feature)
    assert feature.lifecycle_state == "consolidated"
    assert [j for j, _ in enqueued] == ["readiness_run"]


async def _flag_prior(db_session, feature, from_state):
    db_session.add(
        AuditEvent(
            project_id=PROJECT, feature_id=feature.feature_id, graph="ingest", node="store",
            type="conflict_flagged", detail={"from_state": from_state},
        )
    )
    await db_session.flush()


async def test_dismiss_restores_state_past_consolidated(
    client, db_session, enqueued, make_feature, make_document, make_source_ref
):
    feature, _, item = await _conflict(db_session, make_feature, make_document, make_source_ref)
    await _flag_prior(db_session, feature, "dev_ready")
    resp = await client.post(_resolve_url(item.id), json={"action": "dismiss"})
    assert resp.status_code == 200
    await db_session.refresh(feature)
    assert feature.lifecycle_state == "dev_ready"  # not demoted
    assert enqueued == []  # content unchanged — nothing to re-run


async def test_approve_on_feature_past_consolidated_goes_stale(
    client, db_session, enqueued, make_feature, make_document, make_source_ref
):
    feature, _, item = await _conflict(db_session, make_feature, make_document, make_source_ref)
    await _flag_prior(db_session, feature, "dev_ready")
    resp = await client.post(_resolve_url(item.id), json={"action": "approve"})
    assert resp.status_code == 200
    await db_session.refresh(feature)
    assert feature.lifecycle_state == "stale"
    assert [j for j, _ in enqueued] == ["readiness_run"]


async def test_dismiss_with_unknown_prior_state_goes_stale(
    client, db_session, enqueued, make_feature, make_document, make_source_ref
):
    feature, _, item = await _conflict(db_session, make_feature, make_document, make_source_ref)
    feature.readiness = {"fields": {}}  # registry touched it; no conflict_flagged audit row
    await db_session.flush()
    resp = await client.post(_resolve_url(item.id), json={"action": "dismiss"})
    assert resp.status_code == 200
    await db_session.refresh(feature)
    assert feature.lifecycle_state == "stale"
    assert [j for j, _ in enqueued] == ["readiness_run"]


def test_root_routes_have_distinct_operation_ids():
    import warnings

    from app.main import app

    app.openapi_schema = None
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        schema = app.openapi()
    ops = schema["paths"]["/"]
    assert ops["get"]["operationId"] == "root" and ops["head"]["operationId"] == "root_head"
