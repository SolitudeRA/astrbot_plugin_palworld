"""容器按生效值条件装配：禁用组不构造服务、scheduler 端点随 command_overrides 开关。"""
from pathlib import Path

from palworld_terminal.application.command_permissions import CommandOverride as CO
from palworld_terminal.config import parse_config
from palworld_terminal.container import Container
from palworld_terminal.domain.enums import EndpointName
from palworld_terminal.infrastructure.clock import FakeClock


def _cfg(overrides: dict[str, CO]):
    # 直接注入 command_overrides（不经 features）：证明容器装配门读生效值而非旧 features。
    cfg = parse_config({
        "servers": [{"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
                     "username": "admin", "password": "pw"}],
        "routing": {"access_mode": "open", "default_server": ""}, "group_bindings": [],
        "polling": {}, "world": {}, "bases": {"enabled": True},
        "privacy": {"mode": "balanced"}, "history": {},
    }, {})
    cfg.permissions.command_overrides = dict(overrides)
    return cfg


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


async def test_defaults_exclude_game_data_null_guilds_bases_keep_events(tmp_path: Path):
    # command_overrides={}：events 默认开 → EventService 非 None；
    # guilds_bases 默认关 → game-data 端点排除、GuildService/BaseService 为 None。
    captured = {}
    c = await _build(_cfg({}), tmp_path, captured)
    try:
        assert EndpointName.GAME_DATA not in captured["endpoints"]
        assert {EndpointName.INFO, EndpointName.METRICS,
                EndpointName.PLAYERS, EndpointName.SETTINGS} <= captured["endpoints"]
        assert c._snapshot._guilds is None and c._snapshot._bases is None
        assert c._snapshot._events is not None
    finally:
        await c.stop()


async def test_guild_enable_does_not_wire_game_data_when_unavailable(tmp_path: Path):
    # guilds_bases 上游不可用 force-off（§5A④）：即便显式 guild on，容器装配门读生效值
    # （effective_enabled 恒 False）→ GAME_DATA 不接线、GuildService/BaseService 不装配。
    captured = {}
    c = await _build(_cfg({"guild": CO(enabled=True)}), tmp_path, captured)
    try:
        assert EndpointName.GAME_DATA not in captured["endpoints"]
        assert c._snapshot._guilds is None and c._snapshot._bases is None
    finally:
        await c.stop()


async def test_world_events_disabled_nulls_event_service(tmp_path: Path):
    c = await _build(_cfg({"world events": CO(enabled=False)}), tmp_path, {})
    try:
        assert c._snapshot._events is None
    finally:
        await c.stop()
