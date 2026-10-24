"""FastAPI application factory and process-level endpoints."""

import logging
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app import __version__
from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.db import get_db
from app.core.logging import setup_logging
from app.schemas.health import HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Liveness probe: the process is up. Touches no external systems."""
        return HealthResponse(
            status="ok",
            service="api",
            version=__version__,
            environment=settings.environment,
        )

    @app.get("/health/ready", response_model=ReadinessResponse, tags=["health"])
    def ready(db: Annotated[Session, Depends(get_db)]) -> ReadinessResponse:
        """Readiness probe: the database answers a trivial query."""
        db.execute(text("SELECT 1"))
        return ReadinessResponse(
            status="ok",
            service="api",
            version=__version__,
            environment=settings.environment,
            database="ok",
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": f"http_{exc.status_code}",
                    "message": str(exc.detail),
                    "details": None,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred.",
                    "details": None,
                }
            },
        )

    return app


app = create_app()
