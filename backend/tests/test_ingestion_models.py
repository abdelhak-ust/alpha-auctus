"""Ingestion data layer (plans/ingestion.md §4 / §11.1): table constraints and the camelCase
API schemas that must match client/src/types.ts."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import AuditEvent, Chunk, FeatureRelation, FeatureVersion, ReviewItem
from app.schemas.ingestion import (
    Candidate,
    ErrorDetail,
    IngestDocument,
    IngestItem,
    MatchVerdict,
    RegistryFeature,
    ResolveRequest,
    SourceRef,
    VerdictDetail,
)

# --- constraints ------------------------------------------------------------------------------


async def test_content_hash_unique_per_project(db_session, make_document):
    await make_document(project_id="p1", content_hash="a" * 64)
    # Same bytes in another project is a different document.
    await make_document(project_id="p2", content_hash="a" * 64)
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await make_document(project_id="p1", content_hash="a" * 64)


async def test_version_no_unique_per_feature(db_session, make_feature):
    feature = await make_feature()
    other = await make_feature(name="Other")
    # version 1 exists for both features; version 2 on one is fine.
    db_session.add(
        FeatureVersion(
            feature_id=feature.feature_id,
            version_no=2,
            description="v2",
            source_refs=[],
            created_from="manual:u1",
        )
    )
    await db_session.flush()
    assert other.current_version_id is not None
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                FeatureVersion(
                    feature_id=feature.feature_id,
                    version_no=2,
                    description="dup",
                    source_refs=[],
                    created_from="manual:u1",
                )
            )
            await db_session.flush()


async def test_lifecycle_state_is_checked(db_session, make_feature):
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await make_feature(lifecycle_state="not_a_state")


async def test_review_item_kind_and_status_are_checked(db_session, make_document, make_feature):
    doc = await make_document()
    feature = await make_feature()
    item = ReviewItem(
        project_id="proj-test",
        kind="conflict",
        feature_id=feature.feature_id,
        document_id=doc.doc_id,
        payload={"current": {}, "proposed": {}},
    )
    db_session.add(item)
    await db_session.flush()
    assert item.status == "open"
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(ReviewItem(project_id="proj-test", kind="bogus", document_id=doc.doc_id))
            await db_session.flush()


async def test_rows_round_trip(db_session, make_document, make_feature, make_source_ref):
    doc = await make_document()
    db_session.add(
        Chunk(
            doc_id=doc.doc_id,
            project_id=doc.project_id,
            ordinal=0,
            section_path="1 > 1.1",
            page_start=1,
            page_end=1,
            char_start=0,
            char_end=10,
            text="0123456789",
        )
    )
    ref = make_source_ref(doc_id=str(doc.doc_id))
    a = await make_feature(source_refs=[ref])
    b = await make_feature(name="B")
    db_session.add(
        FeatureRelation(
            feature_id_a=a.feature_id, feature_id_b=b.feature_id, relation_type="depends_on"
        )
    )
    db_session.add(
        AuditEvent(
            project_id="proj-test",
            feature_id=a.feature_id,
            graph="ingest",
            node="store",
            type="version_created",
            detail={"version_no": 1},
        )
    )
    await db_session.commit()  # releases the savepoint only; the fixture still rolls back

    version = await db_session.scalar(
        select(FeatureVersion).where(FeatureVersion.version_id == a.current_version_id)
    )
    assert version is not None
    assert version.source_refs == [ref]
    assert SourceRef.model_validate(version.source_refs[0]).char_end == ref["char_end"]


# --- schemas: JSON keys must equal the TS interfaces -----------------------------------------


def _keys(model) -> set[str]:
    return set(model.model_dump(by_alias=True).keys())


def test_ingest_document_json_matches_ts():
    doc = IngestDocument(
        id=str(uuid.uuid4()),
        project_id="p",
        filename="a.pdf",
        status="done",
        error="x",
        duplicate=True,
        feature_count=3,
        uploaded_at=datetime.now(UTC),
    )
    assert _keys(doc) == {
        "id",
        "projectId",
        "filename",
        "status",
        "error",
        "duplicate",
        "featureCount",
        "uploadedAt",
    }
    # Optional TS fields are omitted (not null) when unset + exclude_none.
    bare = IngestDocument(
        id="d",
        project_id="p",
        filename="a.pdf",
        status="pending",
        feature_count=0,
        uploaded_at=datetime.now(UTC),
    )
    assert "error" not in bare.model_dump(by_alias=True, exclude_none=True)


def test_registry_feature_and_source_ref_json_match_ts(make_source_ref):
    feature = RegistryFeature(
        id="f",
        project_id="p",
        name="n",
        description="d",
        version_no=1,
        lifecycle_state="consolidated",
        source_refs=[SourceRef.model_validate(make_source_ref())],
        updated_at=datetime.now(UTC),
    )
    body = feature.model_dump(by_alias=True, mode="json")
    assert set(body) == {
        "id",
        "projectId",
        "name",
        "description",
        "versionNo",
        "lifecycleState",
        "sourceRefs",
        "updatedAt",
    }
    assert set(body["sourceRefs"][0]) == {
        "docId",
        "docType",
        "chunkId",
        "section",
        "charStart",
        "charEnd",
        "snippet",
    }


def test_ingest_item_json_matches_existing_ts_type():
    item = IngestItem(
        id="r1",
        title="t",
        description="d",
        area="auth",
        priority="P2",
        source_id="doc1",
        source_snippet="…",
        verdict=VerdictDetail(
            type="conflict",
            confidence=0.7,
            message="m",
            candidates=[Candidate(id="f1", type="item", title="t", reason="r", confidence=0.7)],
            citation={"id": "doc1", "type": "source", "title": "spec.pdf", "snippet": "…"},
        ),
    )
    body = item.model_dump(by_alias=True)
    assert set(body) == {
        "id",
        "title",
        "description",
        "area",
        "priority",
        "sourceId",
        "sourceSnippet",
        "verdict",
    }
    assert set(body["verdict"]) == {"type", "confidence", "message", "candidates", "citation"}
    assert set(body["verdict"]["candidates"][0]) == {"id", "type", "title", "reason", "confidence"}


def test_request_and_error_shapes():
    assert ResolveRequest.model_validate({"action": "approve"}).action == "approve"
    with pytest.raises(ValueError):
        ResolveRequest.model_validate({"action": "merge"})
    assert _keys(ErrorDetail(problem="p", cause="c", fix="f")) == {"problem", "cause", "fix"}


def test_match_verdict_outcomes():
    v = MatchVerdict(outcome="duplicate", matched_feature_id="f1", confidence=0.9)
    assert v.candidates == []
    with pytest.raises(ValueError):
        MatchVerdict(outcome="merge", confidence=0.5)

