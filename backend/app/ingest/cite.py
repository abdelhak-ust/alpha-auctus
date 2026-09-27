"""Cite or stay silent (CLAUDE.md): locate a quote in the document Markdown.

The model's own offsets are never trusted. We search for the quoted snippet by exact
string match, then by whitespace-normalised match. A quote we can't find is marked
`verified=False` and shown as "unverified" — never presented as fact.
"""

from __future__ import annotations

import re

MIN_SNIPPET_CHARS = 8


def _clean(quote: str) -> str:
    return quote.strip().strip('"\u201c\u201d').strip()


def _collapse_with_map(text: str) -> tuple[str, list[int]]:
    """Whitespace-collapse `text` and return (collapsed, original_index_for_each_collapsed_char)."""
    out: list[str] = []
    index: list[int] = []
    prev_space = True  # leading whitespace is dropped
    for i, ch in enumerate(text):
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                index.append(i)
                prev_space = True
            continue
        out.append(ch)
        index.append(i)
        prev_space = False
    if out and out[-1] == " ":
        out.pop()
        index.pop()
    return "".join(out), index


def locate_quote(markdown: str, quote: str) -> tuple[int, int] | None:
    """Document-level `[start, end)` of `quote` in `markdown`, or None."""
    q = _clean(quote)
    if len(q) < MIN_SNIPPET_CHARS:
        return None
    pos = markdown.find(q)
    if pos >= 0:
        return pos, pos + len(q)

    collapsed, index = _collapse_with_map(markdown)
    needle = re.sub(r"\s+", " ", q).strip()
    if len(needle) < MIN_SNIPPET_CHARS:
        return None
    cpos = collapsed.find(needle)
    if cpos < 0:
        return None
    start = index[cpos]
    last = index[cpos + len(needle) - 1]
    return start, last + 1


def verify_quote(markdown: str, quote: str) -> dict:
    """`{quote, verified, char_start?, char_end?}` — unverified when the quote is unfindable."""
    q = _clean(quote)
    found = locate_quote(markdown, q) if q else None
    if found is None:
        return {"quote": q, "verified": False, "origin": "document"}
    start, end = found
    return {
        "quote": markdown[start:end],
        "verified": True,
        "char_start": start,
        "char_end": end,
        "origin": "document",
    }


def verify_quotes(markdown: str, quotes: list[str]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for quote in quotes:
        item = verify_quote(markdown, quote)
        key = item["quote"]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
