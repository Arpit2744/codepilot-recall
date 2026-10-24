"""Unit tests for the Codeforces payload normalizer (pure functions)."""

from datetime import UTC, datetime

from app.integrations.codeforces.normalizer import (
    canonical_problem_key,
    is_accepted,
    problem_from_cf,
    slugify,
    submission_from_cf,
    submitted_at_from_cf,
)


def cf_problem(**overrides) -> dict:
    base = {
        "contestId": 1,
        "index": "A",
        "name": "Theatre Square",
        "rating": 1000,
        "tags": ["math"],
    }
    base.update(overrides)
    return base


def cf_submission(**overrides) -> dict:
    base = {
        "id": 100,
        "creationTimeSeconds": 1600000000,
        "problem": cf_problem(),
        "author": {"members": [{"handle": "tourist"}], "participationType": "PRACTICE"},
        "programmingLanguage": "GNU C++17",
        "verdict": "OK",
        "passedTestCount": 30,
        "timeConsumedMillis": 100,
        "memoryConsumedBytes": 1000,
    }
    base.update(overrides)
    return base


def test_canonical_key_uses_contest_and_index():
    assert canonical_problem_key(cf_problem()) == "1-A"


def test_canonical_key_falls_back_for_problemset_only_problems():
    problem = cf_problem(contestId=None, problemsetName="acmsguru", name="Problem 1")
    assert canonical_problem_key(problem) == "ps:acmsguru:problem-1"


def test_slugify_handles_unicode_and_punctuation():
    # Mixed scripts keep their ASCII parts; fully non-Latin names degrade
    # to the "unnamed" fallback rather than an empty key.
    assert slugify("Problem  #42 (Hard!)") == "problem-42-hard"
    assert slugify("Кинской Дворик") == "unnamed"


def test_is_accepted_only_for_ok():
    assert is_accepted("OK") is True
    for verdict in ("WRONG_ANSWER", "TESTING", None, "PARTIAL"):
        assert is_accepted(verdict) is False


def test_problem_from_cf_maps_all_fields():
    mapped = problem_from_cf(cf_problem(tags=["math", "implementation"]))
    assert mapped["canonical_key"] == "1-A"
    assert mapped["contest_id"] == 1
    assert mapped["problem_index"] == "A"
    assert mapped["name"] == "Theatre Square"
    assert mapped["rating"] == 1000
    assert mapped["tags"] == ["math", "implementation"]
    assert mapped["url"].endswith("/problemset/problem/1/A")
    assert mapped["problemset_name"] is None


def test_problem_from_cf_without_rating_or_tags():
    mapped = problem_from_cf(cf_problem(rating=None, tags=None))
    assert mapped["rating"] is None
    assert mapped["tags"] == []


def test_submitted_at_is_tz_aware_utc():
    ts = submitted_at_from_cf(cf_submission(creationTimeSeconds=0))
    assert ts == datetime(1970, 1, 1, tzinfo=UTC)


def test_submitted_at_midnight_boundary_preserved_exactly():
    from datetime import timedelta

    midnight = 1774828800  # 2026-03-30 00:00:00 UTC (exact day boundary)
    before = submitted_at_from_cf(cf_submission(creationTimeSeconds=midnight - 1))
    after = submitted_at_from_cf(cf_submission(creationTimeSeconds=midnight))
    assert before.date() == after.date() - timedelta(days=1)
    assert after - before == timedelta(seconds=1)


def test_submission_from_cf_maps_fields_and_meta():
    mapped = submission_from_cf(cf_submission())
    assert mapped["cf_submission_id"] == 100
    assert mapped["verdict"] == "OK"
    assert mapped["programming_language"] == "GNU C++17"
    assert mapped["passed_test_count"] == 30
    assert mapped["submitted_at"].tzinfo is UTC
    assert mapped["source_meta"]["participation_type"] == "PRACTICE"


def test_submission_from_cf_without_verdict_or_meta():
    mapped = submission_from_cf(
        cf_submission(verdict=None, author={"members": []}, relativeTimeSeconds=5)
    )
    assert mapped["verdict"] is None
    assert mapped["source_meta"] == {"relative_time_seconds": 5}


def test_submission_ids_are_not_treated_as_timestamps():
    # Two submissions with wildly different ids but explicit creation times:
    # the normalizer derives time ONLY from creationTimeSeconds.
    a = submission_from_cf(cf_submission(id=999999999, creationTimeSeconds=100))
    b = submission_from_cf(cf_submission(id=1, creationTimeSeconds=200))
    assert a["submitted_at"] < b["submitted_at"]
