"""Sequential extraction with rolling state (plans/ingestion.md §5 step 4 / §6 step 4).

No chunk is extracted in isolation (§2): each call gets the compact rolling summary of features
found so far in this document and, in incremental mode, the top-k registry candidates retrieved
for that chunk. This is the recall pass — it only *finds* fragments; merging is consolidate.py.

Each fragment's quote is located in the chunk (cite.py). Fragments whose quote can't be found
are returned separately as `unlocated` — they become sweep flags, never features.
"""

from __future__ import annotations

from app.ingest.chunk import ChunkSpec
from app.ingest.cite import make_source_ref, names_match
from app.ingest.llm import call_llm
from app.ingest.prompts import extraction_prompt
from app.schemas.ingestion import ExtractionResult

SUMMARY_LINE_CHARS = 140


async def extract_chunk(
    chunk: ChunkSpec,
    *,
    document_id: str,
    doc_type: str,
    rolling_summary: list[dict],
    registry_candidates: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Run one extraction call. Returns (located fragments, unlocated fragments) as dicts."""
    prompt = extraction_prompt(
        chunk_text=chunk.text,
        section=" > ".join(chunk.section_path),
        rolling_summary=rolling_summary,
        registry_candidates=registry_candidates,
    )
    result = await call_llm(prompt, ExtractionResult)

    located: list[dict] = []
    unlocated: list[dict] = []
    for fragment in result.fragments:
        data = fragment.model_dump()
        data["chunk_ordinal"] = chunk.ordinal
        data["chunk_id"] = chunk.chunk_id
        ref = make_source_ref(
            chunk, fragment.snippet, document_id=document_id, doc_type=doc_type,
            confidence=fragment.confidence,
        )
        if ref is None:
            unlocated.append(data)
            continue
        # The model's offsets are replaced by where the quote really is (absolute offsets).
        data["char_start"], data["char_end"] = ref["char_start"], ref["char_end"]
        data["snippet"] = ref["snippet"]
        data["section"] = ref["section"]
        data["source_ref"] = ref
        located.append(data)
    return located, unlocated


def _one_line(description: str) -> str:
    line = description.strip().split("\n", 1)[0]
    first_sentence = line.split(". ", 1)[0]
    return first_sentence[:SUMMARY_LINE_CHARS]


def update_rolling_summary(rolling: list[dict], fragments: list[dict]) -> list[dict]:
    """Compact rolling state: one {name, summary} line per feature found so far."""
    out = [dict(r) for r in rolling]
    for fragment in fragments:
        target = fragment.get("references_feature") or fragment["feature_name"]
        existing = next(
            (r for r in out if names_match(r["name"], target)
             or names_match(r["name"], fragment["feature_name"])),
            None,
        )
        if existing is None:
            out.append({"name": fragment["feature_name"],
                        "summary": _one_line(fragment["description"])})
    return out
