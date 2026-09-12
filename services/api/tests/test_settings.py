import pytest
from app.settings import DEMO_SECRET, load_settings, validate_production_settings

def test_development_allows_demo_defaults(monkeypatch):
    monkeypatch.setenv("VOICELENS_ENV", "development")
    monkeypatch.delenv("DEDUPE_HMAC_SECRET", raising=False)
    assert validate_production_settings().environment == "development"

@pytest.mark.parametrize("changes", [
    {"AUTH_REQUIRED": "false", "DEDUPE_HMAC_SECRET": "real-secret", "DATABASE_URL": "postgresql://db/app"},
    {"AUTH_REQUIRED": "true", "DEDUPE_HMAC_SECRET": DEMO_SECRET, "DATABASE_URL": "postgresql://db/app"},
    {"AUTH_REQUIRED": "true", "DEDUPE_HMAC_SECRET": "real-secret", "DATABASE_URL": "sqlite:///app.db"},
])
def test_production_rejects_unsafe_settings(monkeypatch, changes):
    monkeypatch.setenv("VOICELENS_ENV", "production")
    for key, value in changes.items(): monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError, match="Invalid production settings"):
        validate_production_settings()

def test_production_accepts_safe_settings(monkeypatch):
    monkeypatch.setenv("VOICELENS_ENV", "production")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("DEDUPE_HMAC_SECRET", "a-long-production-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/app")
    monkeypatch.setenv("SESSION_STORE", "db")
    monkeypatch.setenv("AUTH_INSECURE_DEV", "false")
    assert validate_production_settings().environment == "production"
