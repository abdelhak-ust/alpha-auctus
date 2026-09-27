"""cite.py — cite or stay silent: only verbatim, locatable quotes become source_refs (§11.3)."""

from app.ingest.chunk import ChunkSpec
from app.ingest.cite import (
    chunk_fallback_ref,
    locate_snippet,
    make_source_ref,
    names_match,
)

TEXT = "Intro.\n\n1.2 Session timeout\n\nSessions expire after 30 minutes of inactivity. Bye."
CHUNK = ChunkSpec(chunk_id="c1", ordinal=0, section_path=["Spec", "1.2 Session timeout"],
                  char_start=100, char_end=100 + len(TEXT), text=TEXT)


def test_exact_quote_gives_document_level_offsets():
    quote = "Sessions expire after 30 minutes of inactivity."
    ref = make_source_ref(CHUNK, f'  "{quote}" ', document_id="d1", doc_type="upload",
                          confidence=0.8)
    assert ref is not None
    doc_text = " " * 100 + TEXT  # the chunk sits at offset 100 of the document
    assert doc_text[ref["char_start"]:ref["char_end"]] == ref["snippet"] == quote
    assert ref["section"] == "1.2 Session timeout"
    assert ref["chunk_id"] == "c1" and ref["confidence"] == 0.8


def test_paraphrase_or_hallucination_is_not_located():
    assert locate_snippet(TEXT, "Sessions expire after 8 hours of inactivity.") is None
    assert locate_snippet(TEXT, "Sessions  expire after 30 minutes") is None  # not verbatim
    assert locate_snippet(TEXT, "Bye.") is None  # too short to be evidence


def test_chunk_fallback_ref_is_marked_unlocated():
    ref = chunk_fallback_ref(CHUNK, document_id="d1", doc_type="upload")
    assert ref["located"] is False
    assert ref["snippet"] == TEXT[:300]
    assert ref["char_start"] == 100


def test_names_match():
    assert names_match("Audit-log export", "audit log export")
    assert names_match("CSV audit log export", "Audit log export")
    assert not names_match("Session timeout", "Single sign-on")
