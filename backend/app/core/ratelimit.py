"""
Precision AI - In-process sliding-window rate limiter.
Used for per-IP and per-user request budgets. The app runs a single worker (FAISS is in-process), so
process memory is the right scope; account lockouts that must survive restarts live in the database.
"""

import threading
import time
from collections import deque
from typing import Optional

from fastapi import HTTPException, status


class SlidingWindowLimiter:
    def __init__(self):
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _window(self, key: str, window_seconds: float, now: float) -> deque[float]:
        events = self._events.setdefault(key, deque())
        while events and events[0] <= now - window_seconds:
            events.popleft()
        return events

    def retry_after(self, key: str, limit: int, window_seconds: float) -> Optional[int]:
        """Seconds until one more event is allowed, or None if the budget is not exhausted."""
        now = time.monotonic()
        with self._lock:
            events = self._window(key, window_seconds, now)
            if len(events) < limit:
                return None
            return max(1, int(events[0] + window_seconds - now) + 1)

    def record(self, key: str, window_seconds: float) -> None:
        now = time.monotonic()
        with self._lock:
            self._window(key, window_seconds, now).append(now)

    def hit(self, key: str, limit: int, window_seconds: float) -> Optional[int]:
        """Record an event unless the budget is exhausted; returns the retry delay when refused."""
        wait = self.retry_after(key, limit, window_seconds)
        if wait is None:
            self.record(key, window_seconds)
        return wait

    def reset(self, prefix: str = "") -> None:
        with self._lock:
            for key in [k for k in self._events if k.startswith(prefix)]:
                del self._events[key]


limiter = SlidingWindowLimiter()


def too_many(retry_after: int, message: str) -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, message, headers={"Retry-After": str(retry_after)})


def enforce(key: str, limit: int, window_seconds: float, message: str) -> None:
    wait = limiter.hit(key, limit, window_seconds)
    if wait is not None:
        raise too_many(wait, message)


def enforce_chat_budget(user_id: int) -> None:
    """Per-user budget for chat messages and portal tickets: bounds paid-LLM spend if a cloud tier is configured."""
    from app.core.config import get_settings

    enforce(f"chat:{user_id}", get_settings().RATE_LIMIT_CHAT_PER_MINUTE, 60,
            "You're sending messages very quickly. Wait a minute and try again.")
