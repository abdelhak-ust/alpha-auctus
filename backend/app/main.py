"""Nexus backend — FastAPI entrypoint.

Phase P0 (foundation): this app currently exposes only a health/readiness
check. It exists so the real Postgres+pgvector substrate, DB session
handling, and project layout are in place before P1 (Task Contract) starts
adding real routes/models. See the phased plan for what fills in each
package under app/ (ai, ingest, engine, contracts, validate, runner, mcp,
github_app, registry, ws, queue).

The existing client/ app keeps talking to client/server.ts during the
transition; nothing here is wired into it yet.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)


@app.api_route("/", methods=["GET", "HEAD"])
async def root() -> dict:
    """Bare-origin landing — mainly so readiness probes (and a human hitting the
    origin directly) get a 200 with something useful instead of a 404. Real UI lives in
    client/; this is an API-only service. Handles HEAD explicitly: FastAPI doesn't
    auto-add it for a plain @app.get, and readiness probes commonly use HEAD."""
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
