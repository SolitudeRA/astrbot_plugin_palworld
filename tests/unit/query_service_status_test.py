from pathlib import Path

import pytest

from palworld_terminal.adapters.metadata_repository import MetadataRepository
from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.query_service import QueryService
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
from palworld_terminal.domain.enums import AccessMode, IdConfidence, PingBucket, SessionStatus
from palworld_terminal.domain.models import (
    PlayerIdentity,
    PlayerObservation,
    PlayerSession,
    World,
    WorldMetric,
)
from palworld_terminal.infrastructure.cache import TTLCache
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations

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
    yield repo, q, clock
    await db.close()


async def test_status_assembles_dto(qs):
    repo, q, _ = qs
    await repo.insert_metric(WorldMetric(WID, 1200, 58.0, 17.2, 2, 42, 5))
    # one online player with a recent observation + session
    await repo.upsert_player(PlayerIdentity("pk1", WID, "Neo", 1000, 1200, 21, "g1", IdConfidence.HIGH))
    sid = await repo.insert_session(
        PlayerSession(None, WID, "pk1", 1000, 1200, None, 200, SessionStatus.ACTIVE, None)
    )
    await repo.insert_observation(
        PlayerObservation(1200, WID, "pk1", "Neo", 21, PingBucket.GOOD, 3, "g1", None, None)
    )
    dto = await q.status(_world())
    assert dto.world_day == 42
    assert dto.online == 2
    assert dto.basecamp_count == 5
    assert dto.smoothness_label == "流畅"
    assert dto.degraded is False
    assert ("Neo", 21, "good") in dto.players
    assert sid >= 1


async def test_status_degraded_when_no_metric(qs):
    repo, q, _ = qs
    dto = await q.status(_world())
    assert dto.degraded is True
    assert dto.online == 0


async def test_status_is_cached(qs):
    repo, q, clock = qs
    await repo.insert_metric(WorldMetric(WID, 1200, 58.0, 17.2, 2, 42, 5))
    first = await q.status(_world())
    # mutate DB; cached result should be returned within TTL
    await repo.insert_metric(WorldMetric(WID, 1201, 20.0, 40.0, 9, 42, 5))
    second = await q.status(_world())
    assert second.online == first.online == 2
    # advance beyond TTL 15s -> fresh read
    clock.advance(16)
    third = await q.status(_world())
    assert third.online == 9


async def test_online_dto(qs):
    repo, q, _ = qs
    await repo.upsert_player(PlayerIdentity("pk1", WID, "Neo", 1000, 1200, 21, "g1", IdConfidence.HIGH))
    await repo.insert_session(
        PlayerSession(None, WID, "pk1", 1000, 1200, None, 200, SessionStatus.ACTIVE, None)
    )
    await repo.insert_observation(
        PlayerObservation(1200, WID, "pk1", "Neo", 21, PingBucket.HIGH, 3, "g1", None, None)
    )
    dto = await q.online(_world())
    assert len(dto.rows) == 1
    assert dto.rows[0].name == "Neo"
    assert dto.rows[0].ping_bucket is PingBucket.HIGH
    assert dto.rows[0].online_seconds == 200


_METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"


def _server() -> ServerConfig:
    return ServerConfig(
        server_id="alpha", name="alpha", enabled=True, base_url="http://host:8212",
        username="admin", password="pw", timeout=10, verify_tls=True,
        timezone="Asia/Tokyo",
    )


@pytest.fixture
async def qs_detail(tmp_path: Path):
    db = Database(tmp_path / "d.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1200)
    repo = Repository(db, clock)
    await repo.upsert_world(_world())
    cfg = _cfg()
    cfg.servers = [_server()]
    meta = MetadataRepository(_METADATA_DIR)
    meta.load()
    settings_cache = {"alpha": {
        "Difficulty": "Normal", "bEnablePlayerToPlayerDamage": False,
        "DeathPenalty": "Item", "ExpRate": 1.0,
    }}
    info_cache = {"alpha": {"description": "Palpagos", "uptime": 553234}}
    q = QueryService(
        repo, TTLCache(clock), cfg, meta=meta, clock=clock,
        settings_cache=settings_cache, info_cache=info_cache,
    )
    yield repo, q
    await db.close()


async def test_status_detail_assembled_from_all_sources(qs_detail):
    repo, q = qs_detail
    await repo.insert_metric(WorldMetric(WID, 1200, 58.0, 17.2, 2, 42, 5))
    dto = await q.status(_world())
    d = dto.detail
    assert d is not None
    assert d.version == "0.3"            # 来自 World.version（持久化，info 采集回写）
    assert d.description == "Palpagos"   # info 采集 → info_cache
    assert d.uptime_seconds == 553234    # metrics 采集 → info_cache
    assert d.frametime_ms == 17.2        # StatusDTO.frame_time 同源
    assert d.address == "http://host:8212"  # config base_url
    assert d.rules == {
        "difficulty": "普通", "pvp": "关闭",
        "death_penalty": "掉落物品", "exp_rate": "1.0×",
    }


async def test_status_detail_none_when_degraded(qs_detail):
    repo, q = qs_detail
    # 无 metric → degraded → 不产 detail（白名单只给可信实时数据）
    dto = await q.status(_world())
    assert dto.degraded is True
    assert dto.detail is None


async def test_status_detail_tolerates_missing_settings(qs_detail):
    repo, q = qs_detail
    # 清空 settings 缓存：rules 子键整体省略，其余字段照常，绝不 500
    q._settings_cache.clear()
    await repo.insert_metric(WorldMetric(WID, 1200, 58.0, 17.2, 2, 42, 5))
    dto = await q.status(_world())
    assert dto.detail is not None
    assert dto.detail.rules == {}
    assert dto.detail.version == "0.3"
    assert dto.detail.address == "http://host:8212"


async def test_status_detail_rules_omits_absent_keys(qs_detail):
    repo, q = qs_detail
    # 仅 DeathPenalty 在快照里：其余规则键省略，不塞空串
    q._settings_cache["alpha"] = {"DeathPenalty": "ItemAndEquipment"}
    await repo.insert_metric(WorldMetric(WID, 1200, 58.0, 17.2, 2, 42, 5))
    dto = await q.status(_world())
    assert dto.detail is not None
    assert dto.detail.rules == {"death_penalty": "掉落物品与装备"}


async def test_status_peak_today_uses_local_day_not_rolling_24h(qs):
    # 「今日最高」按 JST 自然日(day_bounds),不再是 now-86400 滚动窗口
    repo, q, _ = qs
    # clock=1200(今日 09:20 JST);JST 今日起点 = epoch -32400
    await repo.insert_metric(WorldMetric(WID, -36000, 50.0, 20.0, 5, 41, 0))  # 昨日 23:00 JST 峰值 5
    await repo.insert_metric(WorldMetric(WID, 1200, 58.0, 17.2, 3, 42, 0))    # 今日在线 3
    dto = await q.status(_world())
    assert dto.peak_online_today == 3  # 修复前滚动窗口会把昨日 5 算进「今日」
