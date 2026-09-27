"""Completeness sweep (plans/ingestion.md §5 step 6 / §6 step 6).

A high-recall, low-precision pass per chunk ("list every candidate feature mention, even
fragments"), reconciled against what consolidation produced. Anything uncovered becomes a
`review_items(kind=sweep_flag)` row — tinted "please review", never dropped and never
auto-created as a feature (CLAUDE.md "never silently miss, never cry wolf"). Extraction
fragments whose quote couldn't be located are flagged the same way (cite or stay silent).
Chunks that contributed zero features are reported for spot-checking (audit only).
"""

from __future__ import annotations

from app.ingest.chunk import ChunkSpec
from app.ingest.cite import (
    chunk_fallback_ref,
    make_source_ref,
    names_match,
    normalize_name,
    spans_overlap,
)
from app.ingest.llm import call_llm
from app.ingest.prompts import sweep_prompt
from app.schemas.ingestion import SweepResult


async def sweep_chunk(chunk: ChunkSpec) -> SweepResult:
    return await call_llm(
        sweep_prompt(chunk_text=chunk.text, section=" > ".join(chunk.section_path)),
        SweepResult,
    )


def _covered(name: str, ref: dict | None, features: list[dict], fragments: list[dict]) -> bool:
    for feature in features:
        if names_match(name, feature["name"]):
            return True
        if ref and any(spans_overlap(ref, r) for r in feature["source_refs"]):
            return True
    return any(names_match(name, f["feature_name"]) for f in fragments)


def reconcile(
    *,
    chunks: list[ChunkSpec],
    sweeps: dict[int, SweepResult],
    features: list[dict],
    fragments: list[dict],
    unlocated: list[dict],
    document_id: str,
    doc_type: str,
) -> tuple[list[dict], list[int]]:
    """Returns (sweep flag payloads, ordinals of chunks that contributed zero features).

    Each payload is exactly the §11.3 `review_items(kind=sweep_flag)` shape:
    `{feature_name, description, reason, confidence, source_ref}` — `source_ref` is always
    present (whole-chunk fallback with `"located": False` when the quote isn't verbatim)."""
    by_ordinal = {c.ordinal: c for c in chunks}
    flags: list[dict] = []
    seen: set[str] = set()

    def add(flag: dict) -> None:
        key = normalize_name(flag["feature_name"])
        if key and key not in seen:
            seen.add(key)
            flags.append(flag)

    for ordinal in sorted(sweeps):
        chunk = by_ordinal[ordinal]
        for mention in sweeps[ordinal].mentions:
            ref = make_source_ref(
                chunk, mention.snippet, document_id=document_id, doc_type=doc_type,
                confidence=mention.confidence,
            )
            if _covered(mention.name, ref, features, fragments):
                continue
            add({
                "feature_name": mention.name,
                "description": "",
                "reason": "uncovered_mention",
                "confidence": mention.confidence,
                "source_ref": ref or chunk_fallback_ref(
                    chunk, document_id=document_id, doc_type=doc_type),
            })

    for fragment in unlocated:
        if _covered(fragment["feature_name"], None, features, []):
            continue
        chunk = by_ordinal[fragment["chunk_ordinal"]]
        add({
            "feature_name": fragment["feature_name"],
            "description": fragment["description"],
            "reason": "no_locatable_source",
            "confidence": fragment["confidence"],
            "source_ref": chunk_fallback_ref(chunk, document_id=document_id, doc_type=doc_type),
        })

    contributing = {r["chunk_id"] for f in features for r in f["source_refs"]}
    zero = [c.ordinal for c in chunks if c.chunk_id not in contributing]
    return flags, zero
