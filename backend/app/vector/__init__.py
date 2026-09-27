"""Vector store — Qdrant (plans/ingestion.md §4.2, §11.1 / §11.3).

Two collections, both cosine / `embedding_dim`:
- `features` — one point per feature (id = feature_id), re-embedded on description change.
- `chunks`   — one point per document chunk (id = chunk_id), `feature_ids` lists the features
  it cites.

Every point payload carries `project_id`, and every read filters by it. Call through the
module (`vector.search_features(...)`) so tests can swap the client with `set_client`.
"""

from app.vector.store import (
    CHUNKS,
    FEATURES,
    ScoredFeature,
    ensure_collections,
    get_chunks,
    get_client,
    reset_client,
    search_features,
    set_client,
    upsert_chunks,
    upsert_features,
)

__all__ = [
    "CHUNKS",
    "FEATURES",
    "ScoredFeature",
    "ensure_collections",
    "get_chunks",
    "get_client",
    "reset_client",
    "search_features",
    "set_client",
    "upsert_chunks",
    "upsert_features",
]
