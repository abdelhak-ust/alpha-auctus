"""Cite or stay silent (CLAUDE.md; contract §5): turn an LLM quote into a real `source_ref`.

The model's own offsets are never trusted. We search for its quoted snippet inside the chunk
text by exact string search and build the `source_ref` from where we actually found it, with
document-level offsets and the snippet re-sliced from the chunk, so
`snippet == parsed_text[char_start:char_end]` by construction (§11.3). A quote we can't find
yields `None`: the caller must not store that claim as a feature.
"""

from __future__ import annotations

import re

from app.ingest.chunk import ChunkSpec

MIN_SNIPPET_CHARS = 8
FALLBACK_SNIPPET_CHARS = 300


def locate_snippet(chunk_text: str, snippet: str) -> tuple[int, int] | None:
    """Offsets of `snippet` within `chunk_text` (chunk-relative) by exact string search, or
    None. Only surrounding whitespace/quote marks the model wrapped the quote in are
    stripped — the quote itself must appear verbatim (plans/ingestion.md §11.3)."""
    quote = snippet.strip().strip('"\u201c\u201d').strip()
    if len(quote) < MIN_SNIPPET_CHARS:
        return None
    pos = chunk_text.find(quote)
    if pos < 0:
        return None
    return pos, pos + len(quote)


def make_source_ref(
    chunk: ChunkSpec,
    snippet: str,
    *,
    document_id: str,
    doc_type: str,
    confidence: float | None = None,
) -> dict | None:
    """A contract §5 `source_ref` (snake_case dict) with absolute offsets, or None."""
    found = locate_snippet(chunk.text, snippet)
    if found is None:
        return None
    start, end = found
    ref = {
        "doc_id": document_id,
        "doc_type": doc_type,
        "chunk_id": chunk.chunk_id,
        "section": chunk.section,
        "char_start": chunk.char_start + start,
        "char_end": chunk.char_start + end,
        "snippet": chunk.text[start:end],
    }
    if confidence is not None:
        ref["confidence"] = confidence
    return ref


def chunk_fallback_ref(chunk: ChunkSpec, *, document_id: str, doc_type: str) -> dict:
    """Whole-chunk citation (first ~300 chars) for a sweep flag whose quote wasn't found
    verbatim — marked `"located": False` so the UI never presents it as exact evidence."""
    end = min(len(chunk.text), FALLBACK_SNIPPET_CHARS)
    return {
        "doc_id": document_id,
        "doc_type": doc_type,
        "chunk_id": chunk.chunk_id,
        "section": chunk.section,
        "char_start": chunk.char_start,
        "char_end": chunk.char_start + end,
        "snippet": chunk.text[:end],
        "located": False,
    }


def spans_overlap(a: dict, b: dict) -> bool:
    return (
        a["doc_id"] == b["doc_id"]
        and a["char_start"] < b["char_end"]
        and b["char_start"] < a["char_end"]
    )


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def name_tokens(name: str) -> set[str]:
    return {t for t in normalize_name(name).split() if len(t) > 2}


def names_match(a: str, b: str) -> bool:
    """Same feature name: equal after normalization, or ≥ 60% token overlap (Jaccard)."""
    if normalize_name(a) == normalize_name(b):
        return True
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.6
