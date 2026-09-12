"""身份提供商抽象:本地账号(默认)或外部 OIDC。

演示账号只作为本地 provider 的默认值;生产用 LOCAL_ACCOUNTS 注入真实账号
(哈希由 app.admin CLI 生成),或切换 IDENTITY_PROVIDER=oidc 走外部身份提供商。
认证结果统一映射为 {id, email, name, role},角色取值 ANALYST / VIEWER。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable, Protocol

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, status

_ph = PasswordHasher()

# 演示账号(Argon2id 哈希,密码分别为 demo / viewer);生产必须用 LOCAL_ACCOUNTS 覆盖
DEMO_ACCOUNTS: dict[str, dict] = {
    "demo": {
        "id": "demo-user", "email": "demo@voicelens.local", "name": "Demo Analyst", "role": "ANALYST",
        "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$BOlNifCsXp/v/U6+6ZneqQ$tspysmF+6BheqOMNlFx7tBrK40oFQ37snMyLg/ELjiA",
    },
    "viewer": {
        "id": "viewer-user", "email": "viewer@voicelens.local", "name": "Demo Viewer", "role": "VIEWER",
        "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$ZsWn/N8qPOjqSWzrjJKYJw$EZz95/r1qEc9BFkHjVAwzre48FichTDaMhuJXhosVwk",
    },
}


class IdentityError(HTTPException):
    pass


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _ph.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


def _public(record: dict) -> dict:
    return {
        "id": record["id"], "email": record.get("email", ""),
        "name": record.get("name", record["id"]), "role": str(record.get("role", "VIEWER")).upper(),
    }


def load_local_accounts() -> dict[str, dict]:
    """LOCAL_ACCOUNTS(JSON)覆盖内置演示账号;格式见 app.admin CLI 输出。"""
    raw = os.getenv("LOCAL_ACCOUNTS")
    if not raw:
        return dict(DEMO_ACCOUNTS)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LOCAL_ACCOUNTS must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("LOCAL_ACCOUNTS must be an object keyed by username")
    return parsed


@dataclass
class LocalAccountProvider:
    """用户名 + 密码,Argon2id 校验;账号来自 LOCAL_ACCOUNTS 或内置演示账号。"""

    name: str = "local"

    def __post_init__(self) -> None:
        self.accounts = load_local_accounts()

    def authenticate(self, username: str, password: str) -> dict | None:
        record = self.accounts.get(username)
        if record is None or not verify_password(record.get("password_hash", ""), password):
            return None
        return _public(record)

    def describe(self) -> dict:
        return {"mode": "local"}


@dataclass
class OidcProvider:
    """外部 OIDC:校验 ID token 的签名(JWKS/RS256)、issuer、audience 与有效期。"""

    issuer: str
    audience: str
    jwks_url: str
    role_claim: str = "role"
    default_role: str = "VIEWER"
    name: str = "oidc"
    # 测试可注入;默认走 PyJWKClient 拉取 JWKS
    key_resolver: Callable[[str], object] | None = None

    def _signing_key(self, token: str):
        if self.key_resolver is not None:
            return self.key_resolver(token)
        from jwt import PyJWKClient
        return PyJWKClient(self.jwks_url).get_signing_key_from_jwt(token).key

    def verify_assertion(self, assertion: str) -> dict | None:
        import jwt
        try:
            key = self._signing_key(assertion)
            claims = jwt.decode(
                assertion, key, algorithms=["RS256"],
                audience=self.audience, issuer=self.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except Exception:
            # 任何校验失败一律视为未认证,不向调用方泄露具体原因
            return None
        role = str(claims.get(self.role_claim) or self.default_role).upper()
        return _public({
            "id": str(claims["sub"]),
            "email": claims.get("email", ""),
            "name": claims.get("name") or claims.get("preferred_username") or claims["sub"],
            "role": role,
        })

    def authenticate(self, username: str, password: str) -> dict | None:
        # OIDC 模式不接受表单密码:应使用 SSO 断言(见 /auth/token)
        return None

    def describe(self) -> dict:
        return {
            "mode": "oidc", "issuer": self.issuer, "audience": self.audience,
            "assertion_endpoint": "/api/v1/auth/token",
        }


def get_identity_provider() -> LocalAccountProvider | OidcProvider:
    mode = os.getenv("IDENTITY_PROVIDER", "local").strip().lower()
    if mode == "local":
        return LocalAccountProvider()
    if mode == "oidc":
        issuer = os.getenv("OIDC_ISSUER")
        audience = os.getenv("OIDC_AUDIENCE")
        jwks_url = os.getenv("OIDC_JWKS_URL")
        missing = [k for k, v in (("OIDC_ISSUER", issuer), ("OIDC_AUDIENCE", audience), ("OIDC_JWKS_URL", jwks_url)) if not v]
        if missing:
            raise RuntimeError(f"IDENTITY_PROVIDER=oidc requires {', '.join(missing)}")
        return OidcProvider(
            issuer=issuer, audience=audience, jwks_url=jwks_url,
            role_claim=os.getenv("OIDC_ROLE_CLAIM", "role"),
            default_role=os.getenv("OIDC_DEFAULT_ROLE", "VIEWER"),
        )
    raise RuntimeError(f"unsupported IDENTITY_PROVIDER: {mode}")


def unauthenticated() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "invalid_credentials"})
