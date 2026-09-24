"""Token-aware, paragraph-preserving chunking with exact char-offset tracking.

Each chunk is the provenance unit (plans/ingestion.md's Data model: the `Chunk` model) — every
downstream citation traces back to one chunk's `[char_start, char_end)` into its source text.

Uses tiktoken's cl100k_base encoding as a token-count *approximation* (the target model isn't
GPT; this is only for sizing chunks reasonably, not exact accounting for billing/limits) — see
plans/ingestion.md's "New backend dependencies".
"""

import re

import tiktoken

from app.schemas.ingestion import ChunkSpan

_ENCODING = tiktoken.get_encoding("cl100k_base")

TARGET_TOKENS = 650
MAX_TOKENS = 800

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    """[(start, end), ...] char spans for each non-blank paragraph, split on blank lines."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for match in _PARAGRAPH_BREAK.finditer(text):
        para = text[pos : match.start()]
        if para.strip():
            spans.append((pos, match.start()))
        pos = match.end()
    tail = text[pos:]
    if tail.strip():
        spans.append((pos, len(text)))
    return spans


def _token_count(text: str) -> int:
    return len(_ENCODING.encode(text, disallowed_special=()))


def chunk_text(text: str) -> list[ChunkSpan]:
    """Pack consecutive paragraphs into ~TARGET_TOKENS chunks, splitting before MAX_TOKENS.

    A single paragraph longer than MAX_TOKENS becomes its own (oversized) chunk rather than
    being split mid-paragraph — chunk boundaries never cut a sentence.
    """
    paragraphs = _paragraph_spans(text)
    if not paragraphs:
        return []

    chunks: list[ChunkSpan] = []
    group_start: int | None = None
    group_end: int | None = None
    group_tokens = 0

    def flush() -> None:
        nonlocal group_start, group_end, group_tokens
        if group_start is not None:
            chunks.append(
                ChunkSpan(
                    text=text[group_start:group_end],
                    char_start=group_start,
                    char_end=group_end,
                )
            )
        group_start, group_end, group_tokens = None, None, 0

    for para_start, para_end in paragraphs:
        para_tokens = _token_count(text[para_start:para_end])
        if group_start is not None and group_tokens + para_tokens > MAX_TOKENS:
            flush()
        if group_start is None:
            group_start = para_start
        group_end = para_end
        group_tokens += para_tokens
        if group_tokens >= TARGET_TOKENS:
            flush()

    flush()  # trailing partial group, if any

    return chunks
