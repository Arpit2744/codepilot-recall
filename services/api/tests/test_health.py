"""Health, readiness, API root, and error-envelope behavior."""

from app import __version__


def test_health_liveness(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "status": "ok",
        "service": "api",
        "version": __version__,
        "environment": "test",
    }


def test_health_ready_checks_database(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_api_v1_root_metadata(client):
    resp = client.get("/api/v1/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "CodePilot Recall"
    assert body["version"] == __version__
    assert body["status"] == "ok"


def test_unknown_route_returns_error_envelope(client):
    resp = client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "http_404"
    assert "message" in body["error"]
    assert body["error"]["details"] is None


def test_openapi_document_available(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert "/health" in spec["paths"]
    assert "/api/v1/" in spec["paths"]
