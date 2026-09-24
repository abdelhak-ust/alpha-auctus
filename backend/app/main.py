"""Nexus backend — FastAPI entrypoint.

P0 (foundation) built the substrate. P6 (ingestion, plans/ingestion.md) adds the first real
feature: parse/chunk/extract/embed with real provenance, reached via `client/server.ts`
forwarding its `/api/sources/upload` and `/api/ingest/resolve` handlers here. Everything else
under app/ (engine, contracts, validate, runner, mcp, github_app, registry, ws, queue) is
still an empty stub with a docstring naming its phase.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, ingestion
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
app.include_router(ingestion.router, prefix=settings.api_prefix)


def _root() -> dict:
    """Bare-origin landing — mainly so readiness probes (and a human hitting the
    origin directly) get a 200 with something useful instead of a 404. Real UI lives in
    client/; this is an API-only service."""
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }


# Two separate routes (not one @app.api_route(methods=["GET", "HEAD"])) — FastAPI's
# auto-generated operation IDs collide across methods on a single multi-method route,
# which trips its own "Duplicate Operation ID" warning; explicit ids on two routes avoid it.
@app.get("/", operation_id="root")
async def root_get() -> dict:
    return _root()


@app.head("/", operation_id="root_head")
async def root_head() -> dict:
    return _root()
