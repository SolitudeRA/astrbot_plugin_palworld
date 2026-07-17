"""事件主体名共享 resolver（spec §3 据点名口径 / §4.4 八类事件表 / §6#7）。

T6 events / T7 today / T10 guild info 共用本 resolver 供数：
  - 三类 key（player/guild/base）批量解析为显示名；
  - 隐藏/被排除玩家事件缺席（调用方按 subject_type=="player" 且缺席跳过整条）；
  - 隐藏据点回退「据点」（不泄漏名号）；
  - 据点序号空间与 _bases_indexed / guild bases 列表 / #序号 查找同源（include_low=True）。
"""
from pathlib import Path

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.name_resolver import (
    BASE_FALLBACK,
    GUILD_FALLBACK,
    keep_world_subject_under_strict,
    load_excluded_keys,
    resolve_subjects,
)
from palworld_terminal.domain.enums import Confidence, EventType, IdConfidence
from palworld_terminal.domain.models import (
    Base,
    Guild,
    PlayerIdentity,
    World,
    WorldEvent,
)
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations

WID = "alpha:guid-1:0"


def _world() -> World:
    return World(WID, "alpha", "guid-1", 0, "alpha", "0.3", 900, 1200, 42)


@pytest.fixture
async def repo(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1200)
    r = Repository(db, clock)
    await r.upsert_world(_world())
    yield r
    await db.close()


def _ev(event_type, subject_type, subject_key, payload=None) -> WorldEvent:
    return WorldEvent(
        event_id=None, world_id=WID, event_type=event_type,
        subject_type=subject_type, subject_key=subject_key,
        occurred_at=1200, confirmed_at=1200, payload=payload or {},
        visibility="public", confidence=Confidence.HIGH,
        dedup_key=f"{WID}|{event_type}|{subject_key}",
    )


async def test_resolves_three_key_types(repo):
    await repo.upsert_player(
        PlayerIdentity("pk1", WID, "Neo", 900, 1200, 21, "g1", IdConfidence.HIGH)
    )
    await repo.upsert_guild(Guild("g1", WID, "Matrix", 900, 1200, 4, 2, 10))
    await repo.upsert_base(
        Base("b1", WID, "pb1", "海岸木材场", "g1", Confidence.HIGH, False, False, 900, 1200)
    )
    events = [
        _ev(EventType.PLAYER_LEVEL_UP, "player", "pk1", {"old": 20, "new": 21}),
        _ev(EventType.NEW_GUILD, "guild", "g1"),
        _ev(EventType.NEW_BASE, "base", "b1"),
    ]
    names = await resolve_subjects(repo, WID, events, excluded_keys=set())
    assert names["pk1"] == "Neo"
    assert names["g1"] == "Matrix"
    assert names["b1"] == "海岸木材场"


async def test_hidden_player_event_absent(repo):
    # 被隐藏/排除玩家的事件：主体 key 不入表 → 调用方据缺席跳过整条（不泄漏名号）
    await repo.upsert_player(
        PlayerIdentity("pk1", WID, "Neo", 900, 1200, 21, "g1", IdConfidence.HIGH)
    )
    events = [_ev(EventType.NEW_PLAYER, "player", "pk1")]
    names = await resolve_subjects(repo, WID, events, excluded_keys={"pk1"})
    assert "pk1" not in names


async def test_unresolvable_player_absent(repo):
    # 无身份记录的玩家 key 亦缺席（无名可显、跳过安全）
    events = [_ev(EventType.NEW_PLAYER, "player", "ghost")]
    names = await resolve_subjects(repo, WID, events, excluded_keys=set())
    assert "ghost" not in names


async def test_same_name_convergence_bans_whole_group(repo):
    # 同名两 key、其一被隐藏 → 整名跳过（不让另一 key 补位泄露隐藏者，rank/status 同哲学）
    await repo.upsert_player(
        PlayerIdentity("pk1", WID, "Neo", 900, 1200, 21, None, IdConfidence.HIGH)
    )
    await repo.upsert_player(
        PlayerIdentity("pk2", WID, "Neo", 900, 1200, 20, None, IdConfidence.HIGH)
    )
    events = [_ev(EventType.NEW_PLAYER, "player", "pk2")]
    names = await resolve_subjects(repo, WID, events, excluded_keys={"pk1"})
    assert "pk2" not in names


