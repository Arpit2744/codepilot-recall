"""Endpoint tests: envelopes, validation, dev-auth boundary, cross-user isolation."""

from datetime import UTC, datetime

from app.core.config import get_settings
from app.repositories import codeforces as repo


def test_create_account_accepted_response_shape(auth_client, monkeypatch):
    enqueued = []
    monkeypatch.setattr(
        "app.api.v1.codeforces.enqueue_sync",
        lambda account_id, job_id: enqueued.append(job_id) or True,
    )

    resp = auth_client.post("/api/v1/codeforces/accounts", json={"handle": "tourist"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["account"]["handle"] == "tourist"
    assert body["account"]["verified_at"] is None
    assert body["job"]["job_type"] == "historical"
    assert body["job"]["status"] == "pending"
    assert body["queued"] is True
    assert enqueued  # the job was actually handed to the queue layer


def test_create_account_duplicate_handle_for_same_user_conflicts(auth_client):
    first = auth_client.post("/api/v1/codeforces/accounts", json={"handle": "tourist"})
    assert first.status_code == 202

    dup = auth_client.post("/api/v1/codeforces/accounts", json={"handle": "TOURIST"})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "http_409"


def test_multiple_users_may_track_the_same_public_handle(
    auth_client, make_auth_client
):
    first = auth_client.post("/api/v1/codeforces/accounts", json={"handle": "tourist"})
    assert first.status_code == 202

    peer = make_auth_client("peer@example.com")
    resp = peer.post("/api/v1/codeforces/accounts", json={"handle": "tourist"})
    assert resp.status_code == 202  # public handle: shared tracking (ADR-0009)

    mine = auth_client.get("/api/v1/codeforces/accounts").json()
    theirs = peer.get("/api/v1/codeforces/accounts").json()
    assert [a["handle"] for a in mine] == ["tourist"]
    assert [a["handle"] for a in theirs] == ["tourist"]
    assert mine[0]["id"] != theirs[0]["id"]


def test_linked_account_quota_enforced(auth_client, monkeypatch):

    monkeypatch.setenv("MAX_LINKED_ACCOUNTS", "2")
    get_settings.cache_clear()
    try:
        for handle in ("h1", "h2"):
            assert (
                auth_client.post(
                    "/api/v1/codeforces/accounts", json={"handle": handle}
                ).status_code
                == 202
            )
        resp = auth_client.post("/api/v1/codeforces/accounts", json={"handle": "h3"})
        assert resp.status_code == 422
        assert "limit" in resp.json()["error"]["message"].lower()
    finally:
        monkeypatch.delenv("MAX_LINKED_ACCOUNTS")
        get_settings.cache_clear()


def test_create_account_validates_handle_format(auth_client):
    for bad in ("", "has space", "semi;colon", "x" * 25, "slash/1"):
        resp = auth_client.post("/api/v1/codeforces/accounts", json={"handle": bad})
        assert resp.status_code == 422, bad
        assert resp.json()["error"]["code"] == "validation_error"


def test_missing_session_is_unauthorized(client):
    resp = client.get("/api/v1/codeforces/accounts")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "http_401"


def test_x_user_id_header_is_never_an_identity(auth_client, make_user):
    other = make_user("ghost@example.com")
    resp = auth_client.get(
        "/api/v1/codeforces/accounts", headers={"X-User-Id": str(other.id)}
    )
    # Still the authenticated dev user: no ghost data, no fallback identity.
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_accounts_returns_only_own(auth_client, db_session, make_auth_client):
    other = make_auth_client("solo@example.com")
    repo.create_account(db_session, user_id=other.user.id, handle="someoneelse")

    auth_client.post("/api/v1/codeforces/accounts", json={"handle": "tourist"})

    resp = auth_client.get("/api/v1/codeforces/accounts")
    assert resp.status_code == 200
    handles = [a["handle"] for a in resp.json()]
    assert handles == ["tourist"]


def test_cross_user_cannot_see_or_trigger_other_accounts(auth_client, db_session, make_auth_client):
    other = make_auth_client("victim@example.com")
    other_account = repo.create_account(db_session, user_id=other.user.id, handle="victim")

    status = auth_client.get(f"/api/v1/codeforces/accounts/{other_account.id}/sync-status")
    assert status.status_code == 404

    sync = auth_client.post(f"/api/v1/codeforces/accounts/{other_account.id}/sync")
    assert sync.status_code == 404


def test_trigger_sync_returns_active_job_instead_of_duplicating(auth_client, db_session):
    created = auth_client.post("/api/v1/codeforces/accounts", json={"handle": "tourist"})
    account_id = created.json()["account"]["id"]

    second = auth_client.post(f"/api/v1/codeforces/accounts/{account_id}/sync")
    assert second.status_code == 202
    body = second.json()
    assert body["already_active"] is True
    assert body["job"]["id"] == created.json()["job"]["id"]
    assert body["job"]["job_type"] == "historical"  # the still-pending import


def test_sync_status_reports_totals_and_jobs(auth_client, db_session):
    created = auth_client.post("/api/v1/codeforces/accounts", json={"handle": "tourist"})
    account_id = created.json()["account"]["id"]

    resp = auth_client.get(f"/api/v1/codeforces/accounts/{account_id}/sync-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"] == {"submissions": 0, "solved_problems": 0}
    assert len(body["latest_jobs"]) == 1
    assert body["latest_jobs"][0]["status"] == "pending"
    assert body["account"]["last_sync_error"] is None


def test_problems_endpoint_paginates_solved(auth_client, db_session, make_user):
    # Seed data through the importer path (owner-scoped rollups).
    from tests.test_importer import T0, FakeClient, cf_item, cf_problem, run_historical

    user = auth_client.user
    account = repo.create_account(db_session, user_id=user.id, handle="tourist")
    pages = [
        [
            cf_item(2, datetime(2024, 5, 2, tzinfo=UTC), "OK", cf_problem(1, "A")),
            cf_item(1, T0, "OK", cf_problem(2, "B")),
        ]
    ]
    run_historical(db_session, account, FakeClient(pages))

    resp = auth_client.get("/api/v1/problems?page=1&page_size=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["page_size"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["canonical_key"] == "1-A"  # newest first-solve first
    assert item["first_solved_at"].startswith("2024-05-02")
    assert item["tags"] == ["math"]

    empty = auth_client.get("/api/v1/problems?page=99&page_size=20")
    assert empty.status_code == 200
    assert empty.json()["items"] == []


def test_dev_user_bootstrap_route_is_gone(client):
    resp = client.post("/api/v1/dev/users", json={})
    assert resp.status_code == 404
