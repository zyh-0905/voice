import pytest
from app.settings import DEMO_SECRET, load_settings, validate_production_settings

# LOCAL_ACCOUNTS 的形状见 app.admin CLI 输出(用户名 → 账号记录)。
LOCAL_ACCOUNTS_JSON = '{"analyst-1": {"id": "u1", "role": "ANALYST", "password_hash": "x"}}'

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
    # 8.2:生产不允许哈希替身
    monkeypatch.setenv("EMBEDDING_MODE", "api")
    monkeypatch.setenv("EMBEDDING_ENDPOINT", "https://embed.example/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "bge-small-zh-v1.5")
    # 身份:local provider 必须显式给出账号,否则会启用内置演示账号
    monkeypatch.setenv("LOCAL_ACCOUNTS", LOCAL_ACCOUNTS_JSON)
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
    monkeypatch.setenv("EMBEDDING_MODE", "api")
    monkeypatch.setenv("EMBEDDING_ENDPOINT", "https://embed.example/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "bge-small-zh-v1.5")
    monkeypatch.setenv("LOCAL_ACCOUNTS", LOCAL_ACCOUNTS_JSON)
    assert validate_production_settings().environment == "production"


def test_production_rejects_the_hashing_embedding_standin(monkeypatch):
    """8.2:计划冻结的是真实向量模型;替身只作演示,生产放行等于「分析能力」名存实亡。"""
    monkeypatch.setenv("VOICELENS_ENV", "production")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("DEDUPE_HMAC_SECRET", "a-long-production-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/app")
    monkeypatch.setenv("SESSION_STORE", "db")
    monkeypatch.setenv("AUTH_INSECURE_DEV", "false")
    monkeypatch.setenv("NAMING_MODE", "manual")
    monkeypatch.setenv("EMBEDDING_MODE", "hashing")
    with pytest.raises(RuntimeError, match="EMBEDDING_MODE"):
        validate_production_settings()


def _production_baseline(monkeypatch):
    """一组**其余项都合规**的生产配置,便于单独验证某一项闸门。"""
    monkeypatch.setenv("VOICELENS_ENV", "production")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("DEDUPE_HMAC_SECRET", "a-long-production-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/app")
    monkeypatch.setenv("SESSION_STORE", "db")
    monkeypatch.setenv("AUTH_INSECURE_DEV", "false")
    monkeypatch.setenv("NAMING_MODE", "manual")
    monkeypatch.setenv("EMBEDDING_MODE", "api")
    monkeypatch.setenv("EMBEDDING_ENDPOINT", "https://embed.example/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "bge-small-zh-v1.5")


def test_production_rejects_the_builtin_demo_accounts(monkeypatch):
    """LOCAL_ACCOUNTS 未设时 identity 会回落到内置的 demo/demo、viewer/viewer。

    其余每一项演示默认值都有闸门(NAMING_MODE=mock、EMBEDDING_MODE=hashing、
    DEDUPE_HMAC_SECRET=DEMO_SECRET),唯独账号这一项没有——而它恰恰是部署时最容易
    漏掉的一个:什么都不设就能登录,且启动日志里看不出异常。
    """
    _production_baseline(monkeypatch)
    monkeypatch.delenv("LOCAL_ACCOUNTS", raising=False)
    monkeypatch.delenv("IDENTITY_PROVIDER", raising=False)
    with pytest.raises(RuntimeError, match="LOCAL_ACCOUNTS"):
        validate_production_settings()


def test_production_rejects_demo_accounts_under_an_explicit_local_provider(monkeypatch):
    """显式写 IDENTITY_PROVIDER=local 不足以放行:仍要给出真实账号。"""
    _production_baseline(monkeypatch)
    monkeypatch.setenv("IDENTITY_PROVIDER", "local")
    monkeypatch.delenv("LOCAL_ACCOUNTS", raising=False)
    with pytest.raises(RuntimeError, match="LOCAL_ACCOUNTS"):
        validate_production_settings()


def test_production_accepts_oidc_without_local_accounts(monkeypatch):
    """走外部身份提供商时内置账号根本不会被加载,不应因此拦下。"""
    _production_baseline(monkeypatch)
    monkeypatch.setenv("IDENTITY_PROVIDER", "oidc")
    monkeypatch.delenv("LOCAL_ACCOUNTS", raising=False)
    assert validate_production_settings().environment == "production"



# —— .env.production.example 模板契约 ——
# 模板是「生产闸门要求的最小集」的镜像:settings.py 每新增一条闸门,模板就必须
# 跟着加键,否则部署方照抄模板仍被拦、而且拦在「模板漏键」而不是「值待填」。

def _load_production_template() -> dict[str, str]:
    from pathlib import Path
    path = Path(__file__).resolve().parents[3] / ".env.production.example"
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def test_production_template_satisfies_every_gate(monkeypatch):
    """模板键必须足以通过全部生产闸门:空值全填占位串后校验应当通过。"""
    template = _load_production_template()
    assert template["VOICELENS_ENV"] == "production", "模板必须以生产口径为默认"
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/app")
    for key, value in template.items():
        # 只填空值;模板里已有的语义值(production/api/provider/...)原样生效
        monkeypatch.setenv(key, value or "placeholder-value")
    assert validate_production_settings().environment == "production"


def test_production_template_blank_secrets_fail_loudly(monkeypatch):
    """按原样(空值)部署必须被拦,且拦截点是待填的密钥项——这是刻意的。"""
    template = _load_production_template()
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/app")
    for key, value in template.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError) as excinfo:
        validate_production_settings()
    message = str(excinfo.value)
    assert "DEDUPE_HMAC_SECRET" in message
    assert "LOCAL_ACCOUNTS" in message
