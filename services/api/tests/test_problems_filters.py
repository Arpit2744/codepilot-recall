"""Solved-problems filtering, sorting, pagination, and isolation tests."""

from datetime import UTC, datetime

import pytest

from app.repositories import codeforces as repo
from tests.test_importer import FakeClient, cf_item, cf_problem, run_historical

T0 = datetime(2024, 5, 1, 12, 0, tzinfo=UTC)


def problem(contest, index, name, rating, tags):
    return cf_problem(contest, index, name=name, rating=rating, tags=tags)


PROBLEMS = {
    "theatre": problem(1, "A", "Theatre Square", 1000, ("math",)),
    "subseq": problem(2, "B", "Square Subsequences", 1600, ("dp", "math")),
    "night": problem(4, "D", "Night Chart", 1200, ("graphs",)),
    "segments": problem(5, "E", "Segments", 900, ("two-pointers", "binary search")),
    "mystery": problem(6, "F", "Mystery Problem", None, ()),
}


def seed_page():
    return [
        [
            cf_item(10, T0, "OK", PROBLEMS["mystery"]),
            cf_item(9, T0, "OK", PROBLEMS["segments"]),
            cf_item(8, T0, "OK", PROBLEMS["night"]),
            cf_item(7, T0, "OK", PROBLEMS["subseq"]),
            cf_item(6, T0, "OK", PROBLEMS["theatre"]),
        ]
    ]


@pytest.fixture
def seeded_user(auth_client, db_session):
    user = auth_client.user
    account = repo.create_account(db_session, user_id=user.id, handle="tourist")
    run_historical(db_session, account, FakeClient(seed_page()))
    return user


def names(body):
    return [item["name"] for item in body["items"]]


def test_search_by_name_substring_case_insensitive(auth_client, seeded_user):
    body = auth_client.get("/api/v1/problems?search=SQUARE").json()
    assert body["total"] == 2
    assert set(names(body)) == {"Theatre Square", "Square Subsequences"}


def test_rating_range_filter(auth_client, seeded_user):
    body = auth_client.get("/api/v1/problems?rating_min=1000&rating_max=1500").json()
    assert body["total"] == 2
    assert set(names(body)) == {"Theatre Square", "Night Chart"}


def test_tag_filter_exact_not_substring(auth_client, seeded_user):
    math = auth_client.get("/api/v1/problems?tag=math").json()
    assert names(math) and set(names(math)) == {"Theatre Square", "Square Subsequences"}

    # "two" must NOT match the "two-pointers" tag (quote-wrapped matching).
    assert auth_client.get("/api/v1/problems?tag=two").json()["total"] == 0
    exact = auth_client.get("/api/v1/problems?tag=two-pointers").json()
    assert exact["total"] == 1 and names(exact) == ["Segments"]


def test_combined_filters(auth_client, seeded_user):
    body = auth_client.get("/api/v1/problems?search=square&rating_min=1500").json()
    assert body["total"] == 1
    assert names(body) == ["Square Subsequences"]


def test_sort_by_rating_nulls_last_both_directions(auth_client, seeded_user):
    asc = names(auth_client.get("/api/v1/problems?sort=rating&order=asc").json())
    assert asc == [
        "Segments", "Theatre Square", "Night Chart",
        "Square Subsequences", "Mystery Problem",
    ]
    desc = names(auth_client.get("/api/v1/problems?sort=rating&order=desc").json())
    # Null rating stays last in DESC too; ties broken by name.
    assert desc == [
        "Square Subsequences", "Night Chart", "Theatre Square",
        "Segments", "Mystery Problem",
    ]


def test_sort_by_name_ascending(auth_client, seeded_user):
    asc = names(auth_client.get("/api/v1/problems?sort=name&order=asc").json())
    assert asc == sorted(asc)


def test_default_sort_first_solved_desc(auth_client, seeded_user):
    body = auth_client.get("/api/v1/problems").json()
    assert body["total"] == 5
    dates = [item["first_solved_at"] for item in body["items"]]
    assert dates == sorted(dates, reverse=True)


def test_pagination_totals_and_boundaries(auth_client, seeded_user):
    page1 = auth_client.get("/api/v1/problems?sort=name&order=asc&page=1&page_size=2").json()
    assert page1["total"] == 5 and len(page1["items"]) == 2
    page3 = auth_client.get("/api/v1/problems?sort=name&order=asc&page=3&page_size=2").json()
    assert page3["total"] == 5 and len(page3["items"]) == 1
    beyond = auth_client.get("/api/v1/problems?sort=name&order=asc&page=99").json()
    assert beyond["items"] == [] and beyond["total"] == 5
    # Totals reflect active filters.
    filtered = auth_client.get("/api/v1/problems?tag=math&page=1&page_size=1").json()
    assert filtered["total"] == 2 and len(filtered["items"]) == 1


def test_rejects_invalid_sort_and_order(auth_client, seeded_user):
    resp = auth_client.get("/api/v1/problems?sort=password")  # not sortable
    assert resp.status_code == 422
    assert "Unsupported sort" in resp.json()["error"]["message"]

    resp = auth_client.get("/api/v1/problems?order=sideways")
    assert resp.status_code == 422


def test_rejects_crossed_rating_bounds(auth_client, seeded_user):
    resp = auth_client.get("/api/v1/problems?rating_min=2000&rating_max=1000")
    assert resp.status_code == 422
    assert "rating_min" in resp.json()["error"]["message"]


def test_cross_user_isolation(auth_client, seeded_user, make_auth_client, db_session):
    other = make_auth_client("other@example.com")
    own_account = repo.create_account(db_session, user_id=other.user.id, handle="second-user")
    run_historical(
        db_session,
        own_account,
        FakeClient([[cf_item(1, T0, "OK", PROBLEMS["theatre"])]]),
    )

    mine = auth_client.get("/api/v1/problems?sort=name").json()
    assert mine["total"] == 5

    theirs = other.get("/api/v1/problems?sort=name").json()
    assert theirs["total"] == 1
    assert names(theirs) == ["Theatre Square"]
