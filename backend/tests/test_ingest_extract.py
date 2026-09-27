"""extract.py — rolling-state extraction; model offsets ignored; unlocated → separate (§5.4)."""

import pytest

from app.ingest.chunk import chunk_document
from app.ingest.extract import extract_chunk, update_rolling_summary
from app.ingest.parse import parse_document
from app.schemas.ingestion import ExtractionResult
from tests.fixtures.fake_ai import HALLUCINATED_QUOTE, FakeLLM

DOC_ID = "7d0c6f0e-0000-4000-8000-000000000001"


@pytest.fixture
def fake_llm(monkeypatch):
    llm = FakeLLM()
    monkeypatch.setattr("app.ai.generate_json", llm)
    return llm


def _spec_a():
    from pathlib import Path

    raw = (Path(__file__).parent / "fixtures" / "spec_a.md").read_bytes()
    parsed = parse_document(raw, "spec_a.md")
    return parsed, chunk_document(parsed, document_id=DOC_ID)


async def test_fragments_are_cited_from_the_chunk_not_the_model(fake_llm):
    parsed, chunks = _spec_a()
    located, unlocated = await extract_chunk(
        chunks[0], document_id=DOC_ID, doc_type="upload", rolling_summary=[],
        registry_candidates=[],
    )
    assert {f["feature_name"] for f in located} == {
        "Single sign-on", "Session timeout", "Audit log export"}
    for f in located:
        ref = f["source_ref"]
        assert parsed.text[ref["char_start"]:ref["char_end"]] == ref["snippet"] == f["snippet"]
        assert ref["char_end"] - ref["char_start"] > 5  # the model's (0, 5) was discarded
        assert ref["doc_id"] == DOC_ID and ref["chunk_id"] == chunks[0].chunk_id
    assert [f["snippet"] for f in unlocated] == [HALLUCINATED_QUOTE]
    assert "source_ref" not in unlocated[0]


async def test_rolling_summary_and_registry_candidates_reach_the_prompt(monkeypatch):
    prompts = []

    async def capture(prompt, schema, *, system=None):
        prompts.append(prompt)
        return ExtractionResult()

    monkeypatch.setattr("app.ai.generate_json", capture)
    _, chunks = _spec_a()
    await extract_chunk(
        chunks[0], document_id=DOC_ID, doc_type="upload",
        rolling_summary=[{"name": "Dark mode", "summary": "Toggle theme"}],
        registry_candidates=[{"feature_id": "f-123", "name": "Theme switcher"}],
    )
    assert "Dark mode" in prompts[0] and "Toggle theme" in prompts[0]
    assert "f-123" in prompts[0] and "Theme switcher" in prompts[0]


def test_update_rolling_summary_is_compact_and_deduplicated():
    rolling = update_rolling_summary([], [
        {"feature_name": "Single sign-on", "description": "Users use SSO. More detail here."},
        {"feature_name": "single sign on", "description": "dup",
         "references_feature": "Single sign-on"},
        {"feature_name": "CSV export", "description": "x" * 500},
    ])
    assert [r["name"] for r in rolling] == ["Single sign-on", "CSV export"]
    assert rolling[0]["summary"] == "Users use SSO"
    assert len(rolling[1]["summary"]) <= 140
