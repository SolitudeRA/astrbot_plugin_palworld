"""按期触发采集：每 ready 服务器每端点一个 Task；info 启动即拉；注入 rng/clock/sleep。"""
from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.config import PollingConfig, ServerConfig
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.clock import Clock
from palchronicle.infrastructure.locks import EndpointLocks

OnResponse = Callable[[str, EndpointName, RestResponse], Awaitable[None]]
Fetcher = Callable[[str, EndpointName], Awaitable[RestResponse]]
Sleeper = Callable[[float], Awaitable[None]]

# 背压常量 (spec §6.1)
_BACKOFF_K = 2.0
_BACKOFF_CAP = 8.0          # effective 上限 = base * cap
_RECOVER_STREAK = 3         # 连续低于阈值次数后回落


class Scheduler:
    def __init__(
        self,
        servers: list[ServerConfig],
        polling: PollingConfig,
        locks: EndpointLocks,
        clock: Clock,
        on_response: OnResponse,
        rng_seed: int | None = None,
        *,
        fetcher: Fetcher,
        sleep: Sleeper = asyncio.sleep,
    ) -> None:
        self._servers = servers
        self._polling = polling
        self._locks = locks
        self._clock = clock
        self._on_response = on_response
        self._rng = random.Random(rng_seed)
        self._fetcher = fetcher
        self._sleep = sleep
        self._tasks: list[asyncio.Task] = []
        # 每 (server_id, endpoint) 的背压状态
        self._effective: dict[tuple[str, EndpointName], float] = {}
        self._low_streak: dict[tuple[str, EndpointName], int] = {}

    def _base_interval(self, endpoint: EndpointName) -> float:
        return {
            EndpointName.METRICS: self._polling.metrics_seconds,
            EndpointName.PLAYERS: self._polling.players_seconds,
            EndpointName.INFO: self._polling.info_seconds,
            EndpointName.SETTINGS: self._polling.settings_seconds,
            EndpointName.GAME_DATA: self._polling.game_data_seconds,
        }[endpoint]

    def _jittered(self, base: float) -> float:
        r = self._polling.jitter_ratio
        return base * self._rng.uniform(1 - r, 1 + r)

    async def start(self) -> None:
        for server in self._servers:
            if not server.ready:
                continue
            for endpoint in EndpointName:
                self._tasks.append(
                    asyncio.create_task(self._loop(server, endpoint))
                )

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks = []

    async def _loop(self, server: ServerConfig, endpoint: EndpointName) -> None:
        key = (server.server_id, endpoint)
        base = self._base_interval(endpoint)
        self._effective.setdefault(key, base)
        self._low_streak.setdefault(key, 0)
        immediate = endpoint is EndpointName.INFO
        try:
            while True:
                if not immediate:
                    await self._sleep(self._jittered(self._effective[key]))
                immediate = False
                await self._tick(server, endpoint, key, base)
        except asyncio.CancelledError:
            raise

    async def _tick(
        self,
        server: ServerConfig,
        endpoint: EndpointName,
        key: tuple[str, EndpointName],
        base: float,
    ) -> None:
        ctx = self._locks.inflight(server.server_id, endpoint)
        async with ctx as acquired:
            if not acquired:
                return  # 在途锁占用 → tick 合并跳过
            start = self._clock.monotonic()
            resp = await self._fetcher(server.server_id, endpoint)
            await self._on_response(server.server_id, endpoint, resp)
            self._adjust_backpressure(key, base, self._clock.monotonic() - start)

    def _adjust_backpressure(
        self, key: tuple[str, EndpointName], base: float, elapsed: float
    ) -> None:
        current = self._effective[key]
        if elapsed > current:
            self._effective[key] = min(current * _BACKOFF_K, base * _BACKOFF_CAP)
            self._low_streak[key] = 0
        else:
            self._low_streak[key] += 1
            if self._low_streak[key] >= _RECOVER_STREAK and current > base:
                self._effective[key] = max(current / _BACKOFF_K, base)
                self._low_streak[key] = 0
