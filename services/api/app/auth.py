"""Authentication provider: server-side sessions, Argon2id, login throttling.

- Token store is replaceable: in-memory by default, SQL (SESSION_STORE=db)
  for restart-surviving sessions; production config requires the SQL store.
- Demo account passwords are Argon2id hashes; production deployments must
  replace the in-code accounts with a real identity provider.
- Login failures are throttled per account+IP (5/min, 60s backoff) and the
  error message is uniform to avoid username enumeration.
- Each login rotates/revokes the user's previous sessions.
"""
from __future__ import annotations

import os
import secrets
import threading
import time
from collections import defaultdict, deque
from secrets import token_urlsafe
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)

_DEFAULT_TOKEN_TTL_SECONDS = 8 * 3600
_DEFAULT_IDLE_SECONDS = 30 * 60
_LOGIN_FAIL_WINDOW = 60.0
_LOGIN_FAIL_LIMIT = 5
_LOGIN_LOCKOUT_SECONDS = 60.0

_ph = PasswordHasher()

# 演示账号的 Argon2id 哈希(生成后写死;生产必须替换为真实身份提供商)
_USERS = {
    "demo": {
        "id": "demo-user", "email": "demo@voicelens.local", "name": "Demo Analyst", "role": "ANALYST",
        "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$BOlNifCsXp/v/U6+6ZneqQ$tspysmF+6BheqOMNlFx7tBrK40oFQ37snMyLg/ELjiA",
    },
    "viewer": {
        "id": "viewer-user", "email": "viewer@voicelens.local", "name": "Demo Viewer", "role": "VIEWER",
        "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$ZsWn/N8qPOjqSWzrjJKYJw$EZz95/r1qEc9BFkHjVAwzre48FichTDaMhuJXhosVwk",
    },
}


def _token_ttl() -> int:
    try:
        return max(0, int(os.getenv("AUTH_TOKEN_TTL_SECONDS", str(_DEFAULT_TOKEN_TTL_SECONDS))))
    except (TypeError, ValueError):
        return _DEFAULT_TOKEN_TTL_SECONDS


def _idle_ttl() -> int:
    """空闲过期(默认 30 分钟);每次访问滑动续期。"""
    try:
        return max(0, int(os.getenv("AUTH_IDLE_SECONDS", str(_DEFAULT_IDLE_SECONDS))))
    except (TypeError, ValueError):
        return _DEFAULT_IDLE_SECONDS


def insecure_dev() -> bool:
    """显式开发开关:允许非 Secure Cookie 与 http 场景;生产必须为 false。"""
    return os.getenv("AUTH_INSECURE_DEV", "false").strip().lower() in ("1", "true", "yes", "on")


SESSION_COOKIE = "vl_session"
CSRF_COOKIE = "vl_csrf"
CSRF_HEADER = "X-CSRF-Token"


def _cookie_secure() -> bool:
    return not insecure_dev()


def _allowed_origins() -> list[str]:
    raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173,http://localhost:8080,http://127.0.0.1:8080",
    )
    return [item.strip() for item in raw.split(",") if item.strip()]


def set_session_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=max_age, httponly=True, secure=_cookie_secure(), samesite="lax", path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=_cookie_secure(), samesite="lax")


def issue_csrf_token() -> str:
    """预登录 CSRF token:双提交 Cookie,前端读取后放入请求头。"""
    return token_urlsafe(24)


def set_csrf_cookie(response: Response, token: str) -> None:
    # 前端需要读取该值放入头部,因此不能是 HttpOnly
    response.set_cookie(CSRF_COOKIE, token, httponly=False, secure=_cookie_secure(), samesite="lax", path="/")


def csrf_required(http_request) -> bool:
    """开发环境下无会话的请求(预登录/演示旁路)不校验 CSRF;其余一律校验。

    生产环境(insecure dev 关闭)对包括登录在内的所有写请求校验,
    这正是「登录前先取预登录 CSRF token」的落点。
    """
    if insecure_dev() and not http_request.cookies.get(SESSION_COOKIE):
        return False
    return True


def verify_csrf(http_request) -> None:
    """写请求必须携带匹配的 CSRF 头,且 Origin 在白名单内。"""
    if not csrf_required(http_request):
        return
    origin = http_request.headers.get("origin")
    if origin and origin not in _allowed_origins():
        raise HTTPException(status_code=403, detail={"code": "origin_not_allowed"})
    cookie_token = http_request.cookies.get(CSRF_COOKIE)
    header_token = http_request.headers.get(CSRF_HEADER)
    if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail={"code": "csrf_failed"})


