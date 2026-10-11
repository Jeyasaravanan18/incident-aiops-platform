"""WebSocket connection and Redis Pub/Sub broadcast fan-out manager.

Enables multi-worker cluster fan-out so events published by any worker
are delivered to WebSockets connected to all cluster workers.
"""

import asyncio
import json
from collections import defaultdict
from uuid import uuid4

from fastapi import WebSocket
from redis.asyncio import Redis

from app.core.redis import get_redis_client


class WebSocketManager:
    """Manages local WebSockets and synchronizes multi-worker events via Redis Pub/Sub."""

    def __init__(self, redis_client: Redis | None = None) -> None:
        self.instance_id: str = uuid4().hex[:8]
        self._channels: dict[str, set[WebSocket]] = defaultdict(set)
        self._redis: Redis | None = redis_client
        self._listener_task: asyncio.Task | None = None
        self._running: bool = False

    async def get_redis(self) -> Redis:
        if self._redis is None:
            self._redis = await get_redis_client()
        return self._redis

    async def start(self) -> None:
        """Starts background Redis Pub/Sub subscription listener."""
        if self._running:
            return
        self._running = True
        self._listener_task = asyncio.create_task(self._pubsub_listener())

    async def stop(self) -> None:
        """Stops background listener and cleans up resources."""
        self._running = False
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._channels[channel].add(websocket)
        if not self._running:
            await self.start()

    def disconnect(self, channel: str, websocket: WebSocket) -> None:
        self._channels[channel].discard(websocket)
        if not self._channels[channel]:
            del self._channels[channel]

    async def broadcast(self, channel: str, payload: dict) -> None:
        """Broadcasts an event across all cluster workers via Redis Pub/Sub.

        Falls back to local broadcast if Redis is unreachable.
        """
        envelope = {
            "origin": self.instance_id,
            "channel": channel,
            "payload": payload,
        }
        try:
            redis = await self.get_redis()
            await redis.publish("ws_events", json.dumps(envelope, default=str))
        except Exception:
            # Fallback to local delivery if Redis publish fails
            await self._local_broadcast(channel, payload)

    async def _local_broadcast(self, channel: str, payload: dict) -> None:
        message = json.dumps(payload, default=str)
        stale: list[WebSocket] = []
        for websocket in list(self._channels.get(channel, set())):
            try:
                await websocket.send_text(message)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(channel, websocket)

    async def _pubsub_listener(self) -> None:
        """Background coroutine listening for cross-worker events on Redis channel 'ws_events'."""
        try:
            redis = await self.get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe("ws_events")
            while self._running:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
                if message and message.get("type") == "message":
                    data = message.get("data")
                    if isinstance(data, str | bytes):
                        try:
                            parsed = json.loads(data)
                            channel = parsed.get("channel")
                            payload = parsed.get("payload", {})
                            if channel:
                                await self._local_broadcast(channel, payload)
                        except Exception:
                            pass
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


websocket_manager = WebSocketManager()
