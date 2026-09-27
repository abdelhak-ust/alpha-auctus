"""Read-only document tools and clarifier write tools (plans/mvp-v0.md).

Bound to one document / feature per run via `bind_document_tools` / `bind_clarifier_tools`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import tool

HEADING_RE = re.compile(r"(?m)^(#{1,3}) (.+)$")
PASSAGE_CHARS = 400
MAX_HITS = 5


def _keyword_score(text: str, query: str) -> int:
    tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
    if not tokens:
        return 1 if query.lower() in text.lower() else 0
    hay = text.lower()
    return sum(hay.count(t) for t in tokens)


def keyword_passages(
    markdown: str,
    query: str,
    *,
    max_hits: int = MAX_HITS,
    passage_chars: int = PASSAGE_CHARS,
) -> list[tuple[int, int, int, str]]:
    """Top keyword-scored windows: (score, start, end, text). Empty if nothing matches."""
    if not query.strip() or not markdown:
        return []
    step = max(passage_chars, 1)
    hop = max(step // 2, 1)
    hits: list[tuple[int, int, int, str]] = []
    for start in range(0, len(markdown), hop):
        end = min(len(markdown), start + step)
        passage = markdown[start:end]
        score = _keyword_score(passage, query)
        if score:
            hits.append((score, start, end, passage))
    hits.sort(key=lambda h: (-h[0], h[1]))
    return hits[:max_hits]


def _sections(markdown: str) -> list[tuple[str, int, int]]:
    """(heading, start, end) covering the whole document."""
    matches = list(HEADING_RE.finditer(markdown))
    if not matches:
        return [("", 0, len(markdown))]
    out: list[tuple[str, int, int]] = []
    if matches[0].start() > 0:
        out.append(("", 0, matches[0].start()))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        out.append((m.group(2).strip(), m.start(), end))
    return out


def bind_document_tools(markdown: str) -> list:
    """search_document / read_section / list_sections closed over this document."""

    @tool
    def search_document(query: str) -> str:
        """Return the top passages matching `query`, each with char offsets."""
        if not query.strip():
            return "No query."
        top = keyword_passages(markdown, query)
        if not top:
            return f"No passages matched {query!r}."
        parts = []
        for score, start, end, passage in top:
            parts.append(f"[{start}:{end}] (score {score})\n{passage.strip()}")
        return "\n\n---\n\n".join(parts)

    @tool
    def read_section(heading: str) -> str:
        """Return the full text of the section whose heading matches `heading`."""
        want = heading.strip().lower()
        for title, start, end in _sections(markdown):
            if title.lower() == want or want in title.lower():
                return f"[{start}:{end}] {markdown[start:end].strip()}"
        return f"No section headed {heading!r}. Use list_sections() for the outline."

    @tool
    def list_sections() -> str:
        """Return the document's heading outline with char offsets."""
        secs = _sections(markdown)
        if not secs or (len(secs) == 1 and not secs[0][0]):
            return "No headings in this document."
        lines = [f"[{start}:{end}] {title}" for title, start, end in secs if title]
        return "\n".join(lines) or "No headings in this document."

    return [search_document, read_section, list_sections]


@dataclass
class ClarifierScratch:
    """Mutations the Clarifier made this turn — persisted by the graph, not the tools."""

    updates: list[dict[str, Any]] = field(default_factory=list)
    follow_ups: list[dict[str, str]] = field(default_factory=list)
    resolved: bool = False
    follow_up_count: int = 0
    max_follow_ups: int = 2


def bind_clarifier_tools(scratch: ClarifierScratch) -> list:
    """update_feature_field / ask_follow_up / mark_resolved closed over this turn."""

    @tool
    def update_feature_field(field: str, value: str) -> str:
        """Write `value` into a feature field. The value is cited as a PM answer."""
        field = field.strip()
        value = value.strip()
        if not field or not value:
            return "field and value are required."
        scratch.updates.append({"field": field, "value": value})
        return f"Updated {field}."

    @tool
    def ask_follow_up(question: str, why: str) -> str:
        """Ask one follow-up. Capped per feature."""
        if scratch.follow_up_count >= scratch.max_follow_ups:
            return (
                f"Follow-up cap ({scratch.max_follow_ups}) reached. "
                "Update what you can and mark_resolved."
            )
        q = question.strip()
        if not q:
            return "question is required."
        scratch.follow_ups.append({"question": q, "why": why.strip(), "target_field": ""})
        scratch.follow_up_count += 1
        return "Follow-up recorded."

    @tool
    def mark_resolved() -> str:
        """This question is done (answered or nothing more to ask)."""
        scratch.resolved = True
        return "Marked resolved."

    return [update_feature_field, ask_follow_up, mark_resolved]


# Exposed for tests that want the section helper without constructing tools.
list_document_sections: Callable[[str], list[tuple[str, int, int]]] = _sections
