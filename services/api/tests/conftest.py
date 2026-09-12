"""Test defaults keep the local API fixtures in demo mode."""
import os

os.environ.setdefault("AUTH_REQUIRED", "false")
# 显式开发开关:允许 http 场景下的非 Secure Cookie,并跳过无会话请求的 CSRF 校验。
# 带会话 Cookie 的写请求仍然校验 CSRF(见 test_auth_csrf.py)。
os.environ.setdefault("AUTH_INSECURE_DEV", "true")

import pytest

# W11:topic_case 等 support fixture 需显式注册(support/ 不在 pytest 自动发现路径)
from support.client import reset_all  # noqa: E402
from support.topics import topic_case  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _isolate_client_state():
    """会话 Cookie 会在用例间残留,每个用例结束后清空。"""
    yield
    reset_all()
