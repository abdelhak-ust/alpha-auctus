"""LLM extraction: one chunk -> candidate Items + candidate DecisionRecords.

Uses a forced tool-call (not free-text JSON) so the shape is actually reliable — Claude's tool
schema is a much stronger guarantee than "please output JSON" prompting.

**Hallucination guard**: every candidate must carry a `snippet` that is a literal substring of
its source chunk. Anything that doesn't literally quote the chunk is dropped, not corrected or
kept — a concrete enforcement of "cite or stay silent" (architecture.md; plans/ingestion.md
step 4). This is the single most important property of this module: a silent miss (dropping a
real requirement) is recoverable next ingest pass; a fabricated citation is not something the
rest of the product can detect on its own.
"""

from app.ai import get_client
from app.config import get_settings
from app.schemas.ingestion import ExtractedDecision, ExtractedItem, ExtractionResult

_TOOL_NAME = "extract_candidates"

_TOOL_SCHEMA = {
    "name": _TOOL_NAME,
    "description": (
        "Record every distinct requirement/task/feedback item and every distinct "
        "architectural decision statement found in this chunk of text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": "Backlog-worthy requirements, tasks, or feedback.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Short descriptive title."},
                        "description": {"type": "string", "description": "1-2 sentences of detail"},
                        "entity_tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Feature/area names touched, e.g. 'auth', 'billing'.",
                        },
                        "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                        "snippet": {
                            "type": "string",
                            "description": "EXACT verbatim text this was extracted from — "
                            "copy-paste, do not paraphrase.",
                        },
                    },
                    "required": ["title", "snippet"],
                },
            },
            "decisions": {
                "type": "array",
                "description": "Atomic, normalized architectural/product decision statements.",
                "items": {
                    "type": "object",
                    "properties": {
                        "statement": {
                            "type": "string",
                            "description": "Normalized 'we will X' / 'we will not X' — one claim.",
                        },
                        "polarity": {"type": "string", "enum": ["affirm", "negate"]},
                        "affected_entities": {"type": "array", "items": {"type": "string"}},
                        "snippet": {
                            "type": "string",
                            "description": "EXACT verbatim text this was extracted from — "
                            "copy-paste, do not paraphrase.",
                        },
                    },
                    "required": ["statement", "snippet"],
                },
            },
        },
        "required": ["items", "decisions"],
    },
}

_SYSTEM_PROMPT = (
    "You extract structured backlog items and decision statements from raw project text "
    "(meeting notes, briefs, tickets, transcripts). Only extract what is actually present — "
    "if the chunk has no clear requirements or decisions, call the tool with empty arrays "
    "rather than inventing something. Every `snippet` must be copied verbatim from the input; "
    "never paraphrase or summarize into the snippet field — it is used as a citation and will "
    "be rejected if it doesn't literally appear in the source."
)


async def extract_from_chunk(chunk_text: str) -> ExtractionResult:
    """Run extraction on a single chunk and filter out any candidate whose snippet isn't a
    literal substring of that chunk (the hallucination guard)."""
    if not chunk_text.strip():
        return ExtractionResult()

    settings = get_settings()
    client = get_client()
    response = await client.messages.create(
        model=settings.vertex_model,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[{"role": "user", "content": chunk_text}],
    )

    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        return ExtractionResult()

    raw = tool_use.input or {}

    items: list[ExtractedItem] = []
    for raw_item in raw.get("items", []):
        snippet = (raw_item.get("snippet") or "").strip()
        title = (raw_item.get("title") or "").strip()
        if not title or not snippet or snippet not in chunk_text:
            continue  # hallucination guard: drop, don't keep or "fix"
        items.append(
            ExtractedItem(
                title=title,
                description=raw_item.get("description", ""),
                entity_tags=raw_item.get("entity_tags", []),
                priority=raw_item.get("priority", "P2"),
                snippet=snippet,
            )
        )

    decisions: list[ExtractedDecision] = []
    for raw_decision in raw.get("decisions", []):
        snippet = (raw_decision.get("snippet") or "").strip()
        statement = (raw_decision.get("statement") or "").strip()
        if not statement or not snippet or snippet not in chunk_text:
            continue
        decisions.append(
            ExtractedDecision(
                statement=statement,
                polarity=raw_decision.get("polarity", "affirm"),
                affected_entities=raw_decision.get("affected_entities", []),
                snippet=snippet,
            )
        )

    return ExtractionResult(items=items, decisions=decisions)
