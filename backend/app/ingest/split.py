"""Split Markdown into extraction chunks (plans/mvp-v0.md). Deterministic — no LLM.

A document ≤ `extract_chunk_chars` (40k) is one chunk. Larger documents are split on
`^#{1,3}` headings, packed into windows, and overlapped by `chunk_overlap_chars` (1.5k).
Every chunk's `text == markdown[char_start:char_end]`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"(?m)^#{1,3} ")


@dataclass(frozen=True)
class TextChunk:
    ordinal: int
    char_start: int
    char_end: int
    text: str


def _split_span(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    """Split [start, end) into pieces ≤ max_chars, preferring paragraph then whitespace."""
    pieces: list[tuple[int, int]] = []
    while end - start > max_chars:
        limit = start + max_chars
        cut = text.rfind("\n\n", start + 1, limit)
        if cut <= start:
            cut = text.rfind("\n", start + 1, limit)
        if cut <= start:
            cut = text.rfind(" ", start + 1, limit)
        if cut <= start:
            cut = limit
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


def _heading_spans(text: str) -> list[tuple[int, int]]:
    """[start, end) of each heading-delimited section (text before the first heading is one)."""
    starts = [m.start() for m in HEADING_RE.finditer(text)]
    if not starts or starts[0] != 0:
        starts = [0, *starts]
    spans: list[tuple[int, int]] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        if end > start:
            spans.append((start, end))
    return spans or [(0, len(text))]


def split_markdown(
    text: str,
    *,
    max_chars: int = 40_000,
    overlap_chars: int = 1_500,
) -> list[TextChunk]:
    """Return one or more chunks covering `text` with exact char offsets."""
    if not text:
        return []
    if len(text) <= max_chars:
        return [TextChunk(ordinal=0, char_start=0, char_end=len(text), text=text)]

    units: list[tuple[int, int]] = []
    for start, end in _heading_spans(text):
        units.extend(_split_span(text, start, end, max_chars))

    groups: list[list[tuple[int, int]]] = []
    for unit in units:
        if groups and unit[1] - groups[-1][0][0] <= max_chars:
            groups[-1].append(unit)
        else:
            groups.append([unit])

    chunks: list[TextChunk] = []
    prev_start = 0
    for ordinal, group in enumerate(groups):
        core_start, end = group[0][0], group[-1][1]
        start = core_start
        if ordinal > 0 and overlap_chars > 0:
            start = _snap_forward_to_word(
                text, max(core_start - overlap_chars, prev_start), prev_start
            )
            start = min(start, core_start)
        chunks.append(
            TextChunk(ordinal=ordinal, char_start=start, char_end=end, text=text[start:end])
        )
        prev_start = core_start
    return chunks
