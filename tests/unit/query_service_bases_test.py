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
from palworld_terminal.domain.enums import AccessMode, Confidence, EventType, IdConfidence
from palworld_terminal.domain.models import (
    Base,
    BaseObservation,
    Guild,
    PlayerIdentity,
    World,
    WorldEvent,
)
from palworld_terminal.infrastructure.cache import TTLCache
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations
from palworld_terminal.presentation.event_wording import render_event

WID = "alpha:guid-1:0"


def _cfg(privacy_mode: str = "balanced") -> AppConfig:
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.OPEN, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig(privacy_mode, False, False, 60, 120, 900),
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


async def test_guilds_dto(qs):
    # §5#15：每公会据点数=list_bases 按 guild_key 分组；palbox/active_7d 砍位。
    repo, q, _ = qs
    await repo.upsert_guild(Guild("g1", WID, "Noema", 900, 1200, 4, 2, 10))
    await repo.upsert_base(Base("b1", WID, "pb1", "N-1", "g1", Confidence.HIGH, False, False, 900, 1200))
    await repo.upsert_base(Base("b2", WID, "pb2", "N-2", "g1", Confidence.MEDIUM, False, False, 900, 1200))
    dtos = await q.guilds(_world())
    assert dtos[0].name == "Noema"
    assert dtos[0].observed_members == 4
    assert dtos[0].base_pals == 10
    assert dtos[0].base_count == 2


async def test_guild_detail_found(qs):
    # §5#15：据点列表按 guild_key 过滤（含 low 序号空间）；base_count；恒 0 占位字段砍位。
    repo, q, _ = qs
    await repo.upsert_guild(Guild("g1", WID, "Noema", 900, 1200, 4, 2, 10))
    await repo.upsert_base(Base("b1", WID, "pb1", "海岸木材场", "g1", Confidence.HIGH, False, False, 900, 1200))
    dto = await q.guild(_world(), "Noema")
    assert dto is not None
    assert dto.name == "Noema"
    assert dto.first_seen_at == 900
    assert dto.last_seen_at == 1200
    assert dto.observed_members == 4
    assert dto.base_pals == 10
    assert dto.base_count == 1
    assert dto.bases == [("海岸木材场", Confidence.HIGH)]
    assert dto.recent_events == []


async def test_guild_recent_events_filled(qs):
    # §4.7 / §5#15：近期动态实填=list_events 过滤该公会据点的 NEW_BASE/WORKER_DELTA/BASE_VANISHED
    # （经 event_view 构造 EventView，措辞下沉 render_event；他公会据点事件排除）。
    repo, q, _ = qs
    await repo.upsert_guild(Guild("g1", WID, "Matrix", 900, 1200, 4, 2, 28))
    await repo.upsert_base(Base("b1", WID, "pb1", "海岸木材场", "g1", Confidence.HIGH, False, False, 900, 1200))
    await repo.upsert_base(Base("b2", WID, "pb2", "别家据点", "g2", Confidence.HIGH, False, False, 900, 1200))
    await repo.insert_event(WorldEvent(None, WID, EventType.NEW_BASE, "base", "b1", 1200, 1200, {}, "public", Confidence.HIGH, f"{WID}|NEW_BASE|b1"))
    await repo.insert_event(WorldEvent(None, WID, EventType.WORKER_DELTA, "base", "b1", 1100, 1100, {"prev": 12, "cur": 18}, "public", Confidence.HIGH, f"{WID}|WORKER_DELTA|b1"))
    await repo.insert_event(WorldEvent(None, WID, EventType.NEW_BASE, "base", "b2", 1150, 1150, {}, "public", Confidence.HIGH, f"{WID}|NEW_BASE|b2"))
    dto = await q.guild(_world(), "Matrix")
    assert [render_event(e) for e in dto.recent_events] == [
        "新据点「海岸木材场」确认",
        "据点「海岸木材场」工作帕鲁 12→18",
    ]


async def test_guild_detail_not_found(qs):
    repo, q, _ = qs
    await repo.upsert_guild(Guild("g1", WID, "Noema", 900, 1200, 4, 2, 10))
    assert await q.guild(_world(), "Ghost") is None


async def test_bases_have_stable_index(qs):
    repo, q, _ = qs
    await repo.upsert_base(Base("b1", WID, "pb1", "Noema-1", "g1", Confidence.HIGH, False, False, 900, 1200))
    await repo.upsert_base(Base("b2", WID, "pb2", "Noema-2", "g1", Confidence.MEDIUM, False, False, 900, 1200))
    dtos = await q.bases(_world())
    assert [d.index for d in dtos] == [1, 2]


async def test_bases_worker_count_filled(qs):
    # §5#15：guild bases worker_count 实填=latest_base_observation 每据点索引查询（现恒 0）。
    repo, q, _ = qs
    await repo.upsert_base(Base("b1", WID, "pb1", "N-1", "g1", Confidence.HIGH, False, False, 900, 1200))
    await repo.insert_base_observation(BaseObservation("b1", WID, 1200, 18, 12, 17.5, 0.9, {"working": 18}))
    dtos = await q.bases(_world())
    assert dtos[0].worker_count == 18


