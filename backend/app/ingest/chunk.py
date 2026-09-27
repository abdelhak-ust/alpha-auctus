"""Chunk (plans/ingestion.md §5 step 3): split a parsed document on section boundaries.

- A chunk is a run of whole consecutive sections while they fit in `max_tokens`; a section
  larger than that is split at paragraph boundaries (then whitespace, never mid-word).
- Every chunk after the first is extended backwards by up to `overlap_tokens` (~200–500 tokens,
  §3) so a feature described across a boundary is visible in both chunks.
- `text == parsed.text[char_start:char_end]` always holds — these offsets are what every
  downstream `source_ref` points at (contract §5).
- Chunk ids are deterministic (uuid5 of document id + ordinal), so re-running the job for the
  same document produces the same ids and upserts instead of duplicating (§2 idempotency).

Token counts are approximated as chars / 4 — only used for sizing, never for billing.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass

from app.ingest.parse import ParsedDocument, Section

CHARS_PER_TOKEN = 4
DEFAULT_MAX_TOKENS = 1000
DEFAULT_OVERLAP_TOKENS = 200

_CHUNK_NAMESPACE = uuid.UUID("5b0c7a53-1d1e-4a7e-9d8e-6e7a3c1b2f40")


@dataclass
class ChunkSpec:
    chunk_id: str
    ordinal: int
    section_path: list[str]
    char_start: int
    char_end: int
    text: str
    page_start: int | None = None
    page_end: int | None = None

    @property
    def section(self) -> str:
        """The nearest heading — the `section` value of a `source_ref`."""
        return self.section_path[-1] if self.section_path else ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ChunkSpec:
        return cls(**data)


def chunk_id_for(document_id: str, ordinal: int) -> str:
    return str(uuid.uuid5(_CHUNK_NAMESPACE, f"{document_id}:{ordinal}"))


def _split_span(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    """Split [start, end) into pieces ≤ max_chars, preferring paragraph then whitespace breaks."""
    pieces: list[tuple[int, int]] = []
    while end - start > max_chars:
        limit = start + max_chars
        cut = text.rfind("\n\n", start + 1, limit)
        if cut <= start:
            cut = text.rfind("\n", start + 1, limit)
        if cut <= start:
            cut = text.rfind(" ", start + 1, limit)
        if cut <= start:
            cut = limit  # one enormous token — nothing better to do
        pieces.append((start, cut))
        start = cut
        while start < end and text[start].isspace():
            start += 1
    if end > start:
        pieces.append((start, end))
    return pieces


def _snap_forward_to_word(text: str, pos: int, floor: int) -> int:
    """Move `pos` forward to the start of a word so overlap never begins mid-word."""
    if pos <= floor:
        return floor
    if text[pos - 1].isspace():
        return pos
    nxt = pos
    while nxt < len(text) and not text[nxt].isspace():
        nxt += 1
    while nxt < len(text) and text[nxt].isspace():
        nxt += 1
    return nxt


def chunk_document(
    parsed: ParsedDocument,
    *,
    document_id: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[ChunkSpec]:
    text = parsed.text
    max_chars = max_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    sections = parsed.sections or [Section(path=[], char_start=0, char_end=len(text))]

    # 1. Units: whole sections, or paragraph-split pieces of oversized ones.
    units: list[tuple[int, int, Section]] = []
    for section in sections:
        for s, e in _split_span(text, section.char_start, section.char_end, max_chars):
            units.append((s, e, section))

    # 2. Greedily pack consecutive units up to max_chars.
    groups: list[list[tuple[int, int, Section]]] = []
    for unit in units:
        if groups and unit[1] - groups[-1][0][0] <= max_chars:
            groups[-1].append(unit)
        else:
            groups.append([unit])

    # 3. Emit with backward overlap; offsets always index into `text`.
    chunks: list[ChunkSpec] = []
    prev_start = 0
    for ordinal, group in enumerate(groups):
        core_start, end = group[0][0], group[-1][1]
        start = core_start
        if ordinal > 0 and overlap_chars > 0:
            start = _snap_forward_to_word(text, max(core_start - overlap_chars, prev_start),
                                          prev_start)
            start = min(start, core_start)
        first_section = group[0][2]
        pages = [p for _, _, sec in group for p in (sec.page_start, sec.page_end) if p]
        chunks.append(
            ChunkSpec(
                chunk_id=chunk_id_for(document_id, ordinal),
                ordinal=ordinal,
                section_path=list(first_section.path),
                char_start=start,
                char_end=end,
                text=text[start:end],
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
            )
        )
        prev_start = core_start
    return chunks
