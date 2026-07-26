"""贯通（非 mock）：真实 query_status 产稳定键 DTO → config_view.status_rows 服务端渲染。

堵 mock 盲区：其他 status_rows 测试直接构造 StatusDTO 并喂中文串作输入，会掩盖
「DTO smoothness_label 值域已从中文四档改为稳定键」这一变化（喂什么原样输出，永远绿）。
本测试走真实 QueryService.status，断言 DTO 携带稳定键、且 status_rows 服务端渲染回本地化串。
"""
from pathlib import Path

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.query_service import QueryService
from palworld_terminal.config import (
    AppConfig,
    BasesConfig,
    HistoryConfig,
    PollingConfig,
    PrivacyConfig,
    RoutingConfig,
    WorldConfig,
)
from palworld_terminal.domain.enums import AccessMode
from palworld_terminal.domain.models import World, WorldMetric
from palworld_terminal.infrastructure.cache import TTLCache
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations
from palworld_terminal.presentation.config_view import status_rows

WID = "alpha:guid-1:0"


def _cfg() -> AppConfig:
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.OPEN, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world() -> World:
    return World(WID, "alpha", "guid-1", 0, "alpha", "0.3", 900, 1200, 42)


@pytest.fixture
async def qs(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1200)
    repo = Repository(db, clock)
    await repo.upsert_world(_world())
    q = QueryService(repo, TTLCache(clock), _cfg(), meta=None, clock=clock, settings_cache={})
    yield repo, q
    await db.close()


async def test_real_smoothness_dto_renders_localized_in_status_rows(qs):
    # fps=58 ≥ fps_smooth(50) → 应用层产稳定键 "smooth"
    repo, q = qs
    await repo.insert_metric(WorldMetric(WID, 1200, 58.0, 17.2, 2, 42, 5))
    dto = await q.status(_world())
    assert dto.smoothness_label == "smooth"        # 应用层不产中文，值域为稳定键
    rows = status_rows([("alpha", True, dto)])
    # 设置页 API 契约保持本地化串：status_rows 就地经 L() 服务端渲染回中文（zh 装载下）
    assert rows[0]["smoothness_label"] == "流畅"
