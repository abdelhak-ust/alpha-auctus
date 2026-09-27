"""Shared column helpers and enum value sets for the ingestion tables.

Enum-like columns are plain strings guarded by CHECK constraints (not Postgres ENUM types):
the lifecycle grows as the registry/task-factory stages land, and a CHECK is a one-line
migration to widen, where an ENUM needs ALTER TYPE gymnastics.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

# ingestion.md §4.3 / §11.1 IngestionStatus
INGESTION_STATUSES: tuple[str, ...] = (
    "pending",
    "parsed",
    "extracted",
    "consolidated",
    "done",
    "failed",
)

# ingestion.md §4.3 (doc_type); contract §5: chat answers are documents with doc_type "chat".
DOC_TYPES: tuple[str, ...] = ("upload", "transcript", "email", "ticket", "sheet", "chat")

# feature-pipeline-contract.md §3 / §11.1 FeatureLifecycle
LIFECYCLE_STATES: tuple[str, ...] = (
    "extracted",
    "consolidated",
    "conflicted",
    "classified",
    "assessing",
    "awaiting_answers",
    "answered",
    "dev_ready",
    "overridden",
    "stale",
    "in_breakdown",
    "needs_review",
    "broken_down",
)

# contract §2 feature_relations.relation_type
RELATION_TYPES: tuple[str, ...] = ("depends_on", "extends", "conflicts_with")

# §11.1 review_items
REVIEW_KINDS: tuple[str, ...] = ("conflict", "sweep_flag")
REVIEW_STATUSES: tuple[str, ...] = ("open", "approved", "dismissed")


def check_in(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    """CHECK (<column> IN (...)) with an explicit constraint name."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=name)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
