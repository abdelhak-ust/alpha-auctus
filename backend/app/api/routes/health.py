"""Health check — proves the app is up and can reach its dependencies."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness only — no dependency calls. For orchestrators / uptime checks."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> dict:
    """Readiness — verifies the database (and pgvector) are actually reachable."""
    result = await db.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
    vector_version = result.scalar_one_or_none()
    return {
        "status": "ok",
        "database": "connected",
        "pgvector": vector_version or "not installed",
    }
