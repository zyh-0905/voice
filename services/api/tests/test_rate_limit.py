"""Regression coverage for write rate limiting."""

from fastapi.testclient import TestClient
from app.main import app
from app.rate_limit import WriteRateLimitMiddleware

client = TestClient(app)


def _rate_middleware() -> WriteRateLimitMiddleware:
    client.get("/api/v1/health")  # force Starlette middleware construction
    middleware = app.middleware_stack
    while middleware is not None and not isinstance(middleware, WriteRateLimitMiddleware):
        middleware = getattr(middleware, "app", None)
    assert isinstance(middleware, WriteRateLimitMiddleware)
    return middleware


def test_upload_rate_limit_returns_retry_after(monkeypatch):
    middleware = _rate_middleware()
    previous_limit = middleware.limit
    try:
        monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
        middleware.limit = 1
        middleware._hits.clear()
        path = "/api/v1/projects/rate-limit-test/datasets"
        files = {"file": ("sample.csv", b"email\nlimit@example.com\n")}
        first = client.post(path, files=files, data={"consent": "true"})
        second = client.post(path, files=files, data={"consent": "true"})
        assert first.status_code == 201
        assert second.status_code == 429
        assert int(second.headers["Retry-After"]) >= 1
        assert second.json()["detail"] == "rate_limit_exceeded"
    finally:
        middleware.limit = previous_limit
        middleware._hits.clear()
