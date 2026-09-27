"""Chunking: documents over extract_chunk_chars split on headings with overlap."""

from app.ingest.split import split_markdown


def _big_doc(sections: int = 6, body_chars: int = 12_000) -> str:
    parts = []
    for i in range(sections):
        parts.append(f"## Section {i}\n\n{'word ' * (body_chars // 5)}")
    return "\n".join(parts)


def test_small_document_is_one_chunk():
    text = "# Title\n\nA short spec."
    chunks = split_markdown(text, max_chars=40_000, overlap_chars=1_500)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].char_start == 0 and chunks[0].char_end == len(text)


def test_large_document_splits_on_headings_with_overlap():
    text = _big_doc()
    assert len(text) > 40_000
    chunks = split_markdown(text, max_chars=40_000, overlap_chars=1_500)
    assert len(chunks) > 1
    for c in chunks:
        assert c.text == text[c.char_start : c.char_end]
        assert len(c.text) <= 40_000 + 1_500
    for prev, cur in zip(chunks, chunks[1:], strict=False):
        assert cur.char_start < prev.char_end
        assert cur.char_start == 0 or text[cur.char_start - 1].isspace()


def test_empty_is_no_chunks():
    assert split_markdown("") == []
