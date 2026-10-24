"""Constraint and relationship tests for the Codeforces models."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import CfAccount, Problem, Submission, SyncJob, User, UserProblem

NOW = datetime.now(UTC)


def _user(email: str = "u@example.com") -> User:
    return User(email=email, display_name="U")


def _account(user_id, handle: str = "tourist") -> CfAccount:
    return CfAccount(user_id=user_id, handle=handle, handle_lower=handle.lower())


def _problem(key: str = "1-A") -> Problem:
    return Problem(canonical_key=key, name="Theatre Square", tags=["math"])


@pytest.fixture
def user(db_session) -> User:
    user = _user()
    db_session.add(user)
    db_session.commit()
    return user


def test_handle_lower_globally_unique(db_engine, user):
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)

    a = factory()
    a.add(_account(user.id, "Tourist"))
    a.commit()
    a.close()

    b = factory()
    b.add(_account(user.id, "tOURIST"))  # same identity, different case
    with pytest.raises(IntegrityError):
        b.commit()
    b.rollback()
    b.close()


def test_submission_unique_per_account_and_source_id(db_session, user):
    problem = _problem()
    account = _account(user.id)
    db_session.add_all([problem, account])
    db_session.commit()

    db_session.add(
        Submission(
            cf_account_id=account.id,
            cf_submission_id=123456,
            problem_id=problem.id,
            verdict="OK",
            submitted_at=NOW,
        )
    )
    db_session.commit()

    db_session.add(
        Submission(
            cf_account_id=account.id,
            cf_submission_id=123456,
            problem_id=problem.id,
            submitted_at=NOW,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_user_problem_unique_per_user_and_problem(db_session, user):
    problem = _problem()
    account = _account(user.id)
    db_session.add_all([problem, account])
    db_session.commit()

    db_session.add(
        UserProblem(
            user_id=user.id,
            problem_id=problem.id,
            first_solved_at=NOW,
            last_solved_at=NOW,
        )
    )
    db_session.flush()
    db_session.add(
        UserProblem(
            user_id=user.id,
            problem_id=problem.id,
            first_solved_at=NOW,
            last_solved_at=NOW,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_deleting_user_cascades_accounts_but_not_shared_problems(db_session, user):
    problem = _problem()
    account = _account(user.id)
    db_session.add_all([problem, account])
    db_session.commit()

    account_id, problem_id = account.id, problem.id
    db_session.delete(user)
    db_session.commit()

    # Evict the identity map so the follow-up reads actually hit the database.
    db_session.expire_all()
    assert db_session.get(CfAccount, account_id) is None
    # Problems are shared across users and must survive account deletion.
    assert db_session.get(Problem, problem_id) is not None


def test_sync_job_defaults(db_session, user):
    account = _account(user.id)
    db_session.add(account)
    db_session.commit()

    job = SyncJob(cf_account_id=account.id, job_type="historical")
    db_session.add(job)
    db_session.commit()

    assert job.status == "pending"
    assert job.attempt_count == 0
    assert job.progress is None
    assert isinstance(job.id, uuid.UUID)
