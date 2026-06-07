from __future__ import annotations

import asyncio
import time
from collections import defaultdict


class RateLimiter:
    """Connection + sliding-window request caps (Nomad gateway pattern)."""

    def __init__(self, max_connections: int, max_requests_per_minute: int) -> None:
        self._max_connections = max_connections
        self._max_rpm = max_requests_per_minute
        self._active_connections = 0
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def try_acquire(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            window_start = now - 60.0
            self._timestamps = [t for t in self._timestamps if t >= window_start]
            if len(self._timestamps) >= self._max_rpm:
                return False
            if self._active_connections >= self._max_connections:
                return False
            self._active_connections += 1
            self._timestamps.append(now)
            return True

    async def release(self) -> None:
        async with self._lock:
            self._active_connections = max(0, self._active_connections - 1)

    def snapshot(self) -> dict[str, int]:
        now = time.monotonic()
        recent = [t for t in self._timestamps if t >= now - 60.0]
        return {
            "active_connections": self._active_connections,
            "requests_last_minute": len(recent),
        }


class DistributedRateLimiter:
    """Per-client IP rate limiting."""

    def __init__(self, max_per_minute: int) -> None:
        self._max = max_per_minute
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def try_acquire(self, client_id: str) -> bool:
        async with self._lock:
            now = time.monotonic()
            window = now - 60.0
            hits = [t for t in self._buckets[client_id] if t >= window]
            if len(hits) >= self._max:
                return False
            hits.append(now)
            self._buckets[client_id] = hits
            return True
