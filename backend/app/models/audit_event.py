"""audit_events — one append-only audit log for all three graphs (contract §6).

Written via `app.graph.record_audit(...)`; never updated or deleted.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    # No FK: the log must outlive the features it describes.
    feature_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    graph: Mapped[str] = mapped_column(String, nullable=False)  # ingest | readiness | breakdown
    node: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
