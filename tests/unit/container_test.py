from pathlib import Path

from palchronicle.config import (
    AppConfig, BasesConfig, BindingConfig, HistoryConfig, PollingConfig,
    PrivacyConfig, RoutingConfig, ServerConfig, WorldConfig,
)
from palchronicle.container import Container
from palchronicle.domain.enums import AccessMode
from palchronicle.infrastructure.clock import FakeClock


def _server(name: str) -> ServerConfig:
    return ServerConfig(name, name, True, "http://127.0.0.1:8212", "admin", "pw", 10, True, "")


def _cfg(servers, bindings=None) -> AppConfig:
    return AppConfig(
        servers=servers, skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=bindings or [],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


class _FakeScheduler:
    def __init__(self, *a, **k):
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


class _FakeRest:
    def __init__(self, *a, **k):
        self.closed = False

    async def close(self):
        self.closed = True


async def test_start_builds_services_and_seeds(tmp_path: Path):
    scheds = []

    def sched_factory(*a, **k):
        s = _FakeScheduler()
        scheds.append(s)
        return s

    cfg = _cfg([_server("alpha")], bindings=[BindingConfig("umo1", "alpha", True)])
    c = Container(cfg, tmp_path, FakeClock(1000),
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=sched_factory)
    await c.start()
    try:
        assert c.routing is not None
        assert c.query is not None
        assert c.commands is not None
        assert scheds and scheds[0].started is True
        # seed binding landed
        assert await c.routing._repo.get_binding_active("umo1") == "alpha"
        # salt file created
        assert (tmp_path / "secret_salt").exists()
    finally:
        await c.stop()
    assert scheds[0].stopped is True


async def test_stop_closes_rest_and_db(tmp_path: Path):
    rests = []

    def rest_factory(s, clk):
        r = _FakeRest()
        rests.append(r)
        return r

    c = Container(_cfg([_server("alpha")]), tmp_path, FakeClock(1000),
                  rest_factory=rest_factory, scheduler_factory=lambda *a, **k: _FakeScheduler())
    await c.start()
    await c.stop()
    assert rests and all(r.closed for r in rests)


async def test_on_response_dispatches_info(tmp_path: Path, monkeypatch):
    c = Container(_cfg([_server("alpha")]), tmp_path, FakeClock(1000),
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=lambda *a, **k: _FakeScheduler())
    await c.start()
    from palchronicle.adapters.palworld_rest import RestResponse
    from palchronicle.domain.enums import EndpointName
    calls = []

    async def fake_ingest_info(server, resp):
        calls.append(("info", server.server_id))
        return None

    monkeypatch.setattr(c._snapshot, "ingest_info", fake_ingest_info)
    resp = RestResponse(ok=True, status=200, data={"worldguid": "g"}, duration_ms=1,
                        payload_bytes=1, error=None)
    await c._on_response("alpha", EndpointName.INFO, resp)
    await c.stop()
    assert calls == [("info", "alpha")]
