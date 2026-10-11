"""Redis client management and sliding-window rate limiting.

Implements:
1. Resilient async Redis client with automatic test / offline fallback to fakeredis.
2. Sliding-window rate limiter using Redis Sorted Sets (ZSET) for atomic window tracking.
3. FastAPI dependency for endpoint-level rate limiting on auth and ingestion.
"""

import os
import sys
import time
from collections.abc import Callable
from uuid import uuid4

import fakeredis.aioredis
from fastapi import Request
from redis.asyncio import Redis

from app.core.config import settings
from app.core.errors import AppError

# Global singleton client instance
_redis_client: Redis | None = None


def is_test_environment() -> bool:
    return (
        os.getenv("TESTING", "").lower() in ("1", "true", "yes")
        or "pytest" in sys.modules
        or any("pytest" in arg for arg in sys.argv)
    )


async def get_redis_client() -> Redis:
    """Returns a connected async Redis client.

    Uses real Redis in production/docker; falls back to FakeRedis in testing
    or offline environments to prevent external dependency failure.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    if is_test_environment():
        _redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        return _redis_client

    try:
        client = Redis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        _redis_client = client
        return _redis_client
    except Exception:
        # Fallback to in-memory fake redis if real Redis is unreachable
        _redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        return _redis_client


def set_redis_client(client: Redis | None) -> None:
    """Explicitly inject a Redis client (useful in multi-manager tests)."""
    global _redis_client
    _redis_client = client


async def check_sliding_window_rate_limit(
    redis: Redis,
    key: str,
    max_requests: int,
    window_seconds: int,
) -> tuple[bool, int, int]:
    """Atomic sliding-window rate limiter using Redis Sorted Sets (ZSET).

    Returns:
        (is_allowed, remaining_requests, retry_after_seconds)
    """
    now = time.time()
    window_start = now - window_seconds
    req_id = f"{now}:{uuid4().hex[:8]}"

    pipe = redis.pipeline()
    # 1. Prune entries outside the current sliding window
    pipe.zremrangebyscore(key, 0, window_start)
    # 2. Count active entries in the current window
    pipe.zcard(key)
    # 3. Speculatively add this request
    pipe.zadd(key, {req_id: now})
    # 4. Set TTL to keep Redis memory bounded
    pipe.expire(key, window_seconds + 2)
    results = await pipe.execute()

    count_before = results[1]

    if count_before >= max_requests:
        # Over capacity: remove speculative entry
        await redis.zrem(key, req_id)
        # Calculate retry-after based on oldest entry in window
        earliest = await redis.zrange(key, 0, 0, withscores=True)
        if earliest:
            earliest_time = float(earliest[0][1])
            retry_after = max(1, int(window_seconds - (now - earliest_time)))
        else:
            retry_after = window_seconds
        return False, 0, retry_after

    remaining = max(0, max_requests - count_before - 1)
    return True, remaining, 0


def rate_limiter(
    scope: str,
    max_requests: int = 60,
    window_seconds: int = 60,
) -> Callable:
    """FastAPI dependency factory enforcing a sliding-window rate limit."""

    async def _rate_limit_dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        redis = await get_redis_client()
        rate_key = f"ratelimit:{scope}:{client_ip}"

        allowed, remaining, retry_after = await check_sliding_window_rate_limit(
            redis=redis,
            key=rate_key,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

        if not allowed:
            raise AppError(
                "RATE_LIMIT_EXCEEDED",
                f"Rate limit of {max_requests} requests per {window_seconds}s exceeded. Retry after {retry_after}s.",
                status_code=429,
            )

    return _rate_limit_dependency