class TokenStore:
    def issue(self, user: dict) -> str: ...
    def get(self, token: str) -> dict | None: ...
    def is_expired(self, token: str) -> bool: ...
    def revoke(self, token: str) -> None: ...
    def revoke_user_sessions(self, user_id: str) -> None: ...


class InMemoryTokenStore(TokenStore):
    def __init__(self):
        self._tokens: dict[str, dict] = {}

    def issue(self, user: dict) -> str:
        token = token_urlsafe(32)
        self._tokens[token] = dict(user)
        return token

    def get(self, token: str) -> dict | None:
        session = self._tokens.get(token)
        if session is None:
            return None
        now = time.time()
        if now >= session["exp"]:
            return None  # 保留记录供 is_expired 区分「过期」与「不存在」
        idle_exp = session.get("idle_exp")
        if idle_exp is not None and now >= idle_exp:
            return None  # 空闲过期
        if idle_exp is not None:
            session["idle_exp"] = now + _idle_ttl()  # 滑动续期
        return session

    def is_expired(self, token: str) -> bool:
        session = self._tokens.get(token)
        return session is not None and time.time() >= session["exp"]

    def revoke(self, token: str) -> None:
        self._tokens.pop(token, None)

    def revoke_user_sessions(self, user_id: str) -> None:
        for token in [t for t, s in self._tokens.items() if s.get("id") == user_id]:
            self._tokens.pop(token, None)


class SqlTokenStore(TokenStore):
    """SESSION_STORE=db:会话写入 session_tokens 表,重启不失效。"""

    def __init__(self):
        from .db import Base, SessionLocal
        from .models import SessionToken
        self._SessionLocal = SessionLocal
        self._SessionToken = SessionToken
        # 确保表存在(生产由 Alembic 迁移管理;演示环境 create_all 兜底)
        with SessionLocal() as session:
            Base.metadata.create_all(session.get_bind())

    def issue(self, user: dict) -> str:
        from sqlalchemy import delete
        token = token_urlsafe(32)
        with self._SessionLocal() as session, session.begin():
            session.execute(delete(self._SessionToken).where(self._SessionToken.user_id == user["id"]))
            now = time.time()
            session.add(self._SessionToken(
                token=token, user_id=user["id"], role=user.get("role", "ANALYST"),
                projects=user.get("projects", []), issued_at=now, exp=user["exp"],
                idle_exp=user.get("idle_exp", now + _idle_ttl()),
            ))
        return token

    def get(self, token: str) -> dict | None:
        now = time.time()
        with self._SessionLocal() as session, session.begin():
            row = session.get(self._SessionToken, token)
            if row is None:
                return None
            if now >= row.exp:
                return None  # 保留行供 is_expired 区分「过期」与「不存在」
            if row.idle_exp is not None and now >= row.idle_exp:
                return None
            if row.idle_exp is not None:
                row.idle_exp = now + _idle_ttl()  # 滑动续期
            return {"id": row.user_id, "role": row.role, "projects": row.projects, "exp": row.exp}

    def is_expired(self, token: str) -> bool:
        with self._SessionLocal() as session:
            row = session.get(self._SessionToken, token)
            return row is not None and time.time() >= row.exp

    def revoke(self, token: str) -> None:
        with self._SessionLocal() as session, session.begin():
            row = session.get(self._SessionToken, token)
            if row is not None:
                session.delete(row)

    def revoke_user_sessions(self, user_id: str) -> None:
        from sqlalchemy import delete
        with self._SessionLocal() as session, session.begin():
            session.execute(delete(self._SessionToken).where(self._SessionToken.user_id == user_id))


_store: TokenStore | None = None


def get_token_store() -> TokenStore:
    global _store
    if _store is None:
        _store = SqlTokenStore() if os.getenv("SESSION_STORE", "memory") == "db" else InMemoryTokenStore()
    return _store


def reset_token_store(store: TokenStore | None = None) -> None:
    """测试钩子:替换/重置 token store。"""
    global _store
    _store = store


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


_fail_events: defaultdict[str, deque[float]] = defaultdict(deque)
_fail_lock = threading.Lock()


def _login_rate_limited(key: str) -> tuple[bool, int]:
    """账号+IP 失败计数:窗口内 5 次失败起 60s 退避。"""
    now = time.monotonic()
    with _fail_lock:
        events = _fail_events[key]
        while events and events[0] <= now - _LOGIN_FAIL_WINDOW:
            events.popleft()
        if len(events) >= _LOGIN_FAIL_LIMIT:
            return True, int(_LOGIN_LOCKOUT_SECONDS)
        return False, 0


