"""Nexus backend — FastAPI entrypoint.

MVP v0 (plans/mvp-v0.md): document → features → clarification → tasks, under
/api/projects/{projectId}/…. The client calls this API directly (CORS for the Vite
dev origin); board cards stay on client/server.ts.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import health, mvp
from app.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await mvp.recover_stuck_documents()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(mvp.router, prefix=settings.api_prefix)
app.add_exception_handler(RequestValidationError, mvp.validation_error_handler)
app.add_exception_handler(StarletteHTTPException, mvp.http_error_handler)
app.add_exception_handler(HTTPException, mvp.http_error_handler)


def _root() -> dict:
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }


@app.get("/", operation_id="root")
async def root_get() -> dict:
    return _root()


@app.head("/", operation_id="root_head")
async def root_head() -> dict:
    return _root()
