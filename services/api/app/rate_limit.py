"""Small process-local sliding-window rate limiter for write endpoints."""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from math import ceil

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class WriteRateLimitMiddleware(BaseHTTPMiddleware):
    """Limit dataset uploads and analysis creation per client IP.

    This intentionally stays process-local; production deployments should put a
    shared gateway/Redis limiter in front of multiple API workers.
    Set RATE_LIMIT_PER_MINUTE to 0 (or a negative value) to disable it.
    """

    def __init__(self, app, limit: int | None = None, window_seconds: float = 60.0):
        super().__init__(app)
        raw = os.getenv("RATE_LIMIT_PER_MINUTE", "120") if limit is None else str(limit)
        try:
            self.limit = int(raw)
        except ValueError:
            self.limit = 120
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def _limited(path: str, method: str) -> bool:
        if method.upper() != "POST":
            return False
        return ("/datasets" in path and not path.rstrip("/").endswith("/validate")) or path.rstrip("/").endswith("/analyses")

    async def dispatch(self, request, call_next):
        if self.limit > 0 and self._limited(request.url.path, request.method):
            host = request.client.host if request.client else "unknown"
            key = f"{host}:{request.url.path}"
            now = time.monotonic()
            with self._lock:
                hits = self._hits[key]
                while hits and hits[0] <= now - self.window:
                    hits.popleft()
                if len(hits) >= self.limit:
                    retry = max(1, ceil(self.window - (now - hits[0])))
                    return JSONResponse({"detail": "rate_limit_exceeded"}, status_code=429,
                                        headers={"Retry-After": str(retry)})
                hits.append(now)
        return await call_next(request)
