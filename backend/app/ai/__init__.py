"""AI provider adapter — Vertex AI only, per the plan's §0.3/§5 decisions.

Wraps `AnthropicVertex` (generation: extraction, classification, authoring, validation) and
Vertex AI embeddings behind one import, so callers in engine/, contracts/, validate/, ingest/
never touch the SDKs directly. Auth is Application Default Credentials — no API key, no
BYO-key posture (architecture.md D3's original raw-Anthropic-API BYO-key seam is superseded
for this build; see the plan's resolved decision #6).

Usage:
    from app.ai import get_client, embed_texts

    client = get_client()
    resp = client.messages.create(model="claude-...", ...)

    vectors = embed_texts(["some chunk text", "another chunk"])
"""

from app.ai.vertex import VertexNotConfigured, embed_texts, get_client

__all__ = ["get_client", "embed_texts", "VertexNotConfigured"]
