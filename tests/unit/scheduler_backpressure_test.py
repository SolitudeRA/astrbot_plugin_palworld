import asyncio

import pytest

from palworld_terminal.adapters.palworld_rest import RestResponse
from palworld_terminal.config import PollingConfig, ServerConfig
from palworld_terminal.domain.enums import EndpointName
from palworld_terminal.infrastructure.locks import EndpointLocks
from palworld_terminal.infrastructure.scheduler import Scheduler


class ScriptedClock:
    """monotonic 返回预设序列, 制造可控处理耗时。"""

    def __init__(self, monotonic_values):
        self._values = list(monotonic_values)
        self._i = 0

    def now(self):
        return 0

    def monotonic(self):
        v = self._values[min(self._i, len(self._values) - 1)]
        self._i += 1
        return v


def _server():
    return ServerConfig(
        server_id="s1", name="s1", enabled=True, base_url="http://x",
        username="admin", password="pw", timeout=10, verify_tls=True, timezone="",
    )


def _polling(game_data_seconds=120):
    return PollingConfig(30, 30, 600, 1800, game_data_seconds, 0.0, 6)


def _ok():
    return RestResponse(ok=True, status=200, data={}, duration_ms=1, payload_bytes=1, error=None)


def _make_scheduler(clock, sleep, fetcher):
    async def on_response(s, e, r):
        return None

    return Scheduler(
        servers=[_server()], polling=_polling(),
        locks=EndpointLocks(max_concurrency=6), clock=clock,
        on_response=on_response, rng_seed=0, fetcher=fetcher, sleep=sleep,
    )


def test_backpressure_raises_effective_when_processing_slow():
    # 直接单元测内部 _adjust_backpressure(不跑事件循环)
    clock = ScriptedClock([0.0])
    sched = _make_scheduler(clock, sleep=None, fetcher=None)
    key = ("s1", EndpointName.GAME_DATA)
    base = 120.0
    sched._effective[key] = base
    sched._low_streak[key] = 0
    # 处理耗时 200 > effective 120 → 升频(间隔变大)
    sched._adjust_backpressure(key, base, elapsed=200.0)
    assert sched._effective[key] == pytest.approx(240.0)  # base*k, k=2


def test_backpressure_caps_at_base_times_cap():
    clock = ScriptedClock([0.0])
    sched = _make_scheduler(clock, sleep=None, fetcher=None)
    key = ("s1", EndpointName.GAME_DATA)
    base = 120.0
    sched._effective[key] = base * 8  # 已在上限
    sched._low_streak[key] = 0
    sched._adjust_backpressure(key, base, elapsed=9999.0)
    assert sched._effective[key] == pytest.approx(base * 8)  # 封顶 cap=8


def test_backpressure_recovers_after_streak():
    clock = ScriptedClock([0.0])
    sched = _make_scheduler(clock, sleep=None, fetcher=None)
    key = ("s1", EndpointName.GAME_DATA)
    base = 120.0
    sched._effective[key] = base * 4  # 已升频
    sched._low_streak[key] = 0
    # 连续 3 次处理都很快(< effective) → 回落一档
    sched._adjust_backpressure(key, base, elapsed=1.0)
    sched._adjust_backpressure(key, base, elapsed=1.0)
    assert sched._effective[key] == pytest.approx(base * 4)  # 未满 streak
    sched._adjust_backpressure(key, base, elapsed=1.0)
    assert sched._effective[key] == pytest.approx(base * 2)  # /k 回落


def test_backpressure_recover_floors_at_base():
    clock = ScriptedClock([0.0])
    sched = _make_scheduler(clock, sleep=None, fetcher=None)
    key = ("s1", EndpointName.GAME_DATA)
    base = 120.0
    sched._effective[key] = base  # 已在下限
    sched._low_streak[key] = 0
    for _ in range(5):
        sched._adjust_backpressure(key, base, elapsed=1.0)
    assert sched._effective[key] == pytest.approx(base)  # 不低于 base


async def test_tick_merged_when_inflight_locked():
    # 在途锁占用 → _tick 直接返回, 不 fetch
    fetch_count = {"n": 0}

    async def fetcher(s, e):
        fetch_count["n"] += 1
        return _ok()

    async def sleep(_):
        await asyncio.Event().wait()  # 永久挂起

    clock = ScriptedClock([0.0, 0.0])
    sched = _make_scheduler(clock, sleep=sleep, fetcher=fetcher)
    locks = sched._locks
    # 先手动占用 game_data 在途锁
    ctx = locks.inflight("s1", EndpointName.GAME_DATA)
    async with ctx as acquired:
        assert acquired is not None  # 首次占用成功
        key = ("s1", EndpointName.GAME_DATA)
        sched._effective[key] = 120.0
        sched._low_streak[key] = 0
        await sched._tick(_server(), EndpointName.GAME_DATA, key, 120.0)
        assert fetch_count["n"] == 0  # 被合并跳过, 未 fetch
