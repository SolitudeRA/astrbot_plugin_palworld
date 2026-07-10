"""每 (server_id, endpoint) 在途锁（占用则跳过）+ 全局并发信号量。"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from palchronicle.domain.enums import EndpointName


class EndpointLocks:
    def __init__(self, max_concurrency: int) -> None:
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self._inflight: set[tuple[str, str]] = set()

    @asynccontextmanager
    async def inflight(
        self, server_id: str, endpoint: EndpointName
    ) -> AsyncIterator[bool]:
        key = (server_id, str(endpoint))
        if key in self._inflight:
            # 已有同端点在途请求 → 本次直接跳过（tick 合并）。
            yield False
            return
        self._inflight.add(key)
        try:
            yield True
        finally:
            self._inflight.discard(key)
