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
    if errors:
        raise RuntimeError("Invalid production settings: " + "; ".join(errors))
    return cfg
