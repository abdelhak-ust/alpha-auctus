"""review_items — the human review queue for ingestion (ingestion.md §7, §11.1).

`conflict`: payload holds both versions (current + proposed) with their source_refs and the
ranked candidates. `sweep_flag`: a completeness-sweep mention nothing consolidated covered.
Surfaced through `GET /review-queue` as `IngestItem`.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import (
    REVIEW_KINDS,
    REVIEW_STATUSES,
    check_in,
    created_at_col,
    uuid_pk,
)


class ReviewItem(Base):
    __tablename__ = "review_items"
    __table_args__ = (
        check_in("kind", REVIEW_KINDS, "ck_review_items_kind"),
        check_in("status", REVIEW_STATUSES, "ck_review_items_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    feature_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("features.feature_id", ondelete="CASCADE"), index=True, nullable=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.doc_id", ondelete="CASCADE"), index=True, nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="open", index=True)
    created_at: Mapped[datetime] = created_at_col()
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)
