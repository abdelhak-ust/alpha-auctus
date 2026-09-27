"""LLM factory: override hook and Vertex-not-configured error."""

import pytest

from app.agents.llm import VertexNotConfigured, get_chat_model, set_chat_model_override
from app.config import get_settings
from tests.fakes import FakeChatModel


def test_override_is_returned():
    fake = FakeChatModel()
    set_chat_model_override(fake)
    try:
        assert get_chat_model() is fake
    finally:
        set_chat_model_override(None)


def test_unconfigured_raises_actionable_error(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "")
    get_settings.cache_clear()
    set_chat_model_override(None)
    try:
        with pytest.raises(VertexNotConfigured) as exc:
            get_chat_model()
        err = exc.value.as_error()
        assert {"problem", "cause", "fix"} <= set(err)
        assert "GCP_PROJECT_ID" in err["cause"]
    finally:
        get_settings.cache_clear()
