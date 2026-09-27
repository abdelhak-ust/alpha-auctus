"""Shared column helpers and enum value sets for the MVP tables.

Enum-like columns are plain strings guarded by CHECK constraints (not Postgres ENUM types):
widening a CHECK is a one-line migration; an ENUM needs ALTER TYPE gymnastics.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

# plans/mvp-v0.md — documents.status
DOCUMENT_STATUSES: tuple[str, ...] = (
    "uploaded",
    "converting",
    "extracting",
    "analysing",
    "ready",
    "failed",
)

# plans/mvp-v0.md — features.status
FEATURE_STATUSES: tuple[str, ...] = (
    "extracted",
    "analysed",
    "needs_clarification",
    "clarified",
    "planning",
    "tasks_ready",
)

# Chat workflow UX — features.review_status (human review, not pipeline status)
FEATURE_REVIEW_STATUSES: tuple[str, ...] = ("pending", "approved", "rejected")

# plans/mvp-v0.md — feature_questions.status
QUESTION_STATUSES: tuple[str, ...] = ("open", "answered", "skipped")

# plans/mvp-v0.md — tasks.status
TASK_STATUSES: tuple[str, ...] = ("draft", "approved", "on_board")

CHAT_ROLES: tuple[str, ...] = ("ai", "pm")

# Optional chat_messages.kind — NULL is allowed (treated as text by the API)
CHAT_KINDS: tuple[str, ...] = ("progress", "decision", "question", "text")

PRIORITIES: tuple[str, ...] = ("P0", "P1", "P2", "P3")

ESTIMATES: tuple[str, ...] = ("S", "M", "L")


def check_in(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    """CHECK (<column> IN (...)) with an explicit constraint name."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=name)


def uuid_pk():
    return mapped_column(Uuid, primary_key=True, default=__import__("uuid").uuid4)


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
