"""Test defaults keep the local API fixtures in demo mode."""
import os

os.environ.setdefault("AUTH_REQUIRED", "false")

# W11:topic_case 等 support fixture 需显式注册(support/ 不在 pytest 自动发现路径)
from support.topics import topic_case  # noqa: F401
