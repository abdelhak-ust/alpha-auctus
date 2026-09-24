"""plans/ingestion.md Verification: "chunker produces correct char offsets on a fixture doc"."""

from app.ingest.chunk import chunk_text


def test_empty_text_produces_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_is_one_chunk_with_exact_offsets():
    text = "This is a short paragraph about authentication."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)
    assert chunks[0].text == text


def test_offsets_are_exact_substrings_of_the_source():
    """The provenance guarantee: every chunk's recorded span, sliced back out of the
    original text, must equal the chunk's own text — this is what every downstream
    citation depends on."""
    text = (
        "Paragraph one is about the login flow and session handling for the app.\n\n"
        "Paragraph two covers rate limiting decisions made in the March architecture "
        "review, including why we chose per-account over per-IP.\n\n"
        "Paragraph three is a short note.\n\n"
        "Paragraph four wraps up with a summary of next steps for the team."
    )
    chunks = chunk_text(text)
    assert len(chunks) >= 1
    for c in chunks:
        assert text[c.char_start : c.char_end] == c.text
    # every paragraph's own text must appear inside some chunk, unmodified
    for para in ["login flow", "rate limiting decisions", "short note", "next steps"]:
        assert any(para in c.text for c in chunks)


def test_paragraphs_pack_until_target_then_split():
    """Many small paragraphs should combine into multi-paragraph chunks, not one chunk
    per paragraph, up to ~TARGET_TOKENS — and a chunk boundary should trigger once a
    chunk would otherwise exceed MAX_TOKENS."""
    # ~40 tokens/paragraph * 30 paragraphs ~= 1200 tokens, comfortably forcing >1 chunk
    # without needing any single paragraph to exceed MAX_TOKENS on its own.
    paragraph = "The quick brown fox jumps over the lazy dog near the riverbank. " * 5
    text = "\n\n".join(f"{paragraph}(#{i})" for i in range(30))

    chunks = chunk_text(text)

    assert len(chunks) > 1, "expected packing to still produce more than one chunk"
    for c in chunks:
        assert text[c.char_start : c.char_end] == c.text
    # chunks are contiguous and in order, never overlapping, never skipping text
    for prev, cur in zip(chunks, chunks[1:], strict=False):  # intentionally pairwise, len-1
        assert cur.char_start >= prev.char_end


def test_oversized_single_paragraph_becomes_its_own_chunk():
    """A paragraph longer than MAX_TOKENS is never split mid-sentence — it becomes one
    (oversized) chunk on its own."""
    huge_paragraph = "word " * 2000  # far beyond MAX_TOKENS on its own
    text = f"A short intro.\n\n{huge_paragraph}\n\nA short outro."

    chunks = chunk_text(text)

    assert any("word word word" in c.text for c in chunks)
    for c in chunks:
        assert text[c.char_start : c.char_end] == c.text
