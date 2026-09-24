"""Source — an ingested artifact (upload, transcript, email, ticket, sheet row).

Matches the `WebSource` shape in client/src/types.ts. `project_id` is a plain indexed string
(matches the existing app's `proj-<timestamp>` id convention in client/server.ts) — there is no
`Project` model in this backend yet, so no FK constraint; adding one is out of scope for the
ingestion plan (plans/ingestion.md's impact analysis) and belongs to whichever phase actually
owns projects.
"""

from datetime import datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Vertex AI's text-embedding-005 default output dimensionality.
EMBEDDING_DIM = 768


def _source_id() -> str:
    return f"src-{uuid4().hex[:12]}"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_source_id)
    project_id: Mapped[str] = mapped_column(String, index=True)
    type: Mapped[str] = mapped_column(String)  # upload | sheet | transcript | email | ticket
    name: Mapped[str] = mapped_column(String)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_ref: Mapped[str | None] = mapped_column(String, nullable=True)  # blob path/key
    checksum: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="synced")
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class Chunk(Base):
    """The provenance unit — every downstream citation traces back to one chunk's exact
    character offsets into its source. Not in architecture.md's original model list; required
    to actually "capture all details" (plans/ingestion.md)."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(String)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    source: Mapped[Source] = relationship(back_populates="chunks")
