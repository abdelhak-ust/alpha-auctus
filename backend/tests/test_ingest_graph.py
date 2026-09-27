"""End-to-end `ingest` graph (plans/ingestion.md §5–§7, agent done-criteria).

doc A (spec_a.md) → 3 features `consolidated` with char-offset citations; doc B (spec_b.md,
overlapping) → one UPDATE (new version), one DUPLICATE (no version), one CONFLICT (feature
`conflicted` + review item), and `readiness_run` enqueued only for non-conflicted features.
AI, queue and Qdrant are faked (tests/fixtures/fake_ai.py); Postgres is the real test DB.
"""

import shutil
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select

from app import vector
from app.config import get_settings
from app.ingest.graph import build_ingest_graph, thread_config
from app.ingest.jobs import ingest_document, run_ingest
from app.ingest.parse import parse_document
from app.models import AuditEvent, Chunk, Document, Feature, FeatureVersion, ReviewItem
from app.schemas.ingestion import ExtractionResult
from tests.fixtures.fake_ai import (  # noqa: F401
    HALLUCINATED_QUOTE,
    FakeEmbedder,
    FakeLLM,
    FakeQueue,
    qdrant_memory,
    session_factory_for,
)

# In-memory Qdrant for every test (fixture from tests/fixtures/fake_ai.py).
pytestmark = pytest.mark.usefixtures("qdrant_memory")

FIXTURES = Path(__file__).parent / "fixtures"
PROJECT = "proj-e2e"
NODES = {"prepare", "parse", "chunk", "retrieve", "extract", "consolidate", "sweep", "match",
         "store", "handoff"}


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    llm, emb, queue = FakeLLM(), FakeEmbedder(), FakeQueue()
    monkeypatch.setattr("app.ai.generate_json", llm)
    monkeypatch.setattr("app.ai.embed_texts", emb)
    monkeypatch.setattr("app.queue.enqueue", queue)
    monkeypatch.setattr(get_settings(), "blob_dir", str(tmp_path))
    return llm, emb, queue


@pytest.fixture
def upload(make_document, tmp_path):
    async def _upload(name: str) -> Document:
        blob = f"{PROJECT}/{name}"
        (tmp_path / PROJECT).mkdir(exist_ok=True)
        shutil.copy(FIXTURES / name, tmp_path / blob)
        return await make_document(project_id=PROJECT, filename=name, blob_path=blob)

    return _upload


async def _run(db_session, doc: Document) -> dict:
    return await run_ingest(str(doc.doc_id), checkpointer=InMemorySaver(),
                            session_factory=session_factory_for(db_session))


async def _features(db_session) -> dict[str, Feature]:
    rows = await db_session.scalars(select(Feature).where(Feature.project_id == PROJECT))
    return {f.name: f for f in rows}


async def _versions(db_session, feature: Feature) -> list[FeatureVersion]:
    rows = await db_session.scalars(
        select(FeatureVersion).where(FeatureVersion.feature_id == feature.feature_id)
        .order_by(FeatureVersion.version_no))
    return list(rows)


