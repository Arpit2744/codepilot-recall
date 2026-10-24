import os

# Must happen before any app import so cached settings pick it up.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("REDIS_URL", "")  # in-process rate limiter in tests
# Fast-but-identical-code Argon2 params for test runtime (production
# defaults stay in Settings; see docs/adr/0008-auth-sessions-csrf.md).
os.environ["ARGON2_TIME_COST"] = "1"
os.environ["ARGON2_MEMORY_COST"] = "8"
os.environ["ARGON2_PARALLELISM"] = "1"
# Generous auth limits so functional tests never trip them; the dedicated
# rate-limit tests override the limiter explicitly.
os.environ["RATE_LIMIT_REGISTER"] = "10000:3600"
os.environ["RATE_LIMIT_LOGIN_IP"] = "10000:900"
os.environ["RATE_LIMIT_LOGIN_EMAIL"] = "10000:900"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import rate_limit
from app.core.db import get_db
from app.main import app
from app.models import Base, User
from app.services import auth as auth_service

TEST_ORIGIN = "http://localhost:3000"  # in Settings.cors_origins default


class AuthClient(TestClient):
    """TestClient whose mutations automatically carry CSRF + trusted Origin.

    Session cookie lives in the client's cookie jar exactly like a browser.
    """

    csrf_token: str | None = None
    user: User | None = None

    def _mutation_headers(self, headers=None):
        merged = dict(headers or {})
        merged.setdefault("Origin", TEST_ORIGIN)
        if self.csrf_token:
            merged.setdefault("X-CSRF-Token", self.csrf_token)
        return merged

    def post(self, *args, **kwargs):
        kwargs["headers"] = self._mutation_headers(kwargs.get("headers"))
        return super().post(*args, **kwargs)

    def patch(self, *args, **kwargs):
        kwargs["headers"] = self._mutation_headers(kwargs.get("headers"))
        return super().patch(*args, **kwargs)

    def delete(self, *args, **kwargs):
        kwargs["headers"] = self._mutation_headers(kwargs.get("headers"))
        return super().delete(*args, **kwargs)


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
    rate_limit.reset_rate_limiter()


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
    """Unauthenticated TestClient against the test DB."""

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
    def _make(email: str = "dev@example.com", password: str | None = None) -> User:
        user = User(email=email.lower(), display_name=email.split("@")[0])
        if password is not None:
            user.password_hash = auth_service.hash_password(password)
        db_session.add(user)
        db_session.commit()
        return user

    return _make


def _login_client(db_engine, email: str, password: str) -> AuthClient:
    """Create an AuthClient and authenticate via the real login endpoint."""

    def override_get_db():
        session = sessionmaker(bind=db_engine, expire_on_commit=False)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    auth_client = AuthClient(app)
    try:
        response = auth_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            headers={"Origin": TEST_ORIGIN},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        auth_client.csrf_token = body["csrf_token"]
    except BaseException:
        app.dependency_overrides.clear()
        raise
    return auth_client


@pytest.fixture
def make_auth_client(db_engine, db_session, make_user):
    """Factory: create a user WITH a password and return a logged-in client."""

    clients: list[AuthClient] = []

    def _make(email: str = "dev@example.com", password: str = "Passw0rd!") -> AuthClient:
        make_user(email, password=password)
        auth_client = _login_client(db_engine, email, password)
        with auth_client:
            auth_client.get("/api/v1/auth/me")
        auth_client.user = (
            db_session.query(User).filter_by(email=email.lower()).one()
        )
        clients.append(auth_client)
        return auth_client

    yield _make
    app.dependency_overrides.clear()
    for c in clients:
        c.close()


@pytest.fixture
def auth_client(make_auth_client) -> AuthClient:
    """Default authenticated client (dev@example.com / Passw0rd!)."""
    return make_auth_client()
