"""Container.stop 异常安全：client.close 抛错也必须关闭 DB。"""
from pathlib import Path

from palworld_terminal.config import (
    AppConfig,
    BasesConfig,
    HistoryConfig,
    PollingConfig,
    PrivacyConfig,
    RoutingConfig,
    ServerConfig,
    WorldConfig,
)
from palworld_terminal.container import Container
from palworld_terminal.domain.enums import AccessMode
from palworld_terminal.infrastructure.clock import FakeClock


def _cfg():
    return AppConfig(
        servers=[ServerConfig("a", "a", True, "http://127.0.0.1:8212", "admin",
                              "pw", 10, True, "")],
        skipped=[], routing=RoutingConfig(AccessMode.RESTRICTED, ""),
        group_bindings=[], polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


class _BoomRest:
    async def close(self):
        raise RuntimeError("close failed")


class _FakeSched:
    async def start(self): ...
    async def stop(self): ...


async def test_stop_closes_db_even_if_client_close_raises(tmp_path: Path):
    c = Container(_cfg(), tmp_path, FakeClock(1000),
                  rest_factory=lambda s, clk: _BoomRest(),
                  scheduler_factory=lambda **k: _FakeSched())
    await c.start()
    # client.close 抛错，但 db 仍应被关闭并置空
    try:
        await c.stop()
    except RuntimeError:
        pass
    assert c._db is None
