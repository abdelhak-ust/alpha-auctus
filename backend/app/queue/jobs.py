"""Job functions owned by the queue package itself.

`readiness_run` is a registered **no-op stub** until stage 2 (the registry's readiness graph,
plans/FEATURE_REGISTRY.md) exists: stage 1 hands off to it per consolidated feature, and the
stub just logs and leaves an audit row so the hand-off is visible.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def readiness_run(ctx: dict[str, Any], feature_id: str, project_id: str, **_: Any) -> None:
    """Stage-2 hand-off stub — log + `audit_events` row, nothing else."""
    from app.db.session import async_session_factory
    from app.graph import record_audit

    session_factory = ctx.get("session_factory") or async_session_factory
    logger.info("readiness_run stub: feature=%s project=%s (stage 2 not built yet)",
                feature_id, project_id)
    async with session_factory() as session:
        await record_audit(
            session,
            project_id=project_id,
            feature_id=feature_id,
            graph="readiness",
            node="readiness_run",
            type="stub_received",
            detail={"note": "stage 2 (readiness) not implemented yet; hand-off recorded"},
        )
        await session.commit()