async def test_base_by_index(qs):
    repo, q, _ = qs
    await repo.upsert_base(Base("b1", WID, "pb1", "Noema-1", "g1", Confidence.HIGH, False, False, 900, 1200))
    await repo.insert_base_observation(
        BaseObservation("b1", WID, 1200, 8, 6, 17.5, 0.9, {"working": 6, "idle": 2})
    )
    dto = await q.base(_world(), "#1")
    assert dto is not None
    assert dto.display_name == "Noema-1"
    assert dto.worker_count == 8
    assert dto.available is True
    # health_score = 100*(0.8*0.9 + 0.2*1.0) = 92.0
    assert abs(dto.health_score - 92.0) < 0.01


async def test_base_no_observation_available_false(qs):
    # §6#8：据点存在但无观测 → available=False（formatter 走 ⚠️，不再全 0 假数据）。
    repo, q, _ = qs
    await repo.upsert_base(Base("b1", WID, "pb1", "N-1", "g1", Confidence.HIGH, False, False, 900, 1200))
    dto = await q.base(_world(), "#1")
    assert dto is not None
    assert dto.available is False
    assert dto.worker_count == 0


async def test_base_by_name(qs):
    repo, q, _ = qs
    await repo.upsert_base(Base("b1", WID, "pb1", "Noema-2", "g1", Confidence.HIGH, False, False, 900, 1200))
    dto = await q.base(_world(), "Noema-2")
    assert dto is not None
    assert dto.display_name == "Noema-2"


async def test_base_missing_returns_none(qs):
    repo, q, _ = qs
    assert await q.base(_world(), "#9") is None
    assert await q.base(_world(), "Ghost") is None


async def test_bases_include_low_in_number_space(qs):
    # spec §3/§4.8：guild bases 列表含 low 置信度行，序号空间统一（include_low=True）
    repo, q, _ = qs
    await repo.upsert_base(Base("b1", WID, "pb1", None, "g1", Confidence.HIGH, False, False, 900, 1200))
    await repo.upsert_base(Base("bLow", WID, "pb2", None, "g1", Confidence.LOW, False, False, 900, 1200))
    dtos = await q.bases(_world())
    assert [(d.index, d.display_name, d.confidence) for d in dtos] == [
        (1, "BASE-1", Confidence.HIGH),
        (2, "BASE-2", Confidence.LOW),
    ]
    # #序号查找命中 low 行（与列表同源）
    low = await q.base(_world(), "#2")
    assert low is not None and low.confidence == Confidence.LOW


async def test_base_index_consistent_across_events_bases_lookup(qs):
    # 同一 base_key 的 #序号在 events 解析 / bases 列表 / base #查找 三处必须一致
    repo, q, _ = qs
    await repo.upsert_base(Base("b1", WID, "pb1", None, "g1", Confidence.HIGH, False, False, 900, 1200))
    await repo.upsert_base(Base("bLow", WID, "pb2", None, "g1", Confidence.LOW, False, False, 900, 1200))
    dtos = await q.bases(_world())
    ev = WorldEvent(None, WID, EventType.WORKER_DELTA, "base", "bLow", 1200, 1200,
                    {"prev": 12, "cur": 18}, "public", Confidence.HIGH, "d")
    names = await q.resolve_event_subjects(_world(), [ev])
    # 事件解析名 == bases() 列表位次 2 的显示名
    assert names["bLow"] == next(d.display_name for d in dtos if d.index == 2)
    assert names["bLow"] == "BASE-2"
    # 同一 #序号 命中同一据点
    assert (await q.base(_world(), "#2")).confidence == Confidence.LOW


async def test_resolve_event_subjects_skips_hidden_player(qs):
    repo, q, _ = qs
    await repo.upsert_player(PlayerIdentity("pk1", WID, "Neo", 900, 1200, 21, None, IdConfidence.HIGH))
    await repo.set_hidden(WID, "pk1", "phash")
    ev = WorldEvent(None, WID, EventType.NEW_PLAYER, "player", "pk1", 1200, 1200,
                    {}, "public", Confidence.HIGH, "d")
    names = await q.resolve_event_subjects(_world(), [ev])
    assert "pk1" not in names


async def test_hidden_base_event_falls_back(qs):
    repo, q, _ = qs
    await repo.upsert_base(Base("bHid", WID, "pbH", "秘密", "g1", Confidence.HIGH, False, True, 900, 1200))
    ev = WorldEvent(None, WID, EventType.NEW_BASE, "base", "bHid", 1200, 1200,
                    {}, "public", Confidence.HIGH, "d")
    names = await q.resolve_event_subjects(_world(), [ev])
    assert names["bHid"] == "据点"


