"""documents — one row per ingested file (ingestion.md §4.3)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import DOC_TYPES, INGESTION_STATUSES, check_in, uuid_pk


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        # Idempotency: the same bytes uploaded twice to one project are one document.
        UniqueConstraint("project_id", "content_hash", name="uq_documents_project_content_hash"),
        check_in("doc_type", DOC_TYPES, "ck_documents_doc_type"),
        check_in("ingestion_status", INGESTION_STATUSES, "ck_documents_ingestion_status"),
    )

    doc_id: Mapped[uuid.UUID] = uuid_pk()
    # Projects live in the Node SQLite store (client/db/) — plain string, no FK.
    project_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    doc_type: Mapped[str] = mapped_column(String, nullable=False, default="upload")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex
    filename: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    blob_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # Free-form upload metadata (uploader, original path, …). `metadata` is reserved by
    # SQLAlchemy's declarative base, hence the name.
    upload_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ingestion_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # Problem + cause + fix text when ingestion_status = failed (surfaced as IngestDocument.error).
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
