"""Database engine and session management (SQLAlchemy 2, sync sessions)."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


def create_db_engine(url: str) -> Engine:
    """Create an engine that works for PostgreSQL (prod) and SQLite (tests)."""
    if url.startswith("sqlite"):
        # StaticPool keeps a single connection alive for in-memory SQLite so
        # multiple sessions (and TestClient requests) share the same database.
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(url, pool_pre_ping=True)


engine = create_db_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
