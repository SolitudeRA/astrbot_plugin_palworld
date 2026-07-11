"""容器按 features 条件装配：禁用组不构造服务、scheduler 端点排除 game-data。"""
from pathlib import Path

from palchronicle.config import parse_config
from palchronicle.container import Container
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.clock import FakeClock


def _cfg(guilds_bases: bool, events: bool = True):
    return parse_config({
        "servers": [{"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
                     "username": "admin", "password": "pw"}],
        "routing": {"access_mode": "open", "default_server": ""}, "group_bindings": [],
        "polling": {}, "world": {}, "bases": {"enabled": True},
        "privacy": {"mode": "balanced"}, "history": {},
        "features": {"report": True, "events": events, "guilds_bases": guilds_bases},
    }, {})


class _FakeRest:
    async def close(self): ...


class _FakeSched:
    def __init__(self): self.started = False
    async def start(self): self.started = True
    async def stop(self): ...


async def _build(cfg, tmp_path, captured):
    def sched_factory(**kw):
        captured["endpoints"] = kw.get("endpoints")
        return _FakeSched()
    c = Container(cfg, tmp_path, FakeClock(1000),
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=sched_factory)
    await c.start()
    return c


async def test_guilds_bases_off_excludes_game_data_and_nulls_services(tmp_path: Path):
    captured = {}
    c = await _build(_cfg(guilds_bases=False), tmp_path, captured)
    try:
        assert EndpointName.GAME_DATA not in captured["endpoints"]
        assert {EndpointName.INFO, EndpointName.METRICS,
                EndpointName.PLAYERS, EndpointName.SETTINGS} <= captured["endpoints"]
        assert c._snapshot._guilds is None and c._snapshot._bases is None
    finally:
        await c.stop()


async def test_guilds_bases_on_wires_game_data(tmp_path: Path):
    captured = {}
    c = await _build(_cfg(guilds_bases=True), tmp_path, captured)
    try:
        assert EndpointName.GAME_DATA in captured["endpoints"]
        assert c._snapshot._guilds is not None and c._snapshot._bases is not None
    finally:
        await c.stop()


async def test_events_off_nulls_event_service(tmp_path: Path):
    c = await _build(_cfg(guilds_bases=False, events=False), tmp_path, {})
    try:
        assert c._snapshot._events is None
    finally:
        await c.stop()
