"""Audit trail helper — every graph writes its decisions to `audit_events`
(plans/feature-pipeline-contract.md §6)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent


async def record_audit(
    session: AsyncSession,
    *,
    project_id: str,
    feature_id: uuid.UUID | str | None,
    graph: str,
    node: str,
    type: str,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    """Add one `audit_events` row and flush it (so it gets its id).

    Never commits — the caller owns the transaction, so the audit row lands atomically with
    whatever change it describes.
    """
    if isinstance(feature_id, str):
        feature_id = uuid.UUID(feature_id)
    event = AuditEvent(
        project_id=project_id,
        feature_id=feature_id,
        graph=graph,
        node=node,
        type=type,
        detail=detail or {},
    )
    session.add(event)
    await session.flush()
    return event
