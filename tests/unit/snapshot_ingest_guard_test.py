"""审查修复 A2:API 返回非 Mapping(数组/标量)时 ingest 走降级路径,不抛异常。

背景:官方 API 异常时可能返回 JSON 数组/字符串等非对象体;修复前
normalize_*/dict() 直接抛 TypeError/AttributeError,经采集循环
(修复 A1 前)永久杀死该端点任务。
"""
import pytest

from palworld_terminal.adapters import normalizer as normalizer_mod
from palworld_terminal.adapters import privacy_filter as privacy_mod
from palworld_terminal.adapters.palworld_rest import RestResponse
from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.snapshot_service import SnapshotService
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
from palworld_terminal.domain.models import World
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


class _Noop:
    async def apply(self, *a, **k):
        return []

    async def mark_uncertain(self, *a, **k):
        return None


def _cfg():
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world():
    return World(
        world_id="s1:GUID-A:0", server_id="s1", worldguid="GUID-A", epoch=0,
        server_name="S", version="0.3", first_seen_at=1, last_seen_at=1,
        current_day=0,
    )


@pytest.fixture
async def svc(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=3000)
    service = SnapshotService(
        repo=Repository(db, clock), normalizer_mod=normalizer_mod,
        privacy_mod=privacy_mod, meta=None, salt=b"\x00" * 32, cfg=_cfg(),
        clock=clock, players=_Noop(), guilds=_Noop(), bases=_Noop(), events=_Noop(),
    )
    yield service
    await db.close()


def _resp(data):
    return RestResponse(ok=True, status=200, data=data,
                        duration_ms=1, payload_bytes=1, error=None)


@pytest.mark.parametrize("bad", [[], ["x"], "oops", 42, True])
async def test_ingest_survives_non_mapping_payload(svc, bad):
    world = _world()
    # 五个 ingest 全部走降级路径,不抛异常
    await svc.ingest_info(world.server_id, _resp(bad))
    await svc.ingest_metrics(world, _resp(bad))
    await svc.ingest_settings(world, _resp(bad))
    await svc.ingest_players(world, _resp(bad))
    await svc.ingest_game_data(world, _resp(bad))


async def test_ingest_settings_non_mapping_keeps_old_cache(svc):
    world = _world()
    await svc.ingest_settings(world, _resp({"ExpRate": 2.0}))
    await svc.ingest_settings(world, _resp(["broken"]))
    cached = svc.get_settings(world.world_id)
    assert cached is not None
    assert cached["data"]["ExpRate"] == 2.0  # 旧缓存不被畸形体破坏
