"""The single seam between the ingest graph and `app.ai.generate_json`.

Always resolves `app.ai.generate_json` / `app.ai.embed_texts` at call time (module attribute
lookup), so tests patch `app.ai.*` and every ingest module sees the mock.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app import ai
from app.ingest.prompts import SYSTEM

T = TypeVar("T", bound=BaseModel)

EMBED_BATCH = 100


async def call_llm(prompt: str, schema: type[T]) -> T:
    result = await ai.generate_json(prompt, schema, system=SYSTEM)
    if isinstance(result, schema):
        return result
    return schema.model_validate(result if isinstance(result, dict) else result.model_dump())


async def embed(texts: list[str], task_type: str) -> list[list[float]]:
    """Batched embeddings (plans/ingestion.md §8 batching)."""
    vectors: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        if batch:
            vectors.extend(await ai.embed_texts(batch, task_type=task_type))
    return vectors
