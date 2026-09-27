"""features / feature_versions / feature_relations (feature-pipeline-contract.md §2).

A new `feature_versions` row is the only way a feature's content changes (contract §4).
`features.feature_id` is also the Qdrant point id in the `features` collection.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._common import (
    LIFECYCLE_STATES,
    RELATION_TYPES,
    check_in,
    created_at_col,
    uuid_pk,
)


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (check_in("lifecycle_state", LIFECYCLE_STATES, "ck_features_lifecycle_state"),)

    feature_id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Circular with feature_versions.feature_id — use_alter makes the FK a separate ALTER.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "feature_versions.version_id",
            use_alter=True,
            name="fk_features_current_version_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    lifecycle_state: Mapped[str] = mapped_column(
        String, nullable=False, default="extracted", index=True
    )
    # Written by the registry stage (FEATURE_REGISTRY.md); ingestion leaves them NULL.
    classification: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    readiness: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    override: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    current_version: Mapped["FeatureVersion | None"] = relationship(
        foreign_keys=[current_version_id], post_update=True, lazy="raise"
    )


class FeatureVersion(Base):
    __tablename__ = "feature_versions"
    __table_args__ = (
        UniqueConstraint("feature_id", "version_no", name="uq_feature_versions_feature_version_no"),
    )

    version_id: Mapped[uuid.UUID] = uuid_pk()
    feature_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("features.feature_id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)  # = factory spec_version
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # list of contract §5 source_ref dicts (snake_case keys):
    # {doc_id, doc_type, chunk_id, section, char_start, char_end, snippet}
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    # "ingest:<doc_id>" | "chat:<doc_id>" | "manual:<user_id>"
    created_from: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class FeatureRelation(Base):
    __tablename__ = "feature_relations"
    __table_args__ = (
        check_in("relation_type", RELATION_TYPES, "ck_feature_relations_relation_type"),
    )

    feature_id_a: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("features.feature_id", ondelete="CASCADE"), primary_key=True
    )
    feature_id_b: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("features.feature_id", ondelete="CASCADE"), primary_key=True, index=True
    )
    relation_type: Mapped[str] = mapped_column(String, primary_key=True)
