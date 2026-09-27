"""The actual Vertex AI wiring behind app.ai's adapter interface — Gemini only.

Two capabilities (plans/ingestion.md §11.1 / §11.3), both through the `google-genai` SDK in
Vertex mode and authenticated via Application Default Credentials (no API key):

- `generate_json(prompt, schema, *, system=None)` — Gemini structured output, validated
  against a Pydantic model.
- `embed_texts(texts, *, task_type)` — Gemini embeddings, batched, `embedding_dim` long.

Both raise a clear, actionable `VertexNotConfigured` rather than a confusing SDK traceback when
`gcp_project_id` isn't set — the product's "problem + cause + fix" convention
(ui_ux_design.md §7). Transient Vertex failures (429 / 5xx) are retried with exponential
backoff + jitter before surfacing.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import TYPE_CHECKING, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import get_settings

if TYPE_CHECKING:  # the SDK is only needed once a call is actually made
    from google import genai

logger = logging.getLogger(__name__)

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)

EmbeddingTaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]

# Retry policy for transient Vertex errors.
MAX_ATTEMPTS = 5
BASE_DELAY_S = 1.0
MAX_DELAY_S = 30.0
# Texts per embed request. Vertex caps instances per request; if the model rejects
# multi-text requests entirely we fall back to one text per call (§11.3).
EMBED_BATCH_SIZE = 100


class VertexNotConfigured(RuntimeError):
    """Raised when a Vertex AI call is attempted without GCP_PROJECT_ID configured."""

    def __init__(self):
        super().__init__(
            "Vertex AI isn't configured: GCP_PROJECT_ID is empty. Set GCP_PROJECT_ID (and "
            "VERTEX_LOCATION if not us-central1) in backend/.env, and run "
            "`gcloud auth application-default login` so the backend can authenticate. "
            "See the plan's §0.3 GCP setup checklist."
        )


class AIResponseInvalid(ValueError):
    """Gemini answered, but not with JSON matching the requested schema."""

    def __init__(self, schema: type[BaseModel], cause: str):
        super().__init__(
            f"Gemini's response didn't match the {schema.__name__} schema: {cause}. "
            "Retry the step; if it keeps failing, check the prompt/schema pair."
        )


def _require_project() -> tuple[str, str]:
    settings = get_settings()
    if not settings.gcp_project_id:
        raise VertexNotConfigured()
    return settings.gcp_project_id, settings.vertex_location


@lru_cache
def _client_for(project_id: str, location: str) -> genai.Client:
    from google import genai

    return genai.Client(vertexai=True, project=project_id, location=location)


def get_client() -> genai.Client:
    """Cached `google.genai.Client` in Vertex mode (ADC auth) for the configured project."""
    project_id, location = _require_project()
    return _client_for(project_id, location)


def _is_retryable(exc: BaseException) -> bool:
    from google.genai import errors

    if isinstance(exc, errors.APIError):
        return exc.code == 429 or (exc.code or 0) >= 500
    return False


async def _with_retry(call: Callable[[], Awaitable[T]], *, what: str) -> T:
    """Run `call`, retrying 429/5xx with exponential backoff + full jitter."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await call()
        except Exception as exc:
            if attempt == MAX_ATTEMPTS or not _is_retryable(exc):
                raise
            delay = min(MAX_DELAY_S, BASE_DELAY_S * 2 ** (attempt - 1))
            delay = random.uniform(0, delay)
            logger.warning(
                "Vertex %s failed (attempt %d/%d): %s — retrying in %.1fs",
                what, attempt, MAX_ATTEMPTS, exc, delay,
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


async def generate_json(prompt: str, schema: type[M], *, system: str | None = None) -> M:
    """Ask Gemini for JSON conforming to `schema` and return it as a validated `schema`.

    Raises `VertexNotConfigured` when no project is set, `AIResponseInvalid` when the reply
    doesn't validate, and the SDK's `APIError` for non-transient Vertex failures.
    """
    client = get_client()
    settings = get_settings()

    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_schema=schema,
        temperature=0.0,
    )

    response = await _with_retry(
        lambda: client.aio.models.generate_content(
            model=settings.gemini_model, contents=prompt, config=config
        ),
        what="generate_json",
    )

    usage = getattr(response, "usage_metadata", None)
    if usage is not None:
        logger.info(
            "gemini generate_json schema=%s prompt_tokens=%s output_tokens=%s",
            schema.__name__,
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
        )

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    text = getattr(response, "text", None)
    if not text:
        raise AIResponseInvalid(schema, "empty response")
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        raise AIResponseInvalid(schema, str(exc)) from exc


async def embed_texts(texts: list[str], *, task_type: EmbeddingTaskType) -> list[list[float]]:
    """Embed `texts` with Gemini, returning one `embedding_dim`-length vector per input.

    Batched (`EMBED_BATCH_SIZE` per request); if the model rejects multi-text requests, falls
    back to one request per text for the rest of the call.
    """
    if not texts:
        return []
    client = get_client()
    settings = get_settings()

    from google.genai import errors, types

    config = types.EmbedContentConfig(
        task_type=task_type, output_dimensionality=settings.embedding_dim
    )

    async def _embed(batch: list[str]) -> list[list[float]]:
        response = await _with_retry(
            lambda: client.aio.models.embed_content(
                model=settings.gemini_embedding_model, contents=batch, config=config
            ),
            what="embed_texts",
        )
        vectors = [list(e.values or []) for e in (response.embeddings or [])]
        if len(vectors) != len(batch):
            raise ValueError(
                f"Vertex returned {len(vectors)} embeddings for {len(batch)} texts."
            )
        return vectors

    out: list[list[float]] = []
    batch_size = EMBED_BATCH_SIZE
    i = 0
    while i < len(texts):
        batch = texts[i : i + batch_size]
        try:
            out.extend(await _embed(batch))
        except errors.ClientError as exc:
            # 400 on a multi-text request: the model doesn't accept batches — go one by one.
            if len(batch) > 1 and exc.code == 400:
                logger.info("Embedding model rejected a batch (%s); falling back to 1/call", exc)
                batch_size = 1
                continue
            raise
        i += len(batch)

    for v in out:
        if len(v) != settings.embedding_dim:
            raise ValueError(
                f"Embedding has {len(v)} dims but EMBEDDING_DIM is {settings.embedding_dim}."
            )
    return out