async def test_doc_a_then_overlapping_doc_b(db_session, upload, fakes):
    llm, emb, queue = fakes

    # ---- doc A: initial ingestion ------------------------------------------------------
    doc_a = await upload("spec_a.md")
    state = await _run(db_session, doc_a)
    assert doc_a.ingestion_status == "done" and doc_a.ingested_at is not None
    assert doc_a.error is None

    features = await _features(db_session)
    assert set(features) == {"Single sign-on", "Session timeout", "Audit log export"}
    assert {f.lifecycle_state for f in features.values()} == {"consolidated"}

    parsed = parse_document((FIXTURES / "spec_a.md").read_bytes(), "spec_a.md")
    for feature in features.values():
        [v1] = await _versions(db_session, feature)
        assert v1.created_from == f"ingest:{doc_a.doc_id}"
        assert v1.source_refs, "cite or stay silent: every version has a source_ref"
        for ref in v1.source_refs:
            assert parsed.text[ref["char_start"]:ref["char_end"]] == ref["snippet"]
            assert ref["doc_id"] == str(doc_a.doc_id) and ref["section"]
    [sso_v1] = await _versions(db_session, features["Single sign-on"])
    assert len(sso_v1.source_refs) == 2  # Okta + Azure AD sections consolidated into one

    # the hallucinated quote never became a feature — it is a sweep flag
    flags = list(await db_session.scalars(select(ReviewItem).where(
        ReviewItem.document_id == doc_a.doc_id)))
    assert [(f.kind, f.payload["reason"]) for f in flags] == [
        ("sweep_flag", "no_locatable_source")]
    assert flags[0].payload["source_ref"]["located"] is False
    assert HALLUCINATED_QUOTE not in str([v.source_refs for v in [sso_v1]])

    assert sorted(queue.readiness_feature_ids()) == sorted(
        str(f.feature_id) for f in features.values())
    assert all(kw["project_id"] == PROJECT for _, kw in queue.calls)
    assert {kw["_job_id"] for _, kw in queue.calls} == {
        f"readiness_run:{f.feature_id}:v1" for f in features.values()}
    assert state["handed_off"] and len(state["handed_off"]) == 3

    chunk_rows = list(await db_session.scalars(select(Chunk).where(
        Chunk.doc_id == doc_a.doc_id)))
    assert chunk_rows and all(c.text == parsed.text[c.char_start:c.char_end]
                              for c in chunk_rows)
    sso_chunks = await vector.get_chunks(PROJECT,
                                         feature_id=str(features["Single sign-on"].feature_id))
    assert [c["doc_id"] for c in sso_chunks] == [str(doc_a.doc_id)]
    assert {t for t, _ in emb.calls} == {"RETRIEVAL_QUERY", "RETRIEVAL_DOCUMENT"}

    audited = set(await db_session.scalars(select(AuditEvent.node).where(
        AuditEvent.project_id == PROJECT, AuditEvent.graph == "ingest")))
    assert NODES <= audited

    # ---- doc B: incremental ingestion ----------------------------------------------------
    queue.calls.clear()
    doc_b = await upload("spec_b.md")
    await _run(db_session, doc_b)
    assert doc_b.ingestion_status == "done"

    features = await _features(db_session)
    assert set(features) == {"Single sign-on", "Session timeout", "Audit log export"}

    export = features["Audit log export"]  # UPDATE → new current version
    v1, v2 = await _versions(db_session, export)
    assert export.current_version_id == v2.version_id and export.lifecycle_state == "consolidated"
    assert "IP address" in v2.description or "IP" in v2.description
    assert {r["doc_id"] for r in v2.source_refs} == {str(doc_a.doc_id), str(doc_b.doc_id)}

    sso = features["Single sign-on"]  # DUPLICATE → no new version, provenance appended
    [sso_v1] = await _versions(db_session, sso)
    assert str(doc_b.doc_id) in {r["doc_id"] for r in sso_v1.source_refs}
    assert await db_session.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.feature_id == sso.feature_id, AuditEvent.type == "provenance_append")) == 1

    timeout = features["Session timeout"]  # CONFLICT → both versions, blocked, review item
    t1, t2 = await _versions(db_session, timeout)
    assert timeout.lifecycle_state == "conflicted"
    assert timeout.current_version_id == t1.version_id
    assert "8 hours" in t2.description
    conflict = await db_session.scalar(select(ReviewItem).where(
        ReviewItem.kind == "conflict", ReviewItem.feature_id == timeout.feature_id))
    assert conflict.status == "open"
    assert conflict.payload["current_version_id"] == str(t1.version_id)
    assert conflict.payload["incoming_version_id"] == str(t2.version_id)

    mobile = await db_session.scalar(select(ReviewItem).where(
        ReviewItem.document_id == doc_b.doc_id, ReviewItem.kind == "sweep_flag"))
    assert mobile.payload["feature_name"] == "Mobile app"
    assert mobile.payload["source_ref"]["snippet"] == "We might offer a mobile app someday."

    # hand-off: only the non-conflicted, changed feature
    assert queue.readiness_feature_ids() == [str(export.feature_id)]
    assert queue.calls[0][1]["_job_id"] == f"readiness_run:{export.feature_id}:v2"


