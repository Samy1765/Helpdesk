"""
Precision AI - In-memory sliding-window rate limiter for the authentication endpoints.
Per process: enough for a single-instance deployment; a multi-instance deployment would back it with Redis.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


class RateLimiter:
    def __init__(self, window_seconds: float = 60.0):
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int) -> bool:
        """Record one attempt for `key`; False when the key has used up its `limit` in the window."""
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


auth_limiter = RateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def limit_auth_attempts(request: Request) -> None:
    """Dependency: at most AUTH_RATE_LIMIT_PER_MINUTE login/register attempts per client IP and route."""
    if not auth_limiter.check(f"{request.url.path}:{client_ip(request)}", get_settings().AUTH_RATE_LIMIT_PER_MINUTE):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Please wait a minute and try again.",
                            headers={"Retry-After": "60"})
