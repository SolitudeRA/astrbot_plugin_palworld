"""OFF 语义端到端：命令 gating、M1 分层、核心收敛不依赖 game-data/events（spec §6/§9）。"""
from pathlib import Path

from palworld_terminal.config import parse_config
from palworld_terminal.container import Container
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.presentation.locale import L


def _cfg(guilds_bases=False, events=True, bases_enabled=True):
    # 经 command_permissions 三态行驱动（容器装配门读 command_overrides；命令层 features
    # 由派生桥复算，两端一致）。空行集 → 全默认（events 开、guilds_bases 关）。
    cmds = []
    if guilds_bases:
        cmds.append({"command": "guild", "enabled": "on"})
    if not events:
        cmds.append({"command": "world events", "enabled": "off"})
    return parse_config({
        "servers": [{"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
                     "username": "admin", "password": "pw"}],
        "routing": {"access_mode": "open", "default_server": ""}, "group_bindings": [],
        "polling": {}, "world": {}, "bases": {"enabled": bases_enabled},
        "privacy": {"mode": "balanced"}, "history": {},
        "command_permissions": cmds,
    }, {})


class _FakeRest:
    async def close(self): ...


class _FakeSched:
    async def start(self): ...
    async def stop(self): ...


async def _container(cfg, tmp_path):
    c = Container(cfg, tmp_path, FakeClock(1000),
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=lambda **k: _FakeSched())
    await c.start()
    return c


async def test_guilds_command_disabled_end_to_end(tmp_path: Path):
    c = await _container(_cfg(guilds_bases=False), tmp_path)
    try:
        out = await c.commands.guilds("umo", "@alpha", True)
        assert out == L("feature_disabled")
    finally:
        await c.stop()


async def test_m1_layering_master_switch_beats_bases_enabled(tmp_path: Path):
    # features.guilds_bases 关 → 无论 bases.enabled 真假，BaseService 不被构造
    c = await _container(_cfg(guilds_bases=False, bases_enabled=True), tmp_path)
    try:
        assert c._snapshot._bases is None
    finally:
        await c.stop()


async def test_help_omits_disabled_groups(tmp_path: Path):
    c = await _container(_cfg(guilds_bases=False, events=False), tmp_path)
    try:
        text = c.commands.help("/pal help", is_admin=False)
        assert "guilds" not in text and "events" not in text
        assert "status" in text and "world" in text
    finally:
        await c.stop()
