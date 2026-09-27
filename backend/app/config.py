"""Application settings, loaded from environment / backend/.env.

See .env.example for the full list of variables. Nothing here is secret by
itself — actual values (e.g. the real GCP project id) live in a local, gitignored
backend/.env (or the process env in deployment).
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ — so .env and relative paths resolve the same no matter the process cwd
# (uvicorn and pytest are started from different places).
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_name: str = "Nexus backend"
    environment: str = Field(default="development")
    api_prefix: str = "/api"

    # Database — Postgres holds canonical records and the LangGraph checkpointer tables.
    database_url: str = Field(
        default="postgresql+asyncpg://localhost/nexus_dev",
        description="Async SQLAlchemy DSN, e.g. postgresql+asyncpg://user:pass@host/db",
    )

    # AI — Gemini via Vertex AI, reached only through agents/llm.py (LangChain chat model).
    # Auth is Application Default Credentials (`gcloud auth application-default login`
    # locally; a service account when deployed) — no API key.
    gcp_project_id: str = Field(
        default="",
        description="GCP project id hosting Vertex AI. Required for any AI call to work. "
        "Set in backend/.env (gitignored), not here — this stays blank so a real project id "
        "never lands in a committed file.",
    )
    vertex_location: str = Field(
        default="us-central1",
        description="Vertex AI location for the Gemini model.",
    )
    gemini_model: str = Field(default="gemini-2.5-pro")
    google_genai_use_vertexai: bool = Field(
        default=True,
        description="Must stay true: Gemini is reached via Vertex AI, not the "
        "Gemini Developer API. Maps to GOOGLE_GENAI_USE_VERTEXAI.",
    )

    # Uploads — raw document blobs on the local filesystem.
    blob_dir: str = Field(default="./data/blobs")
    max_upload_mb: int = Field(default=25)

    # Document graph — chunking (plans/mvp-v0.md)
    extract_chunk_chars: int = Field(default=40_000)
    chunk_overlap_chars: int = Field(default=1_500)

    # Agent bounds
    agent_concurrency: int = Field(default=4)
    max_questions_per_feature: int = Field(default=5)
    analyst_max_steps: int = Field(default=8)
    max_follow_ups_per_feature: int = Field(default=2)
    llm_max_retries: int = Field(default=3)

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
