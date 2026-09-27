"""The only place a chat model is built (plans/mvp-v0.md).

Gemini on Vertex AI is reached through LangChain. Tests inject a scripted fake through
`set_chat_model_override`. Pipeline code never imports `google.genai` or constructs a
chat model itself.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

_override: BaseChatModel | None = None


class VertexNotConfigured(RuntimeError):
    """Raised when a Vertex AI call is attempted without GCP_PROJECT_ID configured."""

    def __init__(self) -> None:
        super().__init__(
            "Vertex AI isn't configured: GCP_PROJECT_ID is empty. Set GCP_PROJECT_ID (and "
            "VERTEX_LOCATION if not us-central1) in backend/.env, and run "
            "`gcloud auth application-default login` so the backend can authenticate. "
            "See the plan's §0.3 GCP setup checklist."
        )

    def as_error(self) -> dict[str, str]:
        return {
            "problem": "Vertex AI isn't configured.",
            "cause": "GCP_PROJECT_ID is empty, so the agents cannot call Gemini.",
            "fix": "Set GCP_PROJECT_ID (and VERTEX_LOCATION if not us-central1) in "
            "backend/.env, run `gcloud auth application-default login`, then retry.",
        }


def set_chat_model_override(model: BaseChatModel | None) -> None:
    """Tests inject a scripted fake through this hook. Pass None to restore the real factory."""
    global _override
    _override = model


def _require_project() -> tuple[str, str, str]:
    settings = get_settings()
    if not settings.gcp_project_id:
        raise VertexNotConfigured()
    return settings.gcp_project_id, settings.vertex_location, settings.gemini_model


def get_chat_model() -> BaseChatModel:
    """Return the process chat model (or the test override).

    Prefers `ChatGoogleGenerativeAI` only when it actually has Vertex mode
    (`vertexai` is a constructor field). langchain-google-genai 3.x warns and
    swallows `vertexai`/`project`/`location` into model_kwargs, then calls the
    Gemini Developer API — so we fall back to `ChatVertexAI`.
    """
    if _override is not None:
        return _override

    project_id, location, model_name = _require_project()
    settings = get_settings()
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = (
        "TRUE" if settings.google_genai_use_vertexai else "FALSE"
    )
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
    kwargs = {
        "model": model_name,
        "project": project_id,
        "location": location,
        "temperature": 0.2,
        "max_retries": settings.llm_max_retries,
    }

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI

        fields = set(ChatGoogleGenerativeAI.model_fields)
        if "vertexai" in fields:
            return ChatGoogleGenerativeAI(vertexai=True, **kwargs)
    except (TypeError, ImportError, ValueError):
        pass

    from langchain_google_vertexai import ChatVertexAI

    return ChatVertexAI(**kwargs)
