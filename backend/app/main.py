"""Nexus backend — FastAPI entrypoint.

Phase P0 (foundation): this app currently exposes only a health/readiness
check. It exists so the real Postgres+pgvector substrate, DB session
handling, and project layout are in place before P1 (Task Contract) starts
adding real routes/models. See the phased plan for what fills in each
package under app/ (ai, ingest, engine, contracts, validate, runner, mcp,
github_app, registry, ws, queue).

P6 (ingestion, plans/ingestion.md §11.1) adds the project-scoped ingestion API under
/api/projects/{projectId}/… (documents, features, review-queue). The client calls it directly
(CORS for the Vite dev origin); board data stays on client/server.ts.
"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
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
# 422s on the ingestion routes use the problem + cause + fix error shape.
app.add_exception_handler(RequestValidationError, ingestion.validation_error_handler)


def _root() -> dict:
    """Bare-origin landing — mainly so readiness probes (and a human hitting the
    origin directly) get a 200 with something useful instead of a 404. Real UI lives in
    client/; this is an API-only service."""
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }


# Two routes with explicit operation ids (not one @app.api_route(methods=["GET", "HEAD"])):
# FastAPI's auto-generated ids collide across methods on a multi-method route and it warns
# "Duplicate Operation ID". Readiness probes commonly use HEAD, so both are served.
@app.get("/", operation_id="root")
async def root_get() -> dict:
    return _root()


@app.head("/", operation_id="root_head")
async def root_head() -> dict:
    return _root()
