import asyncio

from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.config import PollingConfig, ServerConfig
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.locks import EndpointLocks
from palchronicle.infrastructure.scheduler import Scheduler


def _server(sid="s1"):
    return ServerConfig(
        server_id=sid, name=sid, enabled=True, base_url="http://x",
        username="admin", password="pw", timeout=10, verify_tls=True, timezone="",
    )


def _polling():
    return PollingConfig(
        metrics_seconds=30, players_seconds=30, info_seconds=600,
        settings_seconds=1800, game_data_seconds=120, jitter_ratio=0.0,
        max_concurrency=6,
    )


def _ok_resp():
    return RestResponse(ok=True, status=200, data={}, duration_ms=1,
                        payload_bytes=1, error=None)


class GatedSleep:
    """每端点循环的首个 sleep 立即返回(触发一轮 fetch)，其后永久挂起，便于计数确定。"""

    # fixture 体已修正为与 docstring 一致：按任务(端点循环)放行首次 sleep。
    def __init__(self):
        self.calls = []
        self._seen = set()
        self._gate = asyncio.Event()

    async def __call__(self, secs):
        self.calls.append(secs)
        task = asyncio.current_task()
        if task not in self._seen:
            self._seen.add(task)
            return
        await self._gate.wait()  # 永不放行 → 每端点只跑一轮


async def test_scheduler_fires_each_endpoint_once_and_info_immediate():
    fetched = []

    async def fetcher(server_id, endpoint):
        fetched.append((server_id, endpoint))
        return _ok_resp()

    responses = []

    async def on_response(server_id, endpoint, resp):
        responses.append((server_id, endpoint, resp.ok))

    sleep = GatedSleep()
    sched = Scheduler(
        servers=[_server()], polling=_polling(),
        locks=EndpointLocks(max_concurrency=6), clock=FakeClock(start=0),
        on_response=on_response, rng_seed=42, fetcher=fetcher, sleep=sleep,
    )
    await sched.start()
    await asyncio.sleep(0)  # 让任务跑到首轮
    await asyncio.sleep(0)
    await sched.stop()

    endpoints_fetched = {ep for _, ep in fetched}
    assert endpoints_fetched == {
        EndpointName.INFO, EndpointName.METRICS, EndpointName.PLAYERS,
        EndpointName.SETTINGS, EndpointName.GAME_DATA,
    }
    # 每端点至少触发一次 on_response
    assert {ep for _, ep, _ in responses} == endpoints_fetched
    # info 端点在首轮无需等待即触发(其循环不在 fetch 前先 sleep)
    assert (_server().server_id, EndpointName.INFO) in fetched


async def test_scheduler_skips_not_ready_servers():
    fetched = []

    async def fetcher(server_id, endpoint):
        fetched.append(server_id)
        return _ok_resp()

    async def on_response(server_id, endpoint, resp):
        return None

    not_ready = ServerConfig(
        server_id="s2", name="s2", enabled=True, base_url="http://y",
        username="admin", password="", timeout=10, verify_tls=True, timezone="",
    )  # password 空 → ready False
    sleep = GatedSleep()
    sched = Scheduler(
        servers=[not_ready], polling=_polling(),
        locks=EndpointLocks(max_concurrency=6), clock=FakeClock(start=0),
        on_response=on_response, rng_seed=1, fetcher=fetcher, sleep=sleep,
    )
    await sched.start()
    await asyncio.sleep(0)
    await sched.stop()
    assert fetched == []  # 未就绪服务器不采集


async def test_scheduler_stop_cancels_all_tasks():
    async def fetcher(server_id, endpoint):
        return _ok_resp()

    async def on_response(server_id, endpoint, resp):
        return None

    sleep = GatedSleep()
    sched = Scheduler(
        servers=[_server()], polling=_polling(),
        locks=EndpointLocks(max_concurrency=6), clock=FakeClock(start=0),
        on_response=on_response, rng_seed=7, fetcher=fetcher, sleep=sleep,
    )
    await sched.start()
    await asyncio.sleep(0)
    await sched.stop()
    assert all(t.done() for t in sched._tasks)
