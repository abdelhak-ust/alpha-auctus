"""match.py — registry retrieval + NEW/UPDATE/CONFLICT/DUPLICATE classification (§6)."""

import pytest

from app import vector
from app.ingest.chunk import ChunkSpec
from app.ingest.match import classify_features, retrieve_for_chunks
from app.schemas.ingestion import ConsolidatedFeature, MatchVerdict
from tests.fixtures.fake_ai import FakeEmbedder, FakeLLM, qdrant_memory, topic_vector  # noqa: F401

# In-memory Qdrant for every test (fixture from tests/fixtures/fake_ai.py).
pytestmark = pytest.mark.usefixtures("qdrant_memory")

PROJECT = "proj-match"


def _feature(name, description):
    return {"key": "g0", "name": name, "description": description,
            "source_refs": [{"doc_id": "d2", "doc_type": "upload", "chunk_id": "c",
                             "section": "S", "char_start": 0, "char_end": 10,
                             "snippet": description}],
            "contradictions": [], "relations": [], "confidence": 0.9, "registry_hint": None}


@pytest.fixture
def fakes(monkeypatch):
    llm, emb = FakeLLM(), FakeEmbedder()
    monkeypatch.setattr("app.ai.generate_json", llm)
    monkeypatch.setattr("app.ai.embed_texts", emb)
    return llm, emb


async def _register(make_feature, name, description):
    feature = await make_feature(project_id=PROJECT, name=name, description=description)
    await vector.upsert_features([{
        "id": str(feature.feature_id), "vector": topic_vector(f"{name}\n{description}"),
        "payload": {"project_id": PROJECT, "feature_id": str(feature.feature_id),
                    "name": name, "lifecycle_state": "consolidated", "source_refs": [],
                    "last_updated": "now"},
    }])
    return feature


async def test_empty_registry_is_new_without_a_classification_call(db_session,
                                                                  fakes):
    llm, emb = fakes
    [result] = await classify_features(db_session, PROJECT,
                                       [_feature("Session timeout", "Sessions expire.")])
    assert result["outcome"] == "new" and result["matched_feature_id"] is None
    assert llm.count(MatchVerdict) == 0
    assert emb.calls == [("RETRIEVAL_QUERY", 1)]


async def test_update_gets_a_separate_merge_call(db_session, make_feature, fakes):
    llm, _ = fakes
    existing = await _register(make_feature, "Audit log export", "Admins export CSV.")
    [result] = await classify_features(
        db_session, PROJECT, [_feature("Audit log export", "CSV export includes IP.")])
    assert result["outcome"] == "update"
    assert result["matched_feature_id"] == str(existing.feature_id)
    assert result["merged_description"] == "Admins export CSV. CSV export includes IP."
    assert llm.count(MatchVerdict) == 1 and llm.count(ConsolidatedFeature) == 1
    assert result["candidates"][0]["feature_id"] == str(existing.feature_id)


async def test_conflict_and_duplicate(db_session, make_feature, fakes):
    await _register(make_feature, "Session timeout", "Sessions expire after 30 minutes.")
    await _register(make_feature, "Single sign-on", "Users sign in with SSO.")
    results = await classify_features(db_session, PROJECT, [
        _feature("Session timeout", "Sessions expire after 8 hours."),
        _feature("Single sign-on", "Users sign in with SSO."),
    ])
    assert [r["outcome"] for r in results] == ["conflict", "duplicate"]
    assert "merged_description" not in results[0]


async def test_other_projects_are_never_candidates(db_session, make_feature,
                                                   fakes):
    feature = await make_feature(project_id="someone-else", name="Session timeout")
    await vector.upsert_features([{
        "id": str(feature.feature_id), "vector": topic_vector("session"),
        "payload": {"project_id": "someone-else", "feature_id": str(feature.feature_id)}}])
    [result] = await classify_features(db_session, PROJECT,
                                       [_feature("Session timeout", "Sessions expire.")])
    assert result["outcome"] == "new"


async def test_low_confidence_verdict_goes_to_review_not_applied(db_session, make_feature, fakes):
    llm, _ = fakes
    llm.match_confidence = 0.3
    await _register(make_feature, "Audit log export", "Admins export CSV.")
    [result] = await classify_features(
        db_session, PROJECT, [_feature("Audit log export", "CSV export includes IP.")])
    assert result["outcome"] == "review"
    assert llm.count(ConsolidatedFeature) == 0  # nothing merged


async def test_retrieve_for_chunks_uses_query_embeddings(db_session, make_feature, fakes):
    _, emb = fakes
    existing = await _register(make_feature, "Session timeout", "Sessions expire.")
    chunks = [ChunkSpec(chunk_id="c0", ordinal=0, section_path=[], char_start=0,
                        char_end=20, text="Sessions expire soon"),
              ChunkSpec(chunk_id="c1", ordinal=1, section_path=[], char_start=20,
                        char_end=40, text="Unrelated paragraph")]
    out = await retrieve_for_chunks(PROJECT, chunks)
    assert [c["feature_id"] for c in out[0]] == [str(existing.feature_id)]
    assert out[1] == []
    assert emb.calls == [("RETRIEVAL_QUERY", 2)]  # one batched call