async def test_rerun_is_idempotent(db_session, upload, fakes):
    llm, _, queue = fakes
    doc = await upload("spec_a.md")
    await _run(db_session, doc)
    before = (await db_session.scalar(select(func.count()).select_from(FeatureVersion)),
              await db_session.scalar(select(func.count()).select_from(Chunk)))
    calls = len(llm.calls)

    await _run(db_session, doc)  # already done → no-op
    assert len(llm.calls) == calls
    assert (await db_session.scalar(select(func.count()).select_from(FeatureVersion)),
            await db_session.scalar(select(func.count()).select_from(Chunk))) == before

    # crash between store and hand-off: only the hand-off is redone
    doc.ingestion_status = "failed"
    await db_session.flush()
    queue.calls.clear()
    await _run(db_session, doc)
    assert len(llm.calls) == calls
    assert doc.ingestion_status == "done" and len(queue.readiness_feature_ids()) == 3


async def test_vertex_not_configured_fails_with_problem_cause_fix(db_session, upload,
                                                                  monkeypatch, tmp_path):
    from app import ai

    async def unconfigured(*args, **kwargs):
        raise ai.VertexNotConfigured()

    async def memory_checkpointer():
        return InMemorySaver()

    monkeypatch.setattr("app.ai.generate_json", unconfigured)
    monkeypatch.setattr("app.ai.embed_texts", unconfigured)
    monkeypatch.setattr("app.graph.get_checkpointer", memory_checkpointer)
    monkeypatch.setattr(get_settings(), "blob_dir", str(tmp_path))
    doc = await upload("spec_a.md")

    await ingest_document({}, str(doc.doc_id), session_factory=session_factory_for(db_session))

    assert doc.ingestion_status == "failed"
    assert "couldn't be analysed" in doc.error and "Vertex" in doc.error
    assert "retry the upload" in doc.error
    assert await db_session.scalar(select(func.count()).select_from(Feature).where(
        Feature.project_id == PROJECT)) == 0


async def test_failed_run_resumes_from_checkpoint(db_session, upload, fakes):
    llm, _, _ = fakes
    doc = await upload("spec_a.md")
    saver = InMemorySaver()
    factory = session_factory_for(db_session)
    original = llm._sweep
    state = {"fail": True}

    def flaky_sweep(prompt):
        if state["fail"]:
            raise RuntimeError("Vertex 503")
        return original(prompt)

    llm._sweep = flaky_sweep
    with pytest.raises(RuntimeError):
        await run_ingest(str(doc.doc_id), checkpointer=saver, session_factory=factory)
    assert doc.ingestion_status == "extracted"
    graph = build_ingest_graph(saver, session_factory=factory)
    assert (await graph.aget_state(thread_config(str(doc.doc_id)))).next == ("sweep",)

    extractions = llm.count(ExtractionResult)
    state["fail"] = False
    await run_ingest(str(doc.doc_id), checkpointer=saver, session_factory=factory)
    assert doc.ingestion_status == "done"
    assert llm.count(ExtractionResult) == extractions  # resumed at sweep, no re-extraction


async def test_unpaired_contradiction_reaches_the_review_queue(db_session, upload, fakes):
    llm, _, _ = fakes
    original = llm._consolidate

    def keep_first_only(prompt):
        merged = original(prompt)
        return merged.model_copy(update={"fragment_indices": [0],
                                         "contradictions": ["Azure AD vs Okta only"]})

    llm._consolidate = keep_first_only
    doc = await upload("spec_a.md")
    await _run(db_session, doc)
    flag = await db_session.scalar(select(ReviewItem).where(
        ReviewItem.document_id == doc.doc_id,
        ReviewItem.payload["reason"].astext == "unpaired_contradiction"))
    assert flag is not None and flag.kind == "sweep_flag"
    assert "Azure AD" in flag.payload["source_ref"]["snippet"]
