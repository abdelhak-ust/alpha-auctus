"""Qdrant async client + the frozen vector-store functions (plans/ingestion.md §11.3)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.config import get_settings

FEATURES = "features"
CHUNKS = "chunks"

# Payload fields indexed per collection (keyword index — exact-match filters).
_PAYLOAD_INDEXES: dict[str, tuple[str, ...]] = {
    FEATURES: ("project_id", "feature_id"),
    CHUNKS: ("project_id", "doc_id", "chunk_id", "feature_ids"),
}

_client: AsyncQdrantClient | None = None


@dataclass(frozen=True)
class ScoredFeature:
    """One `search_features` hit: cosine `score` in [-1, 1] (≥ threshold) plus its payload."""

    feature_id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


def get_client() -> AsyncQdrantClient:
    """Process-wide async Qdrant client. `QDRANT_URL=":memory:"` → in-process store."""
    global _client
    if _client is None:
        url = get_settings().qdrant_url
        _client = (
            AsyncQdrantClient(location=":memory:") if url == ":memory:"
            else AsyncQdrantClient(url=url)
        )
    return _client


def set_client(client: AsyncQdrantClient) -> None:
    """Swap in a client (tests: an in-memory one)."""
    global _client
    _client = client


def reset_client() -> None:
    """Drop the cached client so the next `get_client()` rebuilds it from settings."""
    global _client
    _client = None


async def ensure_collections() -> None:
    """Create `features` and `chunks` (cosine, `embedding_dim`) + payload indexes if missing.

    Idempotent — safe to call on every worker/app start.
    """
    client = get_client()
    dim = get_settings().embedding_dim
    for name, indexed in _PAYLOAD_INDEXES.items():
        if not await client.collection_exists(name):
            await client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
            )
        for field_name in indexed:
            await client.create_payload_index(
                collection_name=name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )


def _to_points(points: Iterable[Mapping[str, Any]], required: tuple[str, ...]) -> list:
    out = []
    for p in points:
        payload = dict(p["payload"])
        missing = [k for k in required if payload.get(k) in (None, "")]
        if missing:
            raise ValueError(f"Vector point {p.get('id')!r} payload is missing {missing}.")
        out.append(
            models.PointStruct(id=str(p["id"]), vector=list(p["vector"]), payload=payload)
        )
    return out


async def upsert_features(points: Iterable[Mapping[str, Any]]) -> None:
    """Upsert feature points `{id: str(feature_id), vector, payload}`.

    Payload: `{project_id, feature_id, name, lifecycle_state, source_refs, last_updated}`.
    """
    structs = _to_points(points, ("project_id", "feature_id"))
    if structs:
        await get_client().upsert(collection_name=FEATURES, points=structs, wait=True)


async def upsert_chunks(points: Iterable[Mapping[str, Any]]) -> None:
    """Upsert chunk points `{id: str(chunk_id), vector, payload}`.

    Payload: `{project_id, doc_id, chunk_id, feature_ids: list[str], section, char_start,
    char_end, text}` (extra keys are kept).
    """
    structs = _to_points(points, ("project_id", "doc_id", "chunk_id"))
    for s in structs:
        s.payload.setdefault("feature_ids", [])
    if structs:
        await get_client().upsert(collection_name=CHUNKS, points=structs, wait=True)


def _match(key: str, value: str) -> models.FieldCondition:
    return models.FieldCondition(key=key, match=models.MatchValue(value=value))


async def search_features(
    project_id: str,
    vector: list[float],
    top_k: int | None = None,
    threshold: float | None = None,
) -> list[ScoredFeature]:
    """Top-`top_k` features in `project_id` with cosine ≥ `threshold`, best first.

    Defaults: `settings.feature_match_top_k` / `settings.feature_match_threshold`.
    """
    settings = get_settings()
    top_k = settings.feature_match_top_k if top_k is None else top_k
    threshold = settings.feature_match_threshold if threshold is None else threshold
    result = await get_client().query_points(
        collection_name=FEATURES,
        query=list(vector),
        query_filter=models.Filter(must=[_match("project_id", project_id)]),
        limit=top_k,
        score_threshold=threshold,
        with_payload=True,
    )
    return [
        ScoredFeature(
            feature_id=str((p.payload or {}).get("feature_id") or p.id),
            score=float(p.score),
            payload=dict(p.payload or {}),
        )
        for p in result.points
    ]


async def get_chunks(
    project_id: str, *, feature_id: str | None = None, doc_id: str | None = None
) -> list[dict[str, Any]]:
    """All chunk payloads in `project_id`, optionally narrowed to chunks citing `feature_id`
    (matched against `feature_ids`) and/or from `doc_id`. Ordered by (doc_id, char_start)."""
    must = [_match("project_id", project_id)]
    if feature_id is not None:
        must.append(_match("feature_ids", str(feature_id)))
    if doc_id is not None:
        must.append(_match("doc_id", str(doc_id)))

    client = get_client()
    out: list[dict[str, Any]] = []
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=CHUNKS,
            scroll_filter=models.Filter(must=must),
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        out.extend(dict(p.payload or {}) for p in points)
        if offset is None:
            break
    out.sort(key=lambda c: (str(c.get("doc_id", "")), c.get("char_start") or 0))
    return out
