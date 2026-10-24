"""Pure mappings from Codeforces API payloads to our storage shapes.

No I/O here: every function is deterministic and unit-testable in isolation.
"""

import re
from datetime import UTC, datetime
from typing import Any

ACCEPTED_VERDICT = "OK"

_SLUG_RE = re.compile(r"[^0-9a-z]+")


def is_accepted(verdict: str | None) -> bool:
    """Only verdict == OK counts as an accepted solve."""
    return verdict == ACCEPTED_VERDICT


def slugify(name: str) -> str:
    return _SLUG_RE.sub("-", name.lower()).strip("-")[:64] or "unnamed"


def canonical_problem_key(problem: dict[str, Any]) -> str:
    """Stable identity: contest+index when available, else problemset+name."""
    contest_id = problem.get("contestId")
    index = problem.get("index")
    if contest_id is not None and index:
        return f"{contest_id}-{index}"
    problemset = problem.get("problemsetName") or "cf"
    return f"ps:{problemset}:{slugify(str(problem.get('name', '')))}"


def problem_url(problem: dict[str, Any], site_base: str = "https://codeforces.com") -> str | None:
    contest_id = problem.get("contestId")
    index = problem.get("index")
    if contest_id is None or not index:
        return None
    return f"{site_base}/problemset/problem/{contest_id}/{index}"


def problem_from_cf(problem: dict[str, Any]) -> dict[str, Any]:
    """Map a CF `problem` object to `problems` column values."""
    return {
        "canonical_key": canonical_problem_key(problem),
        "contest_id": problem.get("contestId"),
        "problem_index": problem.get("index"),
        "problemset_name": problem.get("problemsetName"),
        "name": str(problem.get("name", ""))[:256],
        "rating": problem.get("rating"),
        "tags": list(problem.get("tags") or []),
        "url": problem_url(problem),
    }


def submitted_at_from_cf(submission: dict[str, Any]) -> datetime:
    """The ONLY time source we trust: creationTimeSeconds as tz-aware UTC.

    Submission IDs are never used to infer chronology.
    """
    return datetime.fromtimestamp(int(submission["creationTimeSeconds"]), tz=UTC)


def submission_from_cf(submission: dict[str, Any]) -> dict[str, Any]:
    """Map a CF `user.status` entry to `submissions` column values."""
    author = submission.get("author") or {}
    source_meta: dict[str, Any] = {}
    if author.get("participationType"):
        source_meta["participation_type"] = author["participationType"]
    if submission.get("relativeTimeSeconds") is not None:
        source_meta["relative_time_seconds"] = submission["relativeTimeSeconds"]

    return {
        "cf_submission_id": int(submission["id"]),
        "verdict": submission.get("verdict"),
        "programming_language": submission.get("programmingLanguage"),
        "passed_test_count": submission.get("passedTestCount"),
        "time_consumed_millis": submission.get("timeConsumedMillis"),
        "memory_consumed_bytes": submission.get("memoryConsumedBytes"),
        "submitted_at": submitted_at_from_cf(submission),
        "source_meta": source_meta or None,
    }
