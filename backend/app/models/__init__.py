"""ORM models.

P6 ingestion (plans/ingestion.md §4 / §11.1, feature-pipeline-contract.md §2, §6): documents,
chunks, features, feature_versions, feature_relations, review_items, audit_events. Later phases
(registry readiness, task factory, runs, reviews, …) add their tables here.

Everything is re-exported so `from app.models import *` in migrations/env.py registers every
table on `Base.metadata`.
"""

from app.models._common import (
    DOC_TYPES,
    INGESTION_STATUSES,
    LIFECYCLE_STATES,
    RELATION_TYPES,
    REVIEW_KINDS,
    REVIEW_STATUSES,
)
from app.models.audit_event import AuditEvent
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.feature import Feature, FeatureRelation, FeatureVersion
from app.models.review_item import ReviewItem

__all__ = [
    "DOC_TYPES",
    "INGESTION_STATUSES",
    "LIFECYCLE_STATES",
    "RELATION_TYPES",
    "REVIEW_KINDS",
    "REVIEW_STATUSES",
    "AuditEvent",
    "Chunk",
    "Document",
    "Feature",
    "FeatureRelation",
    "FeatureVersion",
    "ReviewItem",
]
