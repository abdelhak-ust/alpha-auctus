"""chunk.py — section-boundary chunks, overlap, exact offsets, deterministic ids (§5 step 3)."""

import uuid

from app.ingest.chunk import ChunkSpec, chunk_document, chunk_id_for
from app.ingest.parse import Block, build_parsed

DOC = str(uuid.uuid4())


def _doc(sections: int, words_per_section: int):
    blocks = []
    for i in range(sections):
        blocks.append(Block("heading", f"Section {i}", level=1))
        blocks.append(Block("text", " ".join(f"s{i}w{j}" for j in range(words_per_section))))
    return build_parsed(blocks)


def _assert_exact(parsed, chunks):
    for c in chunks:
        assert c.text == parsed.text[c.char_start:c.char_end]


def test_small_document_is_one_chunk():
    parsed = _doc(3, 10)
    chunks = chunk_document(parsed, document_id=DOC)
    assert len(chunks) == 1
    assert chunks[0].char_start == 0 and chunks[0].char_end == len(parsed.text)
    assert chunks[0].section_path == ["Section 0"]


def test_chunks_start_on_section_boundaries_with_overlap():
    parsed = _doc(6, 60)  # ~6 × 420 chars
    chunks = chunk_document(parsed, document_id=DOC, max_tokens=150, overlap_tokens=30)
    assert len(chunks) > 1
    _assert_exact(parsed, chunks)
    section_starts = {s.char_start for s in parsed.sections}
    for prev, cur in zip(chunks, chunks[1:], strict=False):
        # overlap: the chunk starts before the previous one ends ...
        assert cur.char_start < prev.char_end
        # ... and its core (after the overlap) begins at a section heading
        core = parsed.text.find("Section", cur.char_start)
        assert any(core <= s < cur.char_end for s in section_starts)
        # overlap never starts mid-word
        assert cur.char_start == 0 or parsed.text[cur.char_start - 1].isspace()


def test_oversized_section_is_split_without_cutting_words():
    parsed = _doc(1, 400)  # one ~2.8k-char section
    chunks = chunk_document(parsed, document_id=DOC, max_tokens=100, overlap_tokens=0)
    assert len(chunks) > 3
    _assert_exact(parsed, chunks)
    for c in chunks:
        assert len(c.text) <= 400
        assert not c.text[0].isspace() and not c.text[-1].isspace()
        assert c.section_path == ["Section 0"]
    covered = "".join(c.text + " " for c in chunks).split()
    assert covered == parsed.text.split()  # nothing lost


def test_ids_are_deterministic_uuids_and_round_trip():
    parsed = _doc(4, 80)
    a = chunk_document(parsed, document_id=DOC, max_tokens=120, overlap_tokens=20)
    b = chunk_document(parsed, document_id=DOC, max_tokens=120, overlap_tokens=20)
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]
    assert a[1].chunk_id == chunk_id_for(DOC, 1)
    uuid.UUID(a[0].chunk_id)
    assert ChunkSpec.from_dict(a[1].to_dict()) == a[1]
    assert [c.ordinal for c in a] == list(range(len(a)))
