"""查询短时缓存（TTL）。时钟可注入以确定性测过期。"""
from __future__ import annotations

from typing import Any

from palchronicle.infrastructure.clock import Clock


class TTLCache:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._store: dict[str, tuple[int, Any]] = {}  # key -> (expires_at, value)

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock.now() >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store[key] = (self._clock.now() + ttl_seconds, value)
