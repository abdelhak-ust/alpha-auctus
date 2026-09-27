"""Application settings, loaded from environment / backend/.env.

See .env.example for the full list of variables. Nothing here is secret by
itself — actual values (e.g. the real GCP project id) live in a local, gitignored
backend/.env (or the process env in deployment).

The feature-pipeline settings below are frozen by plans/ingestion.md §11.1 / §11.3.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ — so .env and relative paths resolve the same no matter the process cwd
# (uvicorn, the arq worker, and pytest are all started from different places).
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_name: str = "Nexus backend"
    environment: str = Field(default="development")
    api_prefix: str = "/api"

    # Database — Postgres holds canonical records (and the LangGraph checkpointer tables).
    database_url: str = Field(
        default="postgresql+asyncpg://localhost/nexus_dev",
        description="Async SQLAlchemy DSN, e.g. postgresql+asyncpg://user:pass@host/db",
    )

    # Background jobs — local dev only (arq/Redis). Deployed environments use Cloud Tasks
    # instead (see plan §0.3); this field is simply unused there.
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Vector store — Qdrant. ":memory:" gives an in-process store (tests only).
    qdrant_url: str = Field(default="http://localhost:6333")

    # AI — Gemini via Vertex AI only (google-genai SDK in Vertex mode), both local and
    # deployed. Auth is Application Default Credentials (`gcloud auth
    # application-default login` locally; a service account when deployed) — no API key.
    gcp_project_id: str = Field(
        default="",
        description="GCP project id hosting Vertex AI. Required for any AI call to work. "
        "Set in backend/.env (gitignored), not here — this stays blank so a real project id "
        "never lands in a committed file.",
    )
    vertex_location: str = Field(
        default="us-central1",
        description="Vertex AI location for the Gemini generation + embedding models.",
    )
    gemini_model: str = Field(default="gemini-2.5-pro")
    gemini_embedding_model: str = Field(default="gemini-embedding-001")
    embedding_dim: int = Field(default=768)

    # Feature matching (plans/ingestion.md §9: 0.80 cosine, top-k 5, config-tunable).
    feature_match_threshold: float = Field(default=0.80)
    feature_match_top_k: int = Field(default=5)

    # Uploads — raw document blobs on the local filesystem (Cloud Storage when deployed).
    blob_dir: str = Field(default="./data/blobs")
    max_upload_mb: int = Field(default=25)

    # CORS — the existing client dev server (Vite) runs on :3000
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("blob_dir")
    @classmethod
    def _resolve_blob_dir(cls, value: str) -> str:
        """Relative blob_dir is relative to backend/, not to the process cwd."""
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = (BACKEND_DIR / path).resolve()
        return str(path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