async def test_events_today_only_filters(qs):
    repo, q, clock = qs
    old = clock.now() - 100000
    # 玩家事件须有身份方可解析名字（否则查无身份即跳过，spec §4.4 / T5 契约）
    await repo.upsert_player(PlayerIdentity("p1", WID, "P-One", 800, old, 5, None, IdConfidence.HIGH))
    await repo.upsert_player(PlayerIdentity("p2", WID, "P-Two", 800, 1200, 5, None, IdConfidence.HIGH))
    await repo.insert_event(WorldEvent(None, WID, EventType.NEW_PLAYER, "player", "p1", old, old, {}, "public", Confidence.HIGH, f"{WID}|NEW_PLAYER|p1"))
    await repo.insert_event(WorldEvent(None, WID, EventType.NEW_PLAYER, "player", "p2", 1200, 1200, {}, "public", Confidence.HIGH, f"{WID}|NEW_PLAYER|p2"))
    all_events = await q.events(_world(), today_only=False)
    assert len(all_events) == 2
    today = await q.events(_world(), today_only=True)
    assert len(today) == 1
    assert today[0].event_type is EventType.NEW_PLAYER
    assert render_event(today[0]) == "新玩家 P-Two 加入世界"  # 措辞经 render_event 唯一渲染源


async def test_events_render_wording_via_single_source(qs):
    # events() 消费 name_resolver + event_view：subject_key 解析为显示名，EventView 经
    # render_event 渲染照八类表。
    repo, q, _ = qs
    await repo.upsert_player(PlayerIdentity("pk1", WID, "Neo", 900, 1200, 22, None, IdConfidence.HIGH))
    await repo.insert_event(WorldEvent(
        None, WID, EventType.PLAYER_LEVEL_UP, "player", "pk1", 1200, 1200,
        {"old": 21, "new": 22}, "public", Confidence.HIGH, f"{WID}|PLAYER_LEVEL_UP|pk1|22",
    ))
    dtos = await q.events(_world(), today_only=False)
    assert len(dtos) == 1
    assert render_event(dtos[0]) == "Neo 升级 Lv21→Lv22"


async def test_events_skips_hidden_player_event(qs):
    # 隐藏玩家的事件在 query 层整条跳过（resolver 缺席即跳，spec §4.4）。
    repo, q, _ = qs
    await repo.upsert_player(PlayerIdentity("pk1", WID, "Neo", 900, 1200, 21, None, IdConfidence.HIGH))
    await repo.set_hidden(WID, "pk1", "phash")
    await repo.insert_event(WorldEvent(
        None, WID, EventType.NEW_PLAYER, "player", "pk1", 1200, 1200,
        {}, "public", Confidence.HIGH, f"{WID}|NEW_PLAYER|pk1",
    ))
    dtos = await q.events(_world(), today_only=False)
    assert dtos == []


async def test_events_strict_keeps_only_world_subject(qs):
    # Finding 2（隐私泄漏）：strict 下 events 只保留 world 主体（里程碑/在线纪录，聚合无归因）；
    # player（升级·时刻）与 base（据点，§4.7-4.9 不可绕出 strict）主体整条缺席。
    repo, q, clock = qs
    await repo.upsert_player(PlayerIdentity("pk1", WID, "Neo", 900, 1200, 22, None, IdConfidence.HIGH))
    await repo.upsert_base(Base("b1", WID, "pb1", "海岸木材场", "g1", Confidence.HIGH, False, False, 900, 1200))
    await repo.insert_event(WorldEvent(None, WID, EventType.WORLD_DAY_MILESTONE, "world", WID, 1200, 1200, {"milestone": 100}, "public", Confidence.HIGH, f"{WID}|WORLD_DAY_MILESTONE|100"))
    await repo.insert_event(WorldEvent(None, WID, EventType.ONLINE_RECORD, "world", WID, 1200, 1200, {"value": 8}, "public", Confidence.HIGH, f"{WID}|ONLINE_RECORD|8"))
    await repo.insert_event(WorldEvent(None, WID, EventType.PLAYER_LEVEL_UP, "player", "pk1", 1200, 1200, {"old": 21, "new": 22}, "public", Confidence.HIGH, f"{WID}|PLAYER_LEVEL_UP|pk1|22"))
    await repo.insert_event(WorldEvent(None, WID, EventType.NEW_BASE, "base", "b1", 1200, 1200, {}, "public", Confidence.HIGH, f"{WID}|NEW_BASE|b1"))

    # balanced（fixture q）：四条主体全在。
    balanced = await q.events(_world(), today_only=False)
    assert len(balanced) == 4

    # strict：仅 world 主体两条，无个体作息/时刻/据点线（独立 cache，与 balanced 不串）。
    q_strict = QueryService(
        repo, TTLCache(clock), _cfg(privacy_mode="strict"), meta=None,
        clock=clock, settings_cache={},
    )
    strict = await q_strict.events(_world(), today_only=False)
    summaries = [render_event(d) for d in strict]
    assert len(strict) == 2
    assert "世界迎来第 100 天" in summaries
    assert "在线人数新纪录 8 人" in summaries
    assert all("Neo" not in s and "升级" not in s for s in summaries)        # player 缺席
    assert all("海岸木材场" not in s and "新据点" not in s for s in summaries)  # base 缺席
