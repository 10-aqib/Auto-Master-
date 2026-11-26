"""RedisRateLimiter against a real Redis (skipped unless TEST_REDIS_URL is set)."""

from __future__ import annotations

import os
import uuid

import pytest
import redis

from webforge_api.security.rate_limit import RateLimiterUnavailableError, RedisRateLimiter

TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "")


@pytest.fixture
def limiter() -> RedisRateLimiter:
    if not TEST_REDIS_URL:
        if os.environ.get("REQUIRE_DB_TESTS") == "1":
            pytest.fail("REQUIRE_DB_TESTS=1 but TEST_REDIS_URL is not set")
        pytest.skip("TEST_REDIS_URL not set")
    return RedisRateLimiter(redis.Redis.from_url(TEST_REDIS_URL))


def test_redis_limiter_counts_and_resets(limiter: RedisRateLimiter) -> None:
    key = f"test:{uuid.uuid4().hex}"
    assert [limiter.hit(key, limit=2, window_seconds=60) for _ in range(3)] == [True, True, False]
    limiter.reset(key)
    assert limiter.hit(key, limit=2, window_seconds=60)


def test_redis_outage_raises_unavailable() -> None:
    broken = RedisRateLimiter(
        redis.Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    )
    with pytest.raises(RateLimiterUnavailableError):
        broken.hit("k", limit=1, window_seconds=60)
