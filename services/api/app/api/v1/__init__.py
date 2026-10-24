"""Versioned API router. Feature routers attach here as phases land."""

from fastapi import APIRouter

from app import __version__
from app.api.v1 import auth, codeforces, dashboard, problems, reviews
from app.core.config import get_settings

api_router = APIRouter()
api_router.include_router(codeforces.router)
api_router.include_router(problems.router)
api_router.include_router(dashboard.router)
api_router.include_router(reviews.router)
api_router.include_router(auth.router)


@api_router.get("/", tags=["meta"])
def api_root() -> dict[str, str]:
    settings = get_settings()
    return {
        "name": settings.app_name,
        "version": __version__,
        "status": "ok",
    }
