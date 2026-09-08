"""Regression coverage for security middleware and route guards."""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_includes_security_headers():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_auth_required_rejects_anonymous_reads_and_writes(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")

    projects = client.get("/api/v1/projects")
    assert projects.status_code == 401
    assert projects.headers.get("www-authenticate") == "Bearer"

    upload = client.post(
        "/api/v1/projects/demo-project/datasets",
        files={"file": ("sample.csv", b"email\na@example.com\n", "text/csv")},
        data={"consent": "true"},
    )
    assert upload.status_code == 401
    assert upload.headers.get("www-authenticate") == "Bearer"


def test_viewer_cannot_confirm_review(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    token_response = client.post(
        "/api/v1/auth/login", json={"username": "viewer", "password": "viewer"}
    )
    assert token_response.status_code == 200
    token = token_response.json()["access_token"]

    review = client.get(
        "/api/v1/projects/demo-project/reviews",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["items"][0]["id"]
    response = client.post(
        f"/api/v1/projects/demo-project/reviews/{review}/confirm",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
