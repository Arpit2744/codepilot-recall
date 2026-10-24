"""Dashboard endpoint tests: aggregates, timezone boundaries, validation.

All data is seeded through the importer with FakeClient fixtures (Phase 1
helpers) — deterministic, no network.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.repositories import codeforces as repo
from tests.test_importer import FakeClient, cf_item, cf_problem, run_historical


def at(day, hour, minute=0):
    return datetime(2024, 5, day, hour, minute, tzinfo=UTC)


P1 = cf_problem(1, "A", name="Theatre Square", rating=1000, tags=("math",))
P2 = cf_problem(2, "B", name="Square Subsequences", rating=1600, tags=("dp", "math"))
P4 = cf_problem(4, "D", name="Night Chart", rating=1200, tags=("graphs",))
P5 = cf_problem(5, "E", name="Gym Mystery", rating=None, tags=("greedy",))

SEED = [
    [
        # id, timestamp, verdict, problem — one page, ordered newest-first
        dict(sub_id=5, ts=at(2, 20), verdict="WRONG_ANSWER", problem=P5),
        dict(sub_id=4, ts=datetime(2024, 5, 1, 23, 30, tzinfo=UTC), verdict="OK", problem=P2),
        dict(sub_id=3, ts=at(3, 9), verdict="OK", problem=P1),
        # noon: safely mid-day in every fixture timezone
        dict(sub_id=2, ts=at(1, 12), verdict="OK", problem=P1),
        dict(sub_id=6, ts=datetime(2024, 5, 1, 1, 30, tzinfo=UTC), verdict="OK", problem=P4),
        dict(sub_id=1, ts=at(1, 10), verdict="WRONG_ANSWER", problem=P1),
    ]
]


def seed_page():
    return [[cf_item(s["sub_id"], s["ts"], s["verdict"], s["problem"]) for s in SEED[0]]]


@pytest.fixture
def seeded_user(auth_client, db_session):
    """Dev user with one account and the canonical fixture history."""
    user = auth_client.dev_user
    repo.create_account(db_session, user_id=user.id, handle="tourist")
    from tests.test_importer import FakeClient as FC

    # re-import the runner to bind to this account
    account = repo.list_accounts(db_session, user.id)[0]
    run_historical(db_session, account, FC(seed_page()))
    return user


def counts_by_date(days):
    return {d["date"]: d["count"] for d in days}


# ------------------------------------------------------------------ summary


def test_summary_totals_match_fixture(auth_client, seeded_user):
    resp = auth_client.get("/api/v1/dashboard/summary?timezone=UTC")
    assert resp.status_code == 200
    body = resp.json()
    # 6 persisted submissions; 3 distinct solved problems (P1, P2, P4).
    # P5 (WRONG only) and P1's rejected attempt never count as solves.
    assert body["totals"] == {"submissions": 6, "solved_problems": 3}
    assert body["timezone"] == "UTC"
    assert len(body["accounts"]) == 1
    assert body["accounts"][0]["handle"] == "tourist"
    # Most recent first solve first: P1's second acceptance? No — distinct
    # problems only; newest first-solved is P1 (05-03) here? P1 first_solved
    # is its EARLIEST OK (T0); newest first-solve is P2 (23:30 05-01).
    names = [r["name"] for r in body["recent_first_solves"]]
    assert names[0] == "Square Subsequences"


def test_summary_multiple_acceptances_do_not_inflate_solves(auth_client, seeded_user):
    body = auth_client.get("/api/v1/dashboard/summary?timezone=UTC").json()
    # P1 accepted twice (ids 2 and 3) — still one solved problem.
    assert body["totals"]["solved_problems"] == 3


def test_repeated_sync_does_not_inflate_totals(auth_client, seeded_user, db_session):
    account = repo.list_accounts(db_session, seeded_user.id)[0]
    before = auth_client.get("/api/v1/dashboard/summary?timezone=UTC").json()["totals"]

    run_historical(db_session, account, FakeClient(seed_page()))  # identical re-import

    after = auth_client.get("/api/v1/dashboard/summary?timezone=UTC").json()["totals"]
    assert after == before


def test_older_first_solve_discovered_on_resync(auth_client, seeded_user, db_session):
    account = repo.list_accounts(db_session, seeded_user.id)[0]
    older_ok = datetime(2024, 4, 20, 8, 0, tzinfo=UTC)
    p2_ok = datetime(2024, 5, 1, 23, 30, tzinfo=UTC)
    delta = [[cf_item(9, older_ok, "OK", P2), cf_item(4, p2_ok, "OK", P2)]]
    from app.services.sync.importer import SyncImporter

    job = repo.create_job(db_session, account_id=account.id, job_type="incremental")
    SyncImporter(
        db_session, account, FakeClient(delta), page_size=2, historical_max_pages=50,
        incremental_max_pages=10,
    ).run(job)
    db_session.expire_all()

    body = auth_client.get("/api/v1/dashboard/summary?timezone=UTC").json()
    # Solved count unchanged; the earlier date became P2's first solve.
    assert body["totals"] == {"submissions": 7, "solved_problems": 3}

    heat = auth_client.get(
        "/api/v1/dashboard/heatmap"
        "?from=2024-04-20&to=2024-05-03&timezone=UTC&mode=first_solves"
    ).json()
    discovered = counts_by_date(heat["days"])
    assert discovered["2024-04-20"] == 1  # the newly discovered older solve
    assert discovered["2024-05-01"] == 2  # P2 moved back; P1 and P4 remain
    assert sum(discovered.values()) == 3


def test_summary_empty_user(auth_client, make_user):
    other = make_user("empty@example.com")
    auth_client.headers.update({"X-User-Id": str(other.id)})
    body = auth_client.get("/api/v1/dashboard/summary?timezone=UTC").json()
    assert body["totals"] == {"submissions": 0, "solved_problems": 0}
    assert body["accounts"] == []
    assert body["current_streak_days"] == 0
    assert body["recent_first_solves"] == []


def test_summary_streak_counts_recent_activity(auth_client, seeded_user, db_session):
    account = repo.list_accounts(db_session, seeded_user.id)[0]
    recent = [[cf_item(99, datetime.now(UTC) - timedelta(hours=2), "OK", P5)]]
    from app.services.sync.importer import SyncImporter

    job = repo.create_job(db_session, account_id=account.id, job_type="incremental")
    SyncImporter(
        db_session, account, FakeClient(recent), page_size=2, historical_max_pages=50,
        incremental_max_pages=10,
    ).run(job)

    body = auth_client.get("/api/v1/dashboard/summary?timezone=UTC").json()
    assert body["current_streak_days"] >= 1


def test_summary_isolated_across_users(auth_client, seeded_user, make_user):
    other = make_user("solo@example.com")
    resp = auth_client.get(
        "/api/v1/dashboard/summary?timezone=UTC", headers={"X-User-Id": str(other.id)}
    )
    assert resp.json()["totals"] == {"submissions": 0, "solved_problems": 0}


# ----------------------------------------------------------------- heatmap


def test_heatmap_utc_counts_match_fixture(auth_client, seeded_user):
    resp = auth_client.get(
        "/api/v1/dashboard/heatmap?from=2024-05-01&to=2024-05-03&timezone=UTC&mode=submissions"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["mode"] == "submissions"
    assert body["from"] == "2024-05-01" and body["to"] == "2024-05-03"
    assert counts_by_date(body["days"]) == {
        "2024-05-01": 4,  # ids 1,2,4,6
        "2024-05-02": 1,  # id 5
        "2024-05-03": 1,  # id 3
    }
    assert body["max_count"] == 4


def test_heatmap_first_solves_counts_distinct_problems(auth_client, seeded_user):
    body = auth_client.get(
        "/api/v1/dashboard/heatmap?from=2024-05-01&to=2024-05-03&timezone=UTC&mode=first_solves"
    ).json()
    # P1 (T0), P2 (23:30), P4 (01:30) — all on 05-01 UTC; P1's second
    # acceptance (id 3) must NOT add another first solve.
    assert counts_by_date(body["days"]) == {"2024-05-01": 3, "2024-05-02": 0, "2024-05-03": 0}


def test_heatmap_kolkata_buckets_after_utc_midnight(auth_client, seeded_user):
    body = auth_client.get(
        "/api/v1/dashboard/heatmap"
        "?from=2024-05-01&to=2024-05-03&timezone=Asia/Kolkata&mode=submissions"
    ).json()
    # +5:30 — id4 (23:30 UTC) moves to 05-02 local; id5 (20:00 UTC 05-02)
    # moves to 05-03 local; ids 1,2,6 stay on 05-01.
    assert counts_by_date(body["days"]) == {
        "2024-05-01": 3,
        "2024-05-02": 1,
        "2024-05-03": 2,
    }


def test_heatmap_new_york_buckets_before_utc_midnight(auth_client, seeded_user):
    body = auth_client.get(
        "/api/v1/dashboard/heatmap"
        "?from=2024-04-30&to=2024-05-03&timezone=America/New_York&mode=submissions"
    ).json()
    # -4 (EDT) — id6 (01:30 UTC 05-01) lands on 04-30 local.
    assert counts_by_date(body["days"]) == {
        "2024-04-30": 1,
        "2024-05-01": 3,
        "2024-05-02": 1,
        "2024-05-03": 1,
    }


def test_heatmap_includes_zero_days_continuously(auth_client, seeded_user):
    body = auth_client.get(
        "/api/v1/dashboard/heatmap?from=2024-04-25&to=2024-05-05&timezone=UTC&mode=submissions"
    ).json()
    days = body["days"]
    assert len(days) == 11  # continuous, no gaps
    assert counts_by_date(days)["2024-04-25"] == 0
    assert sum(d["count"] for d in days) == 6  # rollup consistent with source rows


def test_heatmap_reviews_mode_is_explicitly_unavailable(auth_client, seeded_user):
    body = auth_client.get(
        "/api/v1/dashboard/heatmap?from=2024-05-01&to=2024-05-03&timezone=UTC&mode=reviews"
    ).json()
    assert body["available"] is False
    assert body["days"] == []
    assert body["max_count"] == 0
    assert "Phase 3" in body["message"]


def test_heatmap_isolated_across_users(auth_client, seeded_user, make_user):
    other = make_user("quiet@example.com")
    body = auth_client.get(
        "/api/v1/dashboard/heatmap?from=2024-05-01&to=2024-05-03&timezone=UTC",
        headers={"X-User-Id": str(other.id)},
    ).json()
    assert all(d["count"] == 0 for d in body["days"])


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "query",
    [
        "from=2024-05-03&to=2024-05-01&timezone=UTC",  # from after to
        "from=2020-01-01&to=2026-01-01&timezone=UTC",  # range too large
        "from=2024-05-01&to=2024-05-03&timezone=Not/AZone",  # bad tz
        "from=2024-05-01&to=2024-05-03&timezone=UTC&mode=bogus",  # bad mode
        "from=notadate&to=2024-05-03&timezone=UTC",  # bad date
    ],
)
def test_heatmap_rejects_invalid_input(auth_client, seeded_user, query):
    resp = auth_client.get(f"/api/v1/dashboard/heatmap?{query}")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] in ("http_422", "validation_error")


def test_summary_rejects_invalid_timezone(auth_client, seeded_user):
    resp = auth_client.get("/api/v1/dashboard/summary?timezone=Mars/Olympus")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "http_422"
