"""IngestCandidate — the persisted form of the frontend's `IngestItem` (client/src/types.ts).

Kept separate from `Item` until approved, exactly like today's `ingestQueue` -> `items` move
in client/server.ts (`/api/ingest/resolve`). `verdict` mirrors `VerdictDetail`'s shape as JSON
(the provisional placeholder verdict — see plans/ingestion.md's "Conflict-check coupling").
"""

from datetime import datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.source import EMBEDDING_DIM


def _candidate_id() -> str:
    return f"ingest-{uuid4().hex[:12]}"


class IngestCandidate(Base):
    __tablename__ = "ingest_candidates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_candidate_id)
    project_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String, default="")
    entity_tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    priority: Mapped[str] = mapped_column(String, default="P2")  # P0-P3, matches Priority
    source_fk = ForeignKey("sources.id", ondelete="CASCADE")
    source_id: Mapped[str] = mapped_column(source_fk, index=True)
    chunk_fk = ForeignKey("chunks.id", ondelete="SET NULL")
    chunk_id: Mapped[int | None] = mapped_column(chunk_fk, nullable=True)
    snippet: Mapped[str] = mapped_column(String)  # verbatim quote from the chunk
    # status: pending | approved | dismissed
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    # verdict: VerdictDetail shape (client/src/types.ts) — see app/schemas/ingestion.py
    verdict: Mapped[dict] = mapped_column(JSON)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
