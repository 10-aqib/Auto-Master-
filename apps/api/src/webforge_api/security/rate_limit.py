"""Fixed-window rate limiting. Redis in the app; in-memory for tests."""

from __future__ import annotations

import threading
import time
from typing import Protocol

import redis


class RateLimiterUnavailableError(Exception):
    """The backing store failed; callers must fail closed."""


class RateLimiter(Protocol):
    def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        """Record one hit. Return True when the request is allowed."""
        ...

    def reset(self, key: str) -> None: ...


class RedisRateLimiter:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        bucket = f"rl:{key}:{int(time.time()) // window_seconds}"
        try:
            pipe = self._client.pipeline()
            pipe.incr(bucket)
            pipe.expire(bucket, window_seconds + 1, nx=True)
            count, _ = pipe.execute()
        except redis.RedisError as exc:
            raise RateLimiterUnavailableError from exc
        return int(count) <= limit

    def reset(self, key: str) -> None:
        try:
            for bucket in self._client.scan_iter(match=f"rl:{key}:*", count=100):
                self._client.delete(bucket)
        except redis.RedisError as exc:
            raise RateLimiterUnavailableError from exc


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        bucket = f"{key}:{int(time.time()) // window_seconds}"
        with self._lock:
            self._counts[bucket] = self._counts.get(bucket, 0) + 1
            return self._counts[bucket] <= limit

    def reset(self, key: str) -> None:
        with self._lock:
            for bucket in [b for b in self._counts if b.startswith(f"{key}:")]:
                del self._counts[bucket]
