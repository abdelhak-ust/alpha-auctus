"""MVP v0 tables (plans/mvp-v0.md): documents, features, feature_questions, chat_messages, tasks.

Projects live in the Node SQLite store — every table carries a `project_id` string, no FK.
`audit_events` is unchanged (app.models.audit_event).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models._common import (
    CHAT_KINDS,
    CHAT_ROLES,
    DOCUMENT_STATUSES,
    ESTIMATES,
    FEATURE_REVIEW_STATUSES,
    FEATURE_STATUSES,
    PRIORITIES,
    QUESTION_STATUSES,
    TASK_STATUSES,
    check_in,
    created_at_col,
    uuid_pk,
)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("project_id", "content_hash", name="uq_documents_project_content_hash"),
        check_in("status", DOCUMENT_STATUSES, "ck_documents_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    blob_path: Mapped[str | None] = mapped_column(String, nullable=True)
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="uploaded", index=True)
    # {step, done, total} — e.g. {step: "extracting", done: 2, total: 5}
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # JSON {problem, cause, fix} when status = failed, else null.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    features: Mapped[list[Feature]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="raise"
    )


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (
        check_in("status", FEATURE_STATUSES, "ck_features_status"),
        check_in("review_status", FEATURE_REVIEW_STATUSES, "ck_features_review_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # FeatureDetails JSON (description, user_roles, requirements, AC, …)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # [{quote, verified, char_start?, char_end?, origin?}]
    source_quotes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="extracted", index=True)
    # Human review for task generation — independent of pipeline `status`.
    review_status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending", index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="features", lazy="raise")
    questions: Mapped[list[FeatureQuestion]] = relationship(
        back_populates="feature", cascade="all, delete-orphan", lazy="raise",
        order_by="FeatureQuestion.ordinal",
    )
    tasks: Mapped[list[Task]] = relationship(
        back_populates="feature", cascade="all, delete-orphan", lazy="raise",
        order_by="Task.ordinal",
    )


class FeatureQuestion(Base):
    __tablename__ = "feature_questions"
    __table_args__ = (check_in("status", QUESTION_STATUSES, "ck_feature_questions_status"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    feature_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("features.id", ondelete="CASCADE"), index=True, nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    why: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_field: Mapped[str] = mapped_column(String, nullable=False, default="")
    is_follow_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open", index=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    feature: Mapped[Feature] = relationship(back_populates="questions", lazy="raise")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        check_in("role", CHAT_ROLES, "ck_chat_messages_role"),
        check_in("kind", CHAT_KINDS, "ck_chat_messages_kind"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    question_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    feature_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # progress | decision | question | text — optional; NULL is treated as text.
    kind: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = created_at_col()


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        check_in("status", TASK_STATUSES, "ck_tasks_status"),
        check_in("priority", PRIORITIES, "ck_tasks_priority"),
        check_in("estimate", ESTIMATES, "ck_tasks_estimate"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    feature_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("features.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    area: Mapped[str] = mapped_column(String, nullable=False, default="")
    priority: Mapped[str] = mapped_column(String, nullable=False, default="P2")
    # [{given, when, then}]
    acceptance_criteria: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    estimate: Mapped[str] = mapped_column(String, nullable=False, default="M")
    # list of requirement / PM-answer strings this task traces to
    traces_to: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    # ordered implementation checklist (3–8 items)
    subtasks: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    # human-checkable exit checks (3–6 items)
    definition_of_done: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft", index=True)
    board_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    feature: Mapped[Feature] = relationship(back_populates="tasks", lazy="raise")
