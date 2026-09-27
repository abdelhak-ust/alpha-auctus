"""ORM models.

MVP v0 (plans/mvp-v0.md): documents, features, feature_questions, chat_messages, tasks,
audit_events. P6 tables (chunks, feature_versions, feature_relations, review_items) are gone.

Everything is re-exported so `from app.models import *` in migrations/env.py registers every
table on `Base.metadata`.
"""

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
)
from app.models.audit_event import AuditEvent
from app.models.mvp import ChatMessage, Document, Feature, FeatureQuestion, Task

__all__ = [
    "CHAT_KINDS",
    "CHAT_ROLES",
    "DOCUMENT_STATUSES",
    "ESTIMATES",
    "FEATURE_REVIEW_STATUSES",
    "FEATURE_STATUSES",
    "PRIORITIES",
    "QUESTION_STATUSES",
    "TASK_STATUSES",
    "AuditEvent",
    "ChatMessage",
    "Document",
    "Feature",
    "FeatureQuestion",
    "Task",
]
