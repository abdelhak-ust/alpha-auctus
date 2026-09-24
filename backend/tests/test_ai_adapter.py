"""The AI adapter must fail clearly, not with a confusing SDK traceback, when Vertex AI
isn't configured yet (plan §0.3 — GCP_PROJECT_ID is blank until the account-level setup is
done). Once a real project id is configured this becomes an integration concern instead;
these tests only cover the graceful-failure contract.
"""

import pytest

from app.ai import VertexNotConfigured, embed_texts, get_client
from app.config import get_settings


@pytest.fixture(autouse=True)
def _unconfigured_gcp_project(monkeypatch):
    """Force GCP_PROJECT_ID empty regardless of the local .env, and clear the settings
    cache so app.config.get_settings() picks it up."""
    monkeypatch.setenv("GCP_PROJECT_ID", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_get_client_without_project_raises_actionable_error():
    with pytest.raises(VertexNotConfigured, match="GCP_PROJECT_ID"):
        get_client()


async def test_embed_texts_without_project_raises_actionable_error():
    with pytest.raises(VertexNotConfigured, match="GCP_PROJECT_ID"):
        await embed_texts(["hello"])
