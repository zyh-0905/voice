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


def test_token_cannot_access_another_project(monkeypatch):
    from app.main import repository
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setitem(repository.projects, "private-project", {"id": "private-project", "name": "Private"})
    token = client.post("/api/v1/auth/login", json={"username": "demo", "password": "demo"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    projects = client.get("/api/v1/projects", headers=headers).json()["items"]
    assert "private-project" not in {item["id"] for item in projects}
    for suffix in ("", "/datasets", "/analyses", "/risks", "/tasks", "/reviews", "/outbox/status", "/exports/redacted.csv"):
        response = client.get("/api/v1/projects/private-project" + suffix, headers=headers)
        assert response.status_code == 404, suffix
    response = client.post("/api/v1/projects/private-project/datasets", headers=headers,
        files={"file": ("test.csv", b"text\nfeedback\n", "text/csv")}, data={"consent": "true"})
    assert response.status_code == 404
    response = client.post("/api/v1/projects/private-project/analyses", headers=headers, json={"dataset_ids": ["any"]})
    assert response.status_code == 404
    assert client.get("/api/v1/projects/demo-project", headers=headers).status_code == 200


def test_cross_project_review_confirmation_does_not_mutate(monkeypatch):
    from app.main import repository
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setitem(repository.reviews, "private-review", {"id": "private-review", "project_id": "private-project", "status": "pending"})
    response = client.post("/api/v1/projects/demo-project/reviews/private-review/confirm")
    assert response.status_code == 404
    assert repository.reviews["private-review"]["status"] == "pending"
