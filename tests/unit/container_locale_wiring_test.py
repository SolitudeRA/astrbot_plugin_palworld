"""容器装配：start() 按 cfg.world.locale 装载语言（i18n Phase 1 spec §3.1）。

load_locale 是唯一校验/回落/告警点；容器只负责在构造服务前按配置装载。
非法/未知 locale 的回落由 load_locale 自身兜底（此处只锚"按配置值调用"）。
"""
from pathlib import Path

import palworld_terminal.container as container_mod
from palworld_terminal.config import parse_config
from palworld_terminal.container import Container
from palworld_terminal.infrastructure.clock import FakeClock


def _cfg(locale: str):
    return parse_config({
        "servers": [{"name": "alpha", "enabled": True,
                     "base_url": "http://127.0.0.1:8212",
                     "username": "admin", "password": "pw"}],
        "routing": {"access_mode": "open", "default_server": ""},
        "group_bindings": [], "polling": {}, "world": {"locale": locale},
        "bases": {"enabled": True}, "privacy": {"mode": "balanced"}, "history": {},
    }, {})


class _FakeRest:
    async def close(self): ...


class _FakeSched:
    async def start(self): ...
    async def stop(self): ...


async def test_start_loads_configured_locale(tmp_path: Path, monkeypatch):
    # start() 中 load_locale 按 cfg.world.locale 被调（en 装载）；
    # 用 spy 记录，避免依赖 en.json 存在（Phase 1 T4 前会 fallback zh）。
    calls: list[str] = []
    monkeypatch.setattr(container_mod, "load_locale", lambda loc: calls.append(loc))
    c = Container(_cfg("en"), tmp_path, FakeClock(1000),
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=lambda **kw: _FakeSched())
    await c.start()
    try:
        assert calls == ["en"]
    finally:
        await c.stop()
