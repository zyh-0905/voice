"""Validated runtime configuration and production safety guardrails."""
from dataclasses import dataclass
import os

DEMO_SECRET = "voicelens-demo-dedupe-secret"

def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

@dataclass(frozen=True)
class RuntimeSettings:
    environment: str
    auth_required: bool
    dedupe_hmac_secret: str | None
    database_url: str

def load_settings() -> RuntimeSettings:
    return RuntimeSettings(
        environment=os.getenv("VOICELENS_ENV", "development").strip().lower(),
        auth_required=_bool("AUTH_REQUIRED", True),
        dedupe_hmac_secret=os.getenv("DEDUPE_HMAC_SECRET"),
        database_url=os.getenv("DATABASE_URL", "postgresql://localhost/voicelens"),
    )

def validate_production_settings(settings: RuntimeSettings | None = None) -> RuntimeSettings:
    """Fail fast on unsafe production configuration; no-op for local/demo envs."""
    cfg = settings or load_settings()
    if cfg.environment != "production":
        return cfg
    errors: list[str] = []
    if not cfg.auth_required:
        errors.append("AUTH_REQUIRED must be true in production")
    if not cfg.dedupe_hmac_secret or cfg.dedupe_hmac_secret == DEMO_SECRET:
        errors.append("DEDUPE_HMAC_SECRET must be a non-demo secret in production")
    if cfg.database_url.strip().lower().startswith("sqlite"):
        errors.append("DATABASE_URL must not use sqlite in production")
    if os.getenv("SESSION_STORE", "memory") != "db":
        errors.append("SESSION_STORE must be db in production (server-side sessions must survive restarts)")
    if os.getenv("AUTH_INSECURE_DEV", "false").strip().lower() in ("1", "true", "yes", "on"):
        errors.append("AUTH_INSECURE_DEV must be false in production (insecure cookies are dev-only)")
    # 14.1:production 禁止 mock 命名;manual 允许无外部 LLM。
    # 不拦的话,一个把 NAMING_MODE 忘在默认值的生产部署会用确定性命名的演示数据
    # 冒充模型产出——而它看起来完全正常。
    naming_mode = (os.getenv("NAMING_MODE") or "mock").strip().lower()
    if naming_mode not in ("provider", "manual"):
        errors.append(
            "NAMING_MODE must be provider or manual in production "
            f"(got {naming_mode!r}); mock naming is demo-only")
    if naming_mode == "provider":
        if not (os.getenv("MODEL_ENDPOINT") or "").strip():
            errors.append("MODEL_ENDPOINT must be set when NAMING_MODE=provider")
        if not (os.getenv("MODEL_ID") or "").strip():
            errors.append("MODEL_ID must be set when NAMING_MODE=provider")
        # 10.5:没有可靠价格配置时禁用付费模式。生产选 provider 却没有价格,
        # 说明部署方打算花钱但算不出花了多少——那不该悄悄放行。
        if not (os.getenv("MODEL_PRICE_IN") or "").strip() or not (os.getenv("MODEL_PRICE_OUT") or "").strip():
            errors.append(
                "MODEL_PRICE_IN / MODEL_PRICE_OUT must be set when NAMING_MODE=provider "
                "(10.5: paid mode is disabled without reliable pricing)")
    # 8.2:计划冻结的是真实向量模型,而哈希替身只作演示。生产放行替身等于让
    # 「分析能力」名义上存在、实际跑在确定性哈希上——正是要禁止的那种偏离。
    embedding_mode = (os.getenv("EMBEDDING_MODE") or "hashing").strip().lower()
    if embedding_mode not in ("api",):
        errors.append(
            "EMBEDDING_MODE must be api in production "
            f"(got {embedding_mode!r}); the hashing stand-in is demo-only")
    else:
        if not (os.getenv("EMBEDDING_ENDPOINT") or "").strip():
            errors.append("EMBEDDING_ENDPOINT must be set when EMBEDDING_MODE=api")
        if not (os.getenv("EMBEDDING_MODEL") or "").strip():
            errors.append("EMBEDDING_MODEL must be set when EMBEDDING_MODE=api")
    if errors:
        raise RuntimeError("Invalid production settings: " + "; ".join(errors))
    return cfg
