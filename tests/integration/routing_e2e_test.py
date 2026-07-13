from pathlib import Path

from palworld_terminal.config import (
    AppConfig,
    BasesConfig,
    FeaturesConfig,
    HistoryConfig,
    PollingConfig,
    PrivacyConfig,
    RoutingConfig,
    ServerConfig,
    WorldConfig,
)
from palworld_terminal.container import Container
from palworld_terminal.domain.enums import AccessMode
from palworld_terminal.domain.models import World, WorldMetric
from palworld_terminal.infrastructure.clock import FakeClock

UMO = "aiocqhttp:GroupMessage:123"


def _server() -> ServerConfig:
    return ServerConfig("alpha", "alpha", True, "http://127.0.0.1:8212", "admin", "pw", 10, True, "")


def _cfg() -> AppConfig:
    return AppConfig(
        servers=[_server()], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
        # 显式钉住:本测试只跑非 gated 命令,features 默认收紧不应改变其行为
        features=FeaturesConfig(report=True, events=True, guilds_bases=False),
    )


class _FakeRest:
    async def close(self):
        pass


class _FakeSched:
    async def start(self):
        pass

    async def stop(self):
        pass


async def test_restricted_denies_then_use_allows(tmp_path: Path):
    clock = FakeClock(1700000000)
    c = Container(_cfg(), tmp_path, clock,
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=lambda **k: _FakeSched())
    await c.start()
    try:
        repo = c.routing._repo
        wid = "alpha:guid-1:0"
        await repo.upsert_world(World(wid, "alpha", "guid-1", 0, "alpha", "0.3", 1, clock.now(), 42))
        await repo.insert_metric(WorldMetric(wid, clock.now(), 58.0, 17.0, 2, 42, 5))

        # 1) unauthorized group is denied
        denied = await c.commands.status(UMO, "/pal status", is_group=True)
        assert "未被授权" in denied or "未指定服务器" in denied

        # 2) admin authorizes via /pal server add
        use_msg = await c.commands.server(UMO, "/pal server add alpha", is_group=True, is_admin=True)
        assert "alpha" in use_msg

        # 3) now the same group can query status
        ok = await c.commands.status(UMO, "/pal status", is_group=True)
        assert "第 42 天" in ok
        assert "据点：5" in ok
    finally:
        await c.stop()
