"""The actual Vertex AI wiring behind app.ai's adapter interface.

Two capabilities, both authenticated via Application Default Credentials (no API key), both
async per nexus-backend-standards ("async everywhere" — a sync call here would stall every
other request on the event loop, not just this one):
- `get_client()` — an `AsyncAnthropicVertex` client for generation (extraction,
  classification, authoring, validation — used by contracts/, engine/, validate/, ingest/).
- `embed_texts()` — Vertex AI text embeddings for indexing (used by ingest/ P6, engine/ P5).
  The `vertexai` SDK has no async embeddings API, so the sync call runs in a worker thread
  (`anyio.to_thread`) rather than blocking the loop directly.

Both raise a clear, actionable `VertexNotConfigured` error rather than a confusing SDK
traceback when `gcp_project_id` isn't set — matching the product's own "Error: inline, not
modal — problem + cause + fix" convention (ui_ux_design.md §7).
"""

from functools import lru_cache

import anyio
from anthropic import AsyncAnthropicVertex

from app.config import get_settings


class VertexNotConfigured(RuntimeError):
    """Raised when a Vertex AI call is attempted without GCP_PROJECT_ID configured."""

    def __init__(self):
        super().__init__(
            "Vertex AI isn't configured: GCP_PROJECT_ID is empty. Set GCP_PROJECT_ID (and "
            "GCP_REGION if not us-east5) in backend/.env, and run "
            "`gcloud auth application-default login` so the backend can authenticate. "
            "See the plan's §0.3 GCP setup checklist."
        )


def _require_project() -> tuple[str, str]:
    settings = get_settings()
    if not settings.gcp_project_id:
        raise VertexNotConfigured()
    return settings.gcp_project_id, settings.gcp_region


@lru_cache
def get_client() -> AsyncAnthropicVertex:
    """Cached AsyncAnthropicVertex client for Claude generation calls."""
    project_id, region = _require_project()
    return AsyncAnthropicVertex(project_id=project_id, region=region)


async def embed_texts(texts: list[str], model: str = "text-embedding-005") -> list[list[float]]:
    """Embed a batch of texts via Vertex AI, returning one vector per input text.

    Used by the ingestion pipeline (plan §5, step 5 "index it") for chunk and candidate
    embeddings, written to pgvector columns.
    """
    project_id, region = _require_project()

    def _sync_embed() -> list[list[float]]:
        # Imported lazily: vertexai.init() is process-global, so this only runs (and only
        # requires the dependency to be importable) when embeddings are actually used.
        import vertexai
        from vertexai.language_models import TextEmbeddingModel

        vertexai.init(project=project_id, location=region)
        embedding_model = TextEmbeddingModel.from_pretrained(model)
        embeddings = embedding_model.get_embeddings(texts)
        return [e.values for e in embeddings]

    return await anyio.to_thread.run_sync(_sync_embed)
