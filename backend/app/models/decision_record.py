"""DecisionRecord — an atomic, normalized decision statement (the conflict anchor).

architecture.md: "a DecisionRecord is *not* the same row as the Item it came from. Decisions
are extracted and normalized into atomic, polarity-bearing statements... so the engine can
reason about contradiction independently of how the original text was phrased."

Scope decision for this pass (plans/ingestion.md): unlike extracted Items, which land in a
human-reviewed queue (IngestCandidate → approve → Item — the existing ingestQueue UX), there
is no equivalent review UI for decisions in the frontend today (Settings only supports adding
one by hand). Extracted DecisionRecords are written directly here, `status="proposed"`, fully
cited (source_id + chunk_id + verbatim statement) — ready for P5's conflict engine to consume
and for a future decisions-review UI to gate. Not silently promoted to "active"; that requires
either that future UI or an explicit decision from the human posture this project is building
toward (principle: human is the final approver).
"""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.source import EMBEDDING_DIM


class DecisionRecord(Base):
    __tablename__ = "decision_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    statement: Mapped[str] = mapped_column(String)  # atomic "we will / will not X"
    polarity: Mapped[str] = mapped_column(String)  # "affirm" | "negate"
    affected_entities: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    source_fk = ForeignKey("sources.id", ondelete="SET NULL")
    source_id: Mapped[str | None] = mapped_column(source_fk, nullable=True)
    chunk_fk = ForeignKey("chunks.id", ondelete="SET NULL")
    chunk_id: Mapped[int | None] = mapped_column(chunk_fk, nullable=True)
    snippet: Mapped[str] = mapped_column(String)  # verbatim quote from the chunk
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # status: proposed | active | superseded | deprecated
    status: Mapped[str] = mapped_column(String, default="proposed")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
