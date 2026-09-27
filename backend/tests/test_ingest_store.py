"""store.py — outcomes → Postgres rows, review payloads (§11.3), Qdrant upserts."""

import uuid

import pytest
from sqlalchemy import select

from app import vector
from app.ingest.store import apply_outcomes, reindex_feature, upsert_vectors
from app.models import AuditEvent, Feature, FeatureVersion, ReviewItem
from tests.fixtures.fake_ai import FakeEmbedder, qdrant_memory  # noqa: F401

# In-memory Qdrant for every test (fixture from tests/fixtures/fake_ai.py).
pytestmark = pytest.mark.usefixtures("qdrant_memory")

PROJECT = "proj-store"
CONFLICT_KEYS = {"feature_name", "reason", "confidence", "current_version_id",
                 "incoming_version_id"}
SWEEP_KEYS = {"feature_name", "description", "reason", "confidence", "source_ref"}


@pytest.fixture
def emb(monkeypatch):
    fake = FakeEmbedder()
    monkeypatch.setattr("app.ai.embed_texts", fake)
    return fake


def _ref(doc_id, text="Sessions expire after 8 hours.", start=10, chunk=None):
    return {"doc_id": doc_id, "doc_type": "upload", "chunk_id": chunk or str(uuid.uuid4()),
            "section": "Sessions", "char_start": start, "char_end": start + len(text),
            "snippet": text}


def _item(outcome, name, description, doc_id, **extra):
    return {"key": f"g{abs(hash(name)) % 1000}", "name": name, "description": description,
            "source_refs": [_ref(doc_id, description)], "contradictions": [], "relations": [],
            "confidence": 0.9, "registry_hint": None, "outcome": outcome,
            "matched_feature_id": None, "candidates": [], "match_confidence": 0.9, **extra}


async def _versions(session, fid):
    rows = await session.scalars(select(FeatureVersion).where(FeatureVersion.feature_id == fid)
                                 .order_by(FeatureVersion.version_no))
    return list(rows)


async def test_new_feature_and_in_document_contradiction(db_session, make_document):
    doc = await make_document(project_id=PROJECT)
    did = str(doc.doc_id)
    contradiction = _item("new", "Session timeout", "Sessions expire after 30 minutes.", did,
                          contradictions=["30 min vs 8 h"],
                          incoming={"description": "Sessions expire after 8 hours.",
                                    "source_refs": [_ref(did, start=200)]})
    touched = await apply_outcomes(db_session, project_id=PROJECT, document_id=did,
                                   classified=[_item("new", "CSV export", "Admins export.", did),
                                               contradiction],
                                   sweep_flags=[])
    assert [t["lifecycle_state"] for t in touched] == ["consolidated", "conflicted"]

    csv = await db_session.get(Feature, touched[0]["feature_id"])
    [v1] = await _versions(db_session, csv.feature_id)
    assert csv.current_version_id == v1.version_id and v1.version_no == 1
    assert v1.created_from == f"ingest:{did}" and len(v1.source_refs) == 1

    session_f = await db_session.get(Feature, touched[1]["feature_id"])
    v1, v2 = await _versions(db_session, session_f.feature_id)
    assert session_f.current_version_id == v1.version_id  # first statement stays current
    assert v2.description == "Sessions expire after 8 hours."
    item = await db_session.scalar(select(ReviewItem).where(
        ReviewItem.feature_id == session_f.feature_id))
    assert item.kind == "conflict" and set(item.payload) == CONFLICT_KEYS
    assert item.payload["reason"] == "in_document_contradiction"
    assert item.payload["current_version_id"] == str(v1.version_id)
    assert item.payload["incoming_version_id"] == str(v2.version_id)


async def test_update_past_consolidated_goes_stale(db_session, make_document, make_feature):
    doc = await make_document(project_id=PROJECT)
    did = str(doc.doc_id)
    feature = await make_feature(project_id=PROJECT, name="Audit log export",
                                 lifecycle_state="dev_ready")
    item = _item("update", "Audit log export", "Includes IP.", did,
                 matched_feature_id=str(feature.feature_id),
                 merged_description="Admins export CSV. Includes IP.")
    await apply_outcomes(db_session, project_id=PROJECT, document_id=did, classified=[item],
                         sweep_flags=[])
    v1, v2 = await _versions(db_session, feature.feature_id)
    assert feature.lifecycle_state == "stale"
    assert feature.current_version_id == v2.version_id
    assert v2.description == "Admins export CSV. Includes IP."
    assert len(v2.source_refs) == 2  # previous refs + this document's


