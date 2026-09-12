"""共享 TestClient:模块级复用,但每个用例结束后清空 Cookie 与请求头。

Cookie 会话上线后,一个用例里的登录会通过 Set-Cookie 影响后续用例
(共享客户端会保留 cookie jar),因此必须在用例之间清理。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

_CLIENTS: list[TestClient] = []


def make_client() -> TestClient:
    client = TestClient(app)
    _CLIENTS.append(client)
    return client


def reset_all() -> None:
    for client in _CLIENTS:
        client.cookies.clear()
        client.headers.pop("Authorization", None)
