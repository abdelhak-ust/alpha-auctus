"""AI provider adapter — Gemini via Vertex AI only (plans/feature-pipeline-contract.md §1).

Wraps the `google-genai` SDK (Vertex mode, Application Default Credentials) behind two
functions, so callers in ingest/, registry/, contracts/, … never touch the SDK directly:

    from app import ai

    result = await ai.generate_json(prompt, MySchema, system="...")   # -> MySchema
    vectors = await ai.embed_texts(texts, task_type="RETRIEVAL_DOCUMENT")

Call through the module (`ai.generate_json`) so tests can monkeypatch `app.ai.*` — tests mock
these two functions, never the SDK (plans/ingestion.md §11.1).
"""

from app.ai.vertex import (
    AIResponseInvalid,
    EmbeddingTaskType,
    VertexNotConfigured,
    embed_texts,
    generate_json,
    get_client,
)

__all__ = [
    "AIResponseInvalid",
    "EmbeddingTaskType",
    "VertexNotConfigured",
    "embed_texts",
    "generate_json",
    "get_client",
]