async def test_registry_conflict_keeps_both_versions(db_session, make_document, make_feature, emb):
    doc = await make_document(project_id=PROJECT)
    did = str(doc.doc_id)
    feature = await make_feature(project_id=PROJECT, name="Session timeout",
                                 description="Sessions expire after 30 minutes.")
    current_id = feature.current_version_id
    item = _item("conflict", "Session timeout", "Sessions expire after 8 hours.", did,
                 matched_feature_id=str(feature.feature_id))
    touched = await apply_outcomes(db_session, project_id=PROJECT, document_id=did,
                                   classified=[item], sweep_flags=[])
    v1, v2 = await _versions(db_session, feature.feature_id)
    assert feature.lifecycle_state == "conflicted"
    assert feature.current_version_id == current_id == v1.version_id  # not auto-resolved
    assert v2.version_no == 2 and v2.description == "Sessions expire after 8 hours."
    review = await db_session.scalar(select(ReviewItem).where(ReviewItem.kind == "conflict",
                                                              ReviewItem.document_id == doc.doc_id))
    assert set(review.payload) == CONFLICT_KEYS
    assert review.payload["incoming_version_id"] == str(v2.version_id)

    await upsert_vectors(db_session, project_id=PROJECT, document_id=did, chunks=[],
                         touched=touched)
    [point] = (await vector.get_client().retrieve("features", [str(feature.feature_id)],
                                                   with_payload=True))
    assert point.payload["lifecycle_state"] == "conflicted"
    assert point.payload["source_refs"] == v1.source_refs  # the current version, not incoming


async def test_duplicate_appends_provenance_only(db_session, make_document, make_feature):
    doc = await make_document(project_id=PROJECT)
    did = str(doc.doc_id)
    feature = await make_feature(project_id=PROJECT, name="Single sign-on")
    item = _item("duplicate", "Single sign-on", "Users sign in with SSO.", did,
                 matched_feature_id=str(feature.feature_id))
    await apply_outcomes(db_session, project_id=PROJECT, document_id=did, classified=[item],
                         sweep_flags=[])
    [v1] = await _versions(db_session, feature.feature_id)
    assert len(v1.source_refs) == 2 and v1.source_refs[-1]["doc_id"] == did
    assert feature.lifecycle_state == "consolidated"
    audit = await db_session.scalar(select(AuditEvent).where(
        AuditEvent.feature_id == feature.feature_id, AuditEvent.type == "provenance_append"))
    assert audit is not None and audit.graph == "ingest"


async def test_low_confidence_and_sweep_flags(db_session, make_document):
    doc = await make_document(project_id=PROJECT)
    did = str(doc.doc_id)
    flag = {"feature_name": "Mobile app", "description": "", "reason": "uncovered_mention",
            "confidence": 0.4, "source_ref": _ref(did, "We might offer a mobile app.")}
    await apply_outcomes(db_session, project_id=PROJECT, document_id=did,
                         classified=[_item("review", "Audit log export", "Maybe IP.", did,
                                           match_confidence=0.3)],
                         sweep_flags=[flag])
    items = list(await db_session.scalars(select(ReviewItem).where(
        ReviewItem.document_id == doc.doc_id).order_by(ReviewItem.created_at)))
    assert [i.kind for i in items] == ["sweep_flag", "sweep_flag"]
    assert all(set(i.payload) == SWEEP_KEYS for i in items)
    assert {i.payload["reason"] for i in items} == {"low_confidence_match", "uncovered_mention"}
    assert await db_session.scalar(select(Feature).where(Feature.project_id == PROJECT)) is None


async def test_reindex_feature_upserts_current_description(db_session, make_feature, emb):
    feature = await make_feature(project_id=PROJECT, name="Session timeout",
                                 description="Sessions expire.")
    await reindex_feature(db_session, str(feature.feature_id))
    hits = await vector.search_features(PROJECT, (await emb(["session"],
                                                            task_type="RETRIEVAL_QUERY"))[0])
    assert [h.feature_id for h in hits] == [str(feature.feature_id)]
    assert emb.calls[0] == ("RETRIEVAL_DOCUMENT", 1)
