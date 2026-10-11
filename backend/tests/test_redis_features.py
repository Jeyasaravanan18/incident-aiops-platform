"""Tests for Redis-backed sliding-window rate limiting and WebSocket pub/sub fan-out.

Validates:
1. Atomic sliding-window rate limiter limits requests within the window and resets when window elapses.
2. HTTP 429 Too Many Requests is returned by rate-limited endpoints when limit is exceeded.
3. Multi-worker WebSocket fan-out: messages broadcast from one manager instance
   are delivered across Redis Pub/Sub to WebSockets connected to other manager instances.
"""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.redis import check_sliding_window_rate_limit, get_redis_client
from app.main import app
from app.websocket.manager import WebSocketManager


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter_logic() -> None:
    """Tests sorted-set sliding window atomic rate limiting."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    rate_key = f"ratelimit:test:{uuid4()}"
    limit = 5
    window_seconds = 2

    # First 5 requests must all be allowed
    for i in range(limit):
        allowed, remaining, retry_after = await check_sliding_window_rate_limit(
            redis=redis,
            key=rate_key,
            max_requests=limit,
            window_seconds=window_seconds,
        )
        assert allowed is True
        assert remaining == limit - i - 1
        assert retry_after == 0

    # 6th request within window must be rejected
    allowed, remaining, retry_after = await check_sliding_window_rate_limit(
        redis=redis,
        key=rate_key,
        max_requests=limit,
        window_seconds=window_seconds,
    )
    assert allowed is False
    assert remaining == 0
    assert retry_after >= 1

    # Wait for the sliding window to elapse
    await asyncio.sleep(2.1)

    # Next request must now succeed
    allowed, remaining, retry_after = await check_sliding_window_rate_limit(
        redis=redis,
        key=rate_key,
        max_requests=limit,
        window_seconds=window_seconds,
    )
    assert allowed is True
    assert remaining == limit - 1


@pytest.mark.asyncio
async def test_endpoint_rate_limiting_returns_429() -> None:
    """Verifies that exceeding the sliding-window rate limit on the auth endpoint returns HTTP 429."""
    redis = await get_redis_client()
    test_ip = "198.51.100.99"
    rate_key = f"ratelimit:auth:login:{test_ip}"
    await redis.delete(rate_key)

    # Pre-populate 20 requests in the window for this IP to hit limit
    for _ in range(20):
        await check_sliding_window_rate_limit(redis, rate_key, 20, 60)

    # Now an HTTP call with this client IP triggers HTTP 429
    transport = ASGITransport(app=app, client=(test_ip, 50000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "Password123!"},
        )
        assert resp.status_code == 429
        data = resp.json()
        assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_websocket_fanout_across_manager_instances() -> None:
    """Tests multi-worker WebSocket synchronization via Redis Pub/Sub.

    Manager A and Manager B represent two distinct backend worker processes.
    A message broadcast on Manager A must be received by WebSockets connected to Manager B.
    """
    shared_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    manager_a = WebSocketManager(redis_client=shared_redis)
    manager_b = WebSocketManager(redis_client=shared_redis)

    await manager_a.start()
    await manager_b.start()

    # Small delay for pub/sub subscription to register in Redis
    await asyncio.sleep(0.05)

    # Create mock WebSockets for both workers
    ws_on_worker_a = AsyncMock()
    ws_on_worker_a.send_text = AsyncMock()

    ws_on_worker_b = AsyncMock()
    ws_on_worker_b.send_text = AsyncMock()

    # Worker A accepts client 1 on "dashboard"
    manager_a._channels["dashboard"].add(ws_on_worker_a)
    # Worker B accepts client 2 on "dashboard"
    manager_b._channels["dashboard"].add(ws_on_worker_b)

    payload = {
        "type": "IncidentCreated",
        "incident_id": str(uuid4()),
        "severity": "SEV1",
        "title": "Cross-worker Redis fanout event",
    }

    # Worker A broadcasts the event
    await manager_a.broadcast("dashboard", payload)

    # Allow event loop to process Redis pub/sub message delivery
    for _ in range(20):
        if ws_on_worker_b.send_text.called and ws_on_worker_a.send_text.called:
            break
        await asyncio.sleep(0.05)

    # Both clients must have received the message!
    assert ws_on_worker_a.send_text.called, "Local client on worker A should receive message"
    assert (
        ws_on_worker_b.send_text.called
    ), "Remote client on worker B must receive message via Redis pub/sub"

    # Clean up listeners
    await manager_a.stop()
    await manager_b.stop()