async def test_hidden_base_falls_back_to_generic(repo):
    # hidden 据点不入 include_low 清单 → 回退「据点」，绝不泄漏其名号
    await repo.upsert_base(
        Base("bHid", WID, "pbH", "秘密基地", "g1", Confidence.HIGH, False, True, 900, 1200)
    )
    events = [_ev(EventType.WORKER_DELTA, "base", "bHid", {"prev": 12, "cur": 18})]
    names = await resolve_subjects(repo, WID, events, excluded_keys=set())
    assert names["bHid"] == BASE_FALLBACK
    assert names["bHid"] != "秘密基地"


async def test_low_confidence_base_named_and_indexed(repo):
    # low 置信度据点在统一序号空间内（include_low=True），拿 BASE-{i} 占位名
    await repo.upsert_base(
        Base("b1", WID, "pb1", None, "g1", Confidence.HIGH, False, False, 900, 1200)
    )
    await repo.upsert_base(
        Base("bLow", WID, "pb2", None, "g1", Confidence.LOW, False, False, 900, 1200)
    )
    events = [_ev(EventType.NEW_BASE, "base", "bLow")]
    names = await resolve_subjects(repo, WID, events, excluded_keys=set())
    # ORDER BY guild_key, palbox_key → pb1=1, pb2=2
    assert names["bLow"] == "BASE-2"


async def test_base_display_name_preferred(repo):
    await repo.upsert_base(
        Base("b1", WID, "pb1", "河谷矿场", "g1", Confidence.MEDIUM, False, False, 900, 1200)
    )
    events = [_ev(EventType.BASE_VANISHED, "base", "b1", {"first_missing_day": 42})]
    names = await resolve_subjects(repo, WID, events, excluded_keys=set())
    assert names["b1"] == "河谷矿场"


async def test_unknown_guild_falls_back(repo):
    # 查无公会 → 回退「公会」，绝不回落内部 subject_key（§6#7 丑键 bug 修的供数）
    events = [_ev(EventType.NEW_GUILD, "guild", "ghost-guild")]
    names = await resolve_subjects(repo, WID, events, excluded_keys=set())
    assert names["ghost-guild"] == GUILD_FALLBACK


async def test_world_subject_has_no_name(repo):
    # world 主体（里程碑/在线纪录）无名，不入表
    events = [
        _ev(EventType.WORLD_DAY_MILESTONE, "world", WID, {"milestone": 100}),
        _ev(EventType.ONLINE_RECORD, "world", WID, {"value": 8}),
    ]
    names = await resolve_subjects(repo, WID, events, excluded_keys=set())
    assert names == {}


# ---- Finding 2 回归：strict 只保留 world 主体事件（events/today 共用单一真相源）----


def _mixed_events():
    return [
        _ev(EventType.WORLD_DAY_MILESTONE, "world", WID, {"milestone": 100}),
        _ev(EventType.ONLINE_RECORD, "world", WID, {"value": 8}),
        _ev(EventType.PLAYER_LEVEL_UP, "player", "pk1", {"old": 20, "new": 21}),
        _ev(EventType.NEW_PLAYER, "player", "pk2"),
        _ev(EventType.NEW_GUILD, "guild", "g1"),
        _ev(EventType.NEW_BASE, "base", "b1"),
        _ev(EventType.WORKER_DELTA, "base", "b1", {"prev": 12, "cur": 18}),
        _ev(EventType.BASE_VANISHED, "base", "b2"),
    ]


def test_keep_world_subject_under_strict_drops_player_base_guild():
    kept = keep_world_subject_under_strict(_mixed_events(), strict=True)
    assert {e.subject_type for e in kept} == {"world"}
    assert {e.event_type for e in kept} == {
        EventType.WORLD_DAY_MILESTONE, EventType.ONLINE_RECORD,
    }


def test_keep_world_subject_under_strict_passthrough_when_not_strict():
    src = _mixed_events()
    kept = keep_world_subject_under_strict(src, strict=False)
    assert kept == src           # 内容一致（balanced/advanced 不裁剪）
    assert kept is not src       # 浅拷贝，不改入参


async def test_load_excluded_keys_names_and_hidden(repo):
    await repo.upsert_player(
        PlayerIdentity("pk1", WID, "Neo", 900, 1200, 21, None, IdConfidence.HIGH)
    )
    await repo.upsert_player(
        PlayerIdentity("pk2", WID, "Trinity", 900, 1200, 18, None, IdConfidence.HIGH)
    )
    await repo.set_hidden(WID, "pk2", "phash")
    keys = await load_excluded_keys(repo, WID, ["Neo"])
    assert keys == {"pk1", "pk2"}
