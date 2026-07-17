"""link 单模式守卫（唯一防线，先于 routing.use = DB 写）+ 启动告警暴露（spec §5/§7）。

- 单世界模式 /pal link add alpha → 回「单世界模式无需选择服务器」提示，且**先于**
  routing.use（守卫是唯一防线，help 省略只是视觉）。
- initialize（容器装配后）经 logger 暴露两条启动告警：single+restricted 授权名单为空告警
  + admin_only_commands 未知锁告警（T5 unknown_locks）。
"""
from __future__ import annotations

import logging
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _raw(*, world_mode="multi", access="restricted", admin_only=None) -> dict:
    raw = {
        "servers": [
            {"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
             "username": "admin", "password": "pw", "timeout": 10, "verify_tls": True,
             "timezone": ""},
        ],
        "group_bindings": [],
        "routing": {"access_mode": access, "default_server": "", "world_mode": world_mode,
                    "setup_confirmed": True},  # 已确认安装：否则默认未确认会被首次设置闸短路
        "polling": {"metrics_seconds": 30, "players_seconds": 30, "info_seconds": 600,
                    "settings_seconds": 1800, "game_data_seconds": 120, "jitter_ratio": 0.1,
                    "max_concurrency": 6},
        "world": {"timezone": "Asia/Tokyo", "locale": "zh-CN", "fps_smooth": 50,
                  "fps_moderate": 35, "fps_laggy": 20},
        "bases": {"enabled": True, "assignment_radius": 5000, "ambiguity_ratio": 0.2,
                  "confirmation_samples": 3, "position_grid_size": 2000, "z_weight": 0.5},
        "privacy": {"mode": "balanced", "public_exact_ping": False, "public_positions": False,
                    "ping_good_ms": 60, "ping_ok_ms": 120, "uncertain_timeout": 900},
        "history": {"raw_metrics_days": 7, "aggregate_days": 90, "session_days": 365,
                    "observation_days": 180},
    }
    if admin_only is not None:
        raw["admin_only_commands"] = admin_only
    return raw


class _FakeContext:
    pass


class _FakeEvent:
    def __init__(self, msg: str, *, sender="123", platform="qq", private=False):
        self.message_str = msg
        self.unified_msg_origin = "umo1"
        self._sender = sender
        self._platform = platform
        self._private = private

    def plain_result(self, text):
        return text

    def get_sender_id(self):
        return self._sender

    def get_platform_name(self):
        return self._platform

    def is_private_chat(self):
        return self._private


async def _make_plugin(tmp_path, monkeypatch, raw):
    import main as main_mod
    from palworld_terminal.container import Container

    class _FakeRest:
        async def close(self):
            pass

    class _FakeSched:
        async def start(self):
            pass

        async def stop(self):
            pass

    orig_init = Container.__init__

    def patched_init(self, config, data_dir, clock, **kw):
        kw.setdefault("rest_factory", lambda s, c: _FakeRest())
        kw.setdefault("scheduler_factory", lambda **k: _FakeSched())
        orig_init(self, config, data_dir, clock, **kw)

    monkeypatch.setattr(Container, "__init__", patched_init)
    monkeypatch.setattr(main_mod, "_resolve_data_dir", lambda: tmp_path)
    plugin = main_mod.PalWorldTerminal(_FakeContext(), raw)
    await plugin.initialize()
    return plugin


async def _drive_link(plugin, event):
    outs = [r async for r in plugin.link(event)]
    return outs[0]


# ---- link 单模式守卫 ----

async def test_single_mode_link_guard_blocks_before_routing_use(tmp_path: Path, monkeypatch):
    plugin = await _make_plugin(tmp_path, monkeypatch, _raw(world_mode="single"))
    used: list = []

    async def spy_use(umo, name):
        used.append((umo, name))
        return "SHOULD_NOT_RUN"

    monkeypatch.setattr(plugin._container.routing, "use", spy_use)
    try:
        out = await _drive_link(plugin, _FakeEvent("/pal link add alpha"))
        assert "单世界模式" in out
        assert used == []  # 守卫先于 routing.use（DB 写）——绝不触达
    finally:
        await plugin.terminate()


async def test_multi_mode_link_not_guarded(tmp_path: Path, monkeypatch):
    # 多模式不被单模式守卫拦：进入 Commands.link 分发（非管理员 → admin 门回 admin_required）。
    plugin = await _make_plugin(tmp_path, monkeypatch, _raw(world_mode="multi", access="open"))
    try:
        out = await _drive_link(plugin, _FakeEvent("/pal link add alpha"))
        assert out == "⚠️ 该命令需要管理员权限"  # 走到 Commands.link 的 admin 门 = 未被守卫短路
    finally:
        await plugin.terminate()


# ---- 启动告警暴露（initialize 经 logger）----

async def test_startup_warns_single_restricted_empty_allowlist(tmp_path: Path, monkeypatch, caplog):
    # 单模式 + restricted + 授权名单为空 → 运维告警（所有会话都无法查询）。
    with caplog.at_level(logging.WARNING, logger="palworld_terminal.main"):
        plugin = await _make_plugin(
            tmp_path, monkeypatch, _raw(world_mode="single", access="restricted"))
    try:
        msgs = [r.getMessage() for r in caplog.records if r.name == "palworld_terminal.main"]
        assert any("授权群名单为空" in m for m in msgs), msgs
    finally:
        await plugin.terminate()


async def test_startup_no_single_restricted_warning_in_multi(tmp_path: Path, monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="palworld_terminal.main"):
        plugin = await _make_plugin(
            tmp_path, monkeypatch, _raw(world_mode="multi", access="restricted"))
    try:
        msgs = [r.getMessage() for r in caplog.records if r.name == "palworld_terminal.main"]
        assert not any("架空" in m for m in msgs), msgs
    finally:
        await plugin.terminate()


async def test_startup_warns_unknown_locks(tmp_path: Path, monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="palworld_terminal.main"):
        plugin = await _make_plugin(
            tmp_path, monkeypatch, _raw(admin_only=["totally_not_a_command"]))
    try:
        msgs = [r.getMessage() for r in caplog.records if r.name == "palworld_terminal.main"]
        assert any("锁未生效" in m for m in msgs), msgs
        assert any("totally_not_a_command" in m for m in msgs), msgs
    finally:
        await plugin.terminate()
