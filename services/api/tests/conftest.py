"""Shared fixtures: isolated in-memory SQLite database per test."""

import os

# Must happen before any app import so cached settings pick it up.
os.environ.setdefault("ENVIRONMENT", "test")
# No broker in API tests: enqueue_sync short-circuits instead of dialing Redis.
os.environ.setdefault("REDIS_URL", "")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.main import app
from app.models import Base, User


def _make_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite does not enforce FKs unless asked; PostgreSQL does natively.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture
def db_engine():
    engine = _make_engine()
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Session:
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_engine) -> TestClient:
    """TestClient with the request-scoped DB dependency pointed at the test DB."""

    def override_get_db():
        session = sessionmaker(bind=db_engine, expire_on_commit=False)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db_session):
    def _make(email: str = "dev@example.com") -> User:
        user = User(email=email, display_name=email.split("@")[0])
        db_session.add(user)
        db_session.commit()
        return user

    return _make


@pytest.fixture
def auth_client(client, make_user) -> TestClient:
    """Client pre-authenticated as a dev user via the Phase 1 dev header."""
    user = make_user("dev@example.com")
    client.headers.update({"X-User-Id": str(user.id)})
    client.dev_user = user
    return client
