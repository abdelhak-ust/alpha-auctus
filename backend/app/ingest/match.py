"""Registry awareness (plans/ingestion.md §6 steps 3–5).

- `retrieve_for_chunks`: before extraction, each chunk is embedded (RETRIEVAL_QUERY) and the
  top-k registry features ≥ `feature_match_threshold` are fetched from Qdrant — they go into
  that chunk's extraction prompt (no chunk extracted in isolation).
- `classify_features`: after consolidation, each consolidated feature is embedded
  (RETRIEVAL_QUERY) and matched against the registry. No candidate ≥ threshold ⇒ NEW with no
  LLM call; otherwise one classification call returns NEW / UPDATE / CONFLICT / DUPLICATE with
  ranked candidates. An UPDATE gets a separate merge call (find ≠ merge); a merge that surfaces
  a contradiction is escalated to CONFLICT. A verdict below `REVIEW_CONFIDENCE_FLOOR` is never
  applied — it becomes outcome `review` (a sweep flag carrying the ranked candidates), so a
  human decides (CLAUDE.md "never silently miss, never cry wolf").
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import vector
from app.config import get_settings
from app.ingest.chunk import ChunkSpec
from app.ingest.llm import call_llm, embed
from app.ingest.prompts import match_prompt, merge_prompt
from app.models import Feature, FeatureVersion
from app.schemas.ingestion import ConsolidatedFeature, MatchVerdict

REVIEW_CONFIDENCE_FLOOR = 0.6
DESCRIPTION_PREVIEW_CHARS = 600


def _hit(raw: Any) -> dict:
    """Normalize a `ScoredFeature(feature_id, score, payload)` (or an equivalent dict)."""
    if isinstance(raw, dict):
        payload = raw.get("payload") or {}
        fid = raw.get("feature_id") or payload.get("feature_id")
        return {"feature_id": str(fid), "score": float(raw.get("score", 0.0)),
                "payload": payload}
    payload = getattr(raw, "payload", None) or {}
    fid = getattr(raw, "feature_id", None) or payload.get("feature_id")
    return {"feature_id": str(fid), "score": float(getattr(raw, "score", 0.0)),
            "payload": payload}


async def search_registry(project_id: str, query_vector: list[float]) -> list[dict]:
    settings = get_settings()
    hits = await vector.search_features(
        project_id, query_vector, top_k=settings.feature_match_top_k,
        threshold=settings.feature_match_threshold,
    )
    return [_hit(h) for h in hits or []]


async def retrieve_for_chunks(project_id: str, chunks: list[ChunkSpec]) -> dict[int, list[dict]]:
    """Top-k registry candidates per chunk ordinal (empty lists when the registry is empty)."""
    if not chunks:
        return {}
    vectors = await embed([c.text for c in chunks], "RETRIEVAL_QUERY")
    out: dict[int, list[dict]] = {}
    for chunk, vec in zip(chunks, vectors, strict=True):
        out[chunk.ordinal] = [
            {"feature_id": h["feature_id"], "name": h["payload"].get("name", ""),
             "similarity": round(h["score"], 3)}
            for h in await search_registry(project_id, vec)
        ]
    return out


async def load_registry_features(
    session: AsyncSession, project_id: str, feature_ids: list[str]
) -> dict[str, dict]:
    """Current state of registry features by id (only this project's, only existing ones)."""
    ids = []
    for fid in feature_ids:
        try:
            ids.append(uuid.UUID(fid))
        except (TypeError, ValueError):
            continue
    if not ids:
        return {}
    rows = await session.execute(
        select(Feature, FeatureVersion)
        .join(FeatureVersion, FeatureVersion.version_id == Feature.current_version_id)
        .where(Feature.project_id == project_id, Feature.feature_id.in_(ids))
    )
    return {
        str(f.feature_id): {
            "feature_id": str(f.feature_id),
            "name": f.name,
            "description": v.description,
            "lifecycle_state": f.lifecycle_state,
            "version_no": v.version_no,
            "version_id": str(v.version_id),
            "source_refs": list(v.source_refs or []),
        }
        for f, v in rows.all()
    }


def _feature_view(feature: dict) -> dict:
    return {
        "name": feature["name"],
        "description": feature["description"],
        "evidence": [r["snippet"] for r in feature["source_refs"]][:5],
    }


async def classify_features(
    session: AsyncSession, project_id: str, features: list[dict]
) -> list[dict]:
    """Attach `outcome` (new|update|conflict|duplicate|review) + match detail to each feature."""
    if not features:
        return []
    vectors = await embed(
        [f"{f['name']}\n{f['description']}" for f in features], "RETRIEVAL_QUERY"
    )
    results: list[dict] = []
    for feature, vec in zip(features, vectors, strict=True):
        hits = await search_registry(project_id, vec)
        scores = {h["feature_id"]: h["score"] for h in hits}
        ids = list(scores)
        if feature.get("registry_hint") and feature["registry_hint"] not in scores:
            ids.append(feature["registry_hint"])
        registry = await load_registry_features(session, project_id, ids)
        result = {**feature, "outcome": "new", "matched_feature_id": None, "candidates": [],
                  "match_confidence": feature.get("confidence", 1.0), "rationale": ""}
        if not registry:
            results.append(result)
            continue

        candidates = [
            {"feature_id": fid, "name": r["name"],
             "description": r["description"][:DESCRIPTION_PREVIEW_CHARS],
             "similarity": round(scores.get(fid, 0.0), 3)}
            for fid, r in registry.items()
        ]
        verdict = await call_llm(
            match_prompt(feature=_feature_view(feature), candidates=candidates), MatchVerdict
        )
        ranked = [c.model_dump() for c in verdict.candidates if c.feature_id in registry]
        matched = verdict.matched_feature_id if verdict.matched_feature_id in registry else (
            ranked[0]["feature_id"] if ranked else None
        )
        result.update(
            outcome=verdict.outcome,
            matched_feature_id=matched if verdict.outcome != "new" else None,
            candidates=ranked,
            match_confidence=verdict.confidence,
            rationale=verdict.rationale,
        )
        if verdict.outcome != "new" and matched is None:
            result["outcome"] = "review"
        elif verdict.confidence < REVIEW_CONFIDENCE_FLOOR:
            result["outcome"] = "review"

        if result["outcome"] in ("update", "conflict", "duplicate"):
            result["existing"] = registry[matched]
        if result["outcome"] == "update":
            merged = await call_llm(
                merge_prompt(existing=_feature_view(registry[matched]),
                             incoming=_feature_view(feature)),
                ConsolidatedFeature,
            )
            if merged.contradictions:
                result["outcome"] = "conflict"
                result["contradictions"] = list(merged.contradictions)
            else:
                result["merged_description"] = merged.description
        results.append(result)
    return results
