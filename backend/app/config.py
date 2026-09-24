"""Application settings, loaded from environment / .env.

See .env.example for the full list of variables. Nothing here is secret by
itself — actual keys live in a local, gitignored .env (or the process env in
deployment).
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "Nexus backend"
    environment: str = Field(default="development")
    api_prefix: str = "/api"

    # Database (P0: Postgres + pgvector — see nexus_dev created locally)
    database_url: str = Field(
        default="postgresql+asyncpg://localhost/nexus_dev",
        description="Async SQLAlchemy DSN, e.g. postgresql+asyncpg://user:pass@host/db",
    )

    # Background jobs — local dev only (arq/Redis). Deployed environments use Cloud Tasks
    # instead (see plan §0.3); this field is simply unused there.
    redis_url: str = Field(default="redis://localhost:6379/0")

    # AI — Vertex AI only, for both local dev and deployed (plan §0.3/§5: AnthropicVertex for
    # generation, Vertex embeddings for indexing). Auth is via Application Default
    # Credentials (`gcloud auth application-default login` locally; a service account when
    # deployed) — there is no API key to manage here, unlike architecture.md's original
    # BYO-key-to-the-raw-Anthropic-API posture.
    gcp_project_id: str = Field(
        default="",
        description="GCP project id hosting Vertex AI. Required for any AI call to work.",
    )
    gcp_region: str = Field(
        default="us-east5",
        description="Vertex AI region — must be one where the needed Claude models are"
        " enabled in Model Garden for gcp_project_id.",
    )

    # CORS — the existing client dev server (Vite) runs on :3000
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
