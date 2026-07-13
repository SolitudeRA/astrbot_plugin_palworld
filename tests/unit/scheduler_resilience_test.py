"""审查修复 A1/A3:单次 tick 异常不杀端点循环;全局并发信号量真实生效。"""
import asyncio

from palworld_terminal.adapters.palworld_rest import RestResponse
from palworld_terminal.config import PollingConfig, ServerConfig
from palworld_terminal.domain.enums import EndpointName
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.locks import EndpointLocks
from palworld_terminal.infrastructure.scheduler import Scheduler


def _server(sid="s1"):
    return ServerConfig(
        server_id=sid, name=sid, enabled=True, base_url="http://x",
        username="admin", password="pw", timeout=10, verify_tls=True, timezone="",
    )


def _polling(max_concurrency=6):
    return PollingConfig(
        metrics_seconds=30, players_seconds=30, info_seconds=600,
        settings_seconds=1800, game_data_seconds=120, jitter_ratio=0.0,
        max_concurrency=max_concurrency,
    )


def _ok_resp():
    return RestResponse(ok=True, status=200, data={}, duration_ms=1,
                        payload_bytes=1, error=None)


class CountedSleep:
    """放行每任务前 N 次间隔 sleep,之后永久挂起(限定轮数,计数确定)。"""

    def __init__(self, rounds: int):
        self._rounds = rounds
        self._seen: dict[object, int] = {}
        self._gate = asyncio.Event()

    async def __call__(self, secs):
        task = asyncio.current_task()
        n = self._seen.get(task, 0) + 1
        self._seen[task] = n
        if n <= self._rounds:
            return
        await self._gate.wait()  # 永不放行


async def test_tick_exception_does_not_kill_endpoint_loop():
    fetched = []

    async def fetcher(server_id, endpoint):
        fetched.append(endpoint)
        if len(fetched) == 1:
            raise ValueError("boom")  # 首轮采集崩溃
        return _ok_resp()

    async def on_response(server_id, endpoint, resp):
        pass

    sched = Scheduler(
        [_server()], _polling(), EndpointLocks(6), FakeClock(start=0),
        on_response, rng_seed=1, fetcher=fetcher, sleep=CountedSleep(2),
        endpoints=frozenset({EndpointName.METRICS}),
    )
    await sched.start()
    for _ in range(20):
        await asyncio.sleep(0)
    await sched.stop()
    # 首轮抛异常后循环仍继续,第二轮 fetch 发生
    assert len(fetched) >= 2


async def test_global_semaphore_caps_concurrent_fetches():
    # 事件同步制造确定性并发窗口,不依赖真实时间(CI 慢机不 flaky):
    # 首个 fetcher 进入后挂在 release 上;若信号量失效,第二个 task 也会
    # 进入 fetcher(peak=2);生效则第二个挂在 semaphore acquire 上。
    cur = 0
    peak = 0
    entered = asyncio.Event()
    release = asyncio.Event()

    async def fetcher(server_id, endpoint):
        nonlocal cur, peak
        cur += 1
        peak = max(peak, cur)
        entered.set()
        await release.wait()
        cur -= 1
        return _ok_resp()

    async def on_response(server_id, endpoint, resp):
        pass

    # 两台服务器同一端点并发首轮;max_concurrency=1 应串行化
    sched = Scheduler(
        [_server("s1"), _server("s2")], _polling(max_concurrency=1),
        EndpointLocks(1), FakeClock(start=0),
        on_response, rng_seed=1, fetcher=fetcher, sleep=CountedSleep(1),
        endpoints=frozenset({EndpointName.METRICS}),
    )
    await sched.start()
    await asyncio.wait_for(entered.wait(), timeout=5)
    for _ in range(50):  # 纯让出调度,给第二个 task 充分机会去抢信号量
        await asyncio.sleep(0)
    assert peak == 1, f"全局并发上限失效,峰值 {peak}"
    release.set()
    await sched.stop()
