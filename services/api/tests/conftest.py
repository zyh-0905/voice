"""Test defaults keep the local API fixtures in demo mode."""
import os

os.environ.setdefault("AUTH_REQUIRED", "false")
