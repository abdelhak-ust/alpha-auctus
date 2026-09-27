"""consolidate.py — grouping, one merge call per multi-fragment group, contradictions (§5.5)."""

import pytest

from app.ingest.consolidate import consolidate, group_fragments
from app.schemas.ingestion import ConsolidatedFeature
from tests.fixtures.fake_ai import FakeLLM


def _frag(name, desc, start, *, ref=None, status="new", chunk="c1"):
    return {
        "feature_name": name, "description": desc, "status": status,
        "references_feature": ref, "snippet": desc, "confidence": 0.9,
        "source_ref": {"doc_id": "d1", "doc_type": "upload", "chunk_id": chunk,
                       "section": "S", "char_start": start, "char_end": start + len(desc),
                       "snippet": desc},
    }


@pytest.fixture
def fake_llm(monkeypatch):
    llm = FakeLLM()
    monkeypatch.setattr("app.ai.generate_json", llm)
    return llm


def test_grouping_by_name_continuation_and_registry_id():
    reg = "5f0e7c1a-1111-4222-8333-444455556666"
    frags = [
        _frag("Single sign-on", "a", 0),
        _frag("CSV export", "b", 10),
        _frag("SSO for Azure", "c", 20, ref="Single sign-on", status="continuation"),
        _frag("Audit export", "d", 30, ref=reg, status="update"),
        _frag("Export of audit log", "e", 40, ref=reg, status="update"),
    ]
    assert group_fragments(frags) == [[0, 2], [1], [3, 4]]


async def test_single_fragment_groups_need_no_llm_call(fake_llm):
    features = await consolidate([_frag("CSV export", "Admins export CSV.", 0)])
    assert fake_llm.count(ConsolidatedFeature) == 0
    assert features[0]["name"] == "CSV export"
    assert len(features[0]["source_refs"]) == 1


async def test_multi_fragment_group_is_merged_with_all_citations(fake_llm):
    frags = [_frag("Single sign-on", "Users sign in with SSO.", 0),
             _frag("Single sign-on", "SSO supports Azure AD.", 50, chunk="c2"),
             # same span seen again through the chunk overlap → deduplicated
             _frag("Single sign-on", "SSO supports Azure AD.", 50, chunk="c3")]
    [feature] = await consolidate(frags)
    assert fake_llm.count(ConsolidatedFeature) == 1
    assert feature["description"].startswith("Users sign in with SSO.")
    assert [r["char_start"] for r in feature["source_refs"]] == [0, 50]
    assert feature["contradictions"] == [] and "incoming" not in feature


async def test_in_document_contradiction_splits_first_statement_and_incoming(fake_llm):
    frags = [_frag("Session timeout", "Sessions expire after 30 minutes.", 0),
             _frag("Session timeout", "Sessions expire after 8 hours.", 100)]
    [feature] = await consolidate(frags)
    assert feature["contradictions"]
    assert feature["description"] == "Sessions expire after 30 minutes."
    assert [r["char_start"] for r in feature["source_refs"]] == [0]
    assert feature["incoming"]["description"] == "Sessions expire after 8 hours."
    assert [r["char_start"] for r in feature["incoming"]["source_refs"]] == [100]


async def test_fragments_rejected_by_the_merge_are_kept_not_dropped(monkeypatch):
    async def merge(prompt, schema, *, system=None):
        return ConsolidatedFeature(name="SSO", description="SSO.", fragment_indices=[0],
                                   confidence=0.8)

    monkeypatch.setattr("app.ai.generate_json", merge)
    features = await consolidate([_frag("SSO", "SSO login.", 0),
                                  _frag("SSO", "SSO admin console.", 30)])
    assert [f["name"] for f in features] == ["SSO", "SSO"]
    assert features[1]["description"] == "SSO admin console."


async def test_unpaired_contradiction_becomes_a_sweep_flag_not_dropped(monkeypatch):
    async def merge(prompt, schema, *, system=None):
        # The merge keeps only fragment 0 yet reports a contradiction with fragment 1.
        return ConsolidatedFeature(name="Session timeout",
                                   description="Sessions expire after 30 minutes.",
                                   fragment_indices=[0],
                                   contradictions=["expire after 8 hours vs 30 minutes"],
                                   confidence=0.7)

    monkeypatch.setattr("app.ai.generate_json", merge)
    features = await consolidate([
        _frag("Session timeout", "Sessions expire after 30 minutes.", 0),
        _frag("Session timeout", "Sessions expire after 8 hours.", 100),
    ])
    kept = features[0]
    assert "incoming" not in kept
    [flag] = kept["contradiction_flags"]
    assert set(flag) == {"feature_name", "description", "reason", "confidence", "source_ref"}
    assert flag["reason"] == "unpaired_contradiction"
    assert flag["source_ref"]["char_start"] == 100  # cites the contradicting fragment
    assert flag["confidence"] == 0.7