def _record_login_failure(key: str) -> None:
    with _fail_lock:
        _fail_events[key].append(time.monotonic())


def _public(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]}


def _projects(user: dict) -> list[dict]:
    role = user["role"]
    return [{"project_id": "demo-project", "role": role,
             "permissions": ["read", "analyze"] if role != "VIEWER" else ["read"]}]


def _verify_password(user: dict, password: str) -> bool:
    try:
        _ph.verify(user["password_hash"], password)
        return True
    except VerifyMismatchError:
        return False


def session_token_of(http_request, credentials) -> str | None:
    """浏览器用 HttpOnly Cookie,非浏览器客户端用 Bearer;两者等价。"""
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return http_request.cookies.get(SESSION_COOKIE)


def current_user(
    http_request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> dict:
    token = session_token_of(http_request, credentials)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "unauthorized"},
                            headers={"WWW-Authenticate": "Bearer"})
    store = get_token_store()
    session = store.get(token)
    if session is None:
        code = 'token_expired' if store.is_expired(token) else 'unauthorized'
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": code},
                            headers={"WWW-Authenticate": "Bearer"})
    return session


def require_user(
    http_request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> dict:
    """Require a valid session (cookie or bearer) when AUTH_REQUIRED is enabled.

    Demo mode deliberately supplies an analyst identity so existing local
    workflows remain usable without a login round trip.
    """
    required = os.getenv("AUTH_REQUIRED", "true").lower() in ("1", "true", "yes", "on")
    if not required and not session_token_of(http_request, credentials):
        return _public(_USERS["demo"]) | {"demo_bypass": True, "projects": [{"project_id": "demo-project", "role": "ANALYST", "permissions": ["read", "analyze"]}]}
    return current_user(http_request, credentials)


def require_analyst(user: Annotated[dict, Depends(require_user)]) -> dict:
    if user.get("role", "ANALYST").upper() == "VIEWER":
        raise HTTPException(status_code=403, detail={"code": "forbidden"})
    return user


@router.get("/csrf")
def csrf_token(response: Response):
    """预登录 CSRF token:双提交 Cookie,登录与所有写接口都要回传该值。"""
    token = issue_csrf_token()
    set_csrf_cookie(response, token)
    return {"csrf_token": token}


@router.post("/login")
def login(request: LoginRequest, http_request: Request, response: Response):
    verify_csrf(http_request)
    user = _USERS.get(request.username)
    client = http_request.client.host if http_request.client else "unknown"
    rate_key = f"{request.username}:{client}"
    limited, retry = _login_rate_limited(rate_key)
    if limited:
        raise HTTPException(status_code=429, detail={"code": "rate_limited"},
                            headers={"Retry-After": str(retry)})
    if user is None or not _verify_password(user, request.password):
        _record_login_failure(rate_key)
        # 统一错误文案,不泄露账号存在性
        raise HTTPException(status_code=401, detail={"code": "invalid_credentials"})
    issued_at = time.time()
    ttl = _token_ttl()
    session = _public(user) | {
        "projects": _projects(user), "issued_at": issued_at,
        "exp": issued_at + ttl, "idle_exp": issued_at + _idle_ttl(),
    }
    store = get_token_store()
    # 登录成功轮换/撤销该用户旧会话(单会话)
    store.revoke_user_sessions(user["id"])
    token = store.issue(session)
    set_session_cookie(response, token, max_age=ttl)
    # access_token 仍返回,供非浏览器客户端使用;浏览器以 HttpOnly Cookie 为准
    return {"access_token": token, "token_type": "bearer", "expires_in": ttl,
            "user": _public(user) | {"projects": _projects(user)}}


@router.get("/me")
def me(user: Annotated[dict, Depends(current_user)]):
    return user


@router.post("/logout", status_code=204)
def logout(http_request: Request, response: Response,
           credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    token = credentials.credentials if credentials else http_request.cookies.get(SESSION_COOKIE)
    if token:
        get_token_store().revoke(token)
    clear_session_cookie(response)


def require_project_access(project_id: str, user: Annotated[dict, Depends(require_user)]) -> dict:
    """Hide projects outside the authenticated principal's membership list."""
    if user.get("demo_bypass"):
        return user
    membership = next((item for item in user.get("projects", []) if item.get("project_id") == project_id), None)
    if membership is None:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"})
    return {**user, "role": membership.get("role", "VIEWER")}


def require_project_analyst(user: Annotated[dict, Depends(require_project_access)]) -> dict:
    return require_analyst(user)
