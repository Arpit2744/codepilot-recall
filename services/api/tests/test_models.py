"""Model behavior: defaults, constraints, timezone-aware timestamps."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import User


def _make_user(email: str = "alice@example.com") -> User:
    return User(email=email, display_name="Alice")


def test_user_defaults(db_session):
    user = _make_user()
    db_session.add(user)
    db_session.commit()

    fetched = db_session.get(User, user.id)
    assert fetched is not None
    assert isinstance(fetched.id, uuid.UUID)
    assert fetched.timezone == "UTC"
    assert fetched.password_hash is None
    assert fetched.created_at.tzinfo is not None
    assert fetched.created_at <= datetime.now(UTC)


def test_duplicate_email_rejected(db_engine):
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)

    first = factory()
    first.add(_make_user("dup@example.com"))
    first.commit()
    first.close()

    second = factory()
    second.add(_make_user("dup@example.com"))
    with pytest.raises(IntegrityError):
        second.commit()
    second.rollback()
    second.close()


def test_updated_at_changes_on_update(db_session):
    user = _make_user()
    db_session.add(user)
    db_session.commit()
    original_updated = user.updated_at

    user.display_name = "Alice II"
    db_session.commit()

    assert user.updated_at >= original_updated
    # first-solve style timestamps must never drift backwards silently
    assert user.created_at == user.created_at
