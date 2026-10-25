"""Beta invitation gate tests (Phase 6): server-enforced registration
allowlist. The gate is configuration, never an obscure URL, and rejection
messages stay generic."""

import pytest

from app.core.config import get_settings

ORIGIN = "http://localhost:3000"


def register(client, email, password="Passw0rd!"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
        headers={"Origin": ORIGIN},
    )


@pytest.fixture(autouse=True)
def _restore_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_registration_open_when_allowlist_empty(client, monkeypatch):
    monkeypatch.delenv("BETA_ALLOWED_EMAILS", raising=False)
    assert register(client, "anyone@example.com").status_code == 201


def test_allowlisted_email_can_register(client, monkeypatch):
    monkeypatch.setenv("BETA_ALLOWED_EMAILS", "tester1@example.com,friend@Example.com")
    resp = register(client, "tester1@example.com")
    assert resp.status_code == 201
    # Case-insensitive match on the normalized address.
    assert register(client, "friend@example.com").status_code == 201


def test_non_allowlisted_email_rejected_generically(client, monkeypatch):
    monkeypatch.setenv("BETA_ALLOWED_EMAILS", "tester1@example.com")
    resp = register(client, "stranger@example.com")
    assert resp.status_code == 403
    body = resp.json()["error"]
    assert "invited beta testers" in body["message"]
    # The message must not leak whether a different address is listed.
    assert "tester1" not in body["message"]
    assert "stranger" not in body["message"]


def test_case_variation_of_allowlisted_address_accepted(client, monkeypatch):
    monkeypatch.setenv("BETA_ALLOWED_EMAILS", "Tester1@Example.com")
    resp = register(client, "tester1@example.com")
    assert resp.status_code == 201


def test_gate_does_not_block_login_of_existing_users(client, db_session, monkeypatch, make_user):
    make_user("pregate@example.com", password="Passw0rd!")
    monkeypatch.setenv("BETA_ALLOWED_EMAILS", "someone-else@example.com")
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "pregate@example.com", "password": "Passw0rd!"},
        headers={"Origin": ORIGIN},
    )
    # The gate is registration-only: existing accounts keep logging in.
    assert resp.status_code in (200, 401)  # 401 would mean wrong password
    assert resp.status_code != 403
