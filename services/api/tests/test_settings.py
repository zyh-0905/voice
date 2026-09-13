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
    # 14.1:生产禁止 mock 命名。manual 是允许的「无外部 LLM」档,所以显式选它。
    monkeypatch.setenv("NAMING_MODE", "manual")
    assert validate_production_settings().environment == "production"


def test_production_rejects_mock_naming(monkeypatch):
    """默认值是 mock,而 mock 命名会用确定性的演示数据冒充模型产出——看起来完全正常。"""
    monkeypatch.setenv("VOICELENS_ENV", "production")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("DEDUPE_HMAC_SECRET", "a-long-production-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/app")
    monkeypatch.setenv("SESSION_STORE", "db")
    monkeypatch.setenv("AUTH_INSECURE_DEV", "false")
    monkeypatch.setenv("NAMING_MODE", "mock")
    with pytest.raises(RuntimeError, match="NAMING_MODE"):
        validate_production_settings()


def test_production_requires_pricing_when_using_a_provider(monkeypatch):
    """10.5:没有可靠价格配置时禁用付费模式——生产选 provider 却没价格必须拦下。"""
    monkeypatch.setenv("VOICELENS_ENV", "production")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("DEDUPE_HMAC_SECRET", "a-long-production-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/app")
    monkeypatch.setenv("SESSION_STORE", "db")
    monkeypatch.setenv("AUTH_INSECURE_DEV", "false")
    monkeypatch.setenv("NAMING_MODE", "provider")
    monkeypatch.setenv("MODEL_ENDPOINT", "https://model.example/v1")
    monkeypatch.setenv("MODEL_ID", "some-model")
    monkeypatch.delenv("MODEL_PRICE_IN", raising=False)
    monkeypatch.delenv("MODEL_PRICE_OUT", raising=False)
    with pytest.raises(RuntimeError, match="MODEL_PRICE_IN"):
        validate_production_settings()

    monkeypatch.setenv("MODEL_PRICE_IN", "0.000001")
    monkeypatch.setenv("MODEL_PRICE_OUT", "0.000002")
    assert validate_production_settings().environment == "production"
