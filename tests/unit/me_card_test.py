"""me_card 数据层（spec §5）：百分位 via list_players_by_level、随身 join 直比（不重复
hash）、随身三态（shown/none_out/no_data）、离线字段预粗化（无绝对时间戳）。"""
from types import SimpleNamespace

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.query_service import QueryService
from palworld_terminal.domain.enums import (
    ActionCategory,
    IdConfidence,
    SessionStatus,
    UnitType,
)
from palworld_terminal.domain.models import (
    CharacterActor,
    GameDataSnapshot,
    PlayerIdentity,
    PlayerSession,
    World,
)
from palworld_terminal.infrastructure.cache import TTLCache
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations

_NOW = 1_700_000_000
_W = World(world_id="w1", server_id="w", worldguid="g", epoch=0,
           server_name="S", version="1", first_seen_at=0, last_seen_at=0, current_day=1)


class _Meta:
    """随身物种/元素解析桩：仅识别皮皮鸡（草），其余优雅降级。"""

    def pal_name(self, cls):
        return {"BP_ChickenPal_C": "皮皮鸡"}.get(cls, cls)

    def element(self, cls):
        return {"BP_ChickenPal_C": "grass"}.get(cls, "unknown")


def _cfg():
    return SimpleNamespace(
        players=SimpleNamespace(rank_top_n=5, exclude_names=[]),
        privacy=SimpleNamespace(mode="balanced"),
        world=SimpleNamespace(timezone="Asia/Tokyo"),
        servers=[SimpleNamespace(server_id="w", timezone="")],
    )


@pytest.fixture
async def env(tmp_path):
    db = Database(tmp_path / "q.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(_NOW)
    repo = Repository(db, clock)
    yield repo, clock
    await db.close()


def _qs(repo, clock, *, world_cache=None, meta=None):
    return QueryService(
        repo, TTLCache(clock), _cfg(), meta, clock, {},
        world_cache=world_cache if world_cache is not None else {}, report=None,
    )


async def _player(repo, key, name, level, *, first_seen=0, last_seen=_NOW, guild=None):
    await repo.upsert_player(PlayerIdentity(
        player_key=key, world_id="w1", latest_name=name,
        first_seen_at=first_seen, last_seen_at=last_seen, latest_level=level,
        latest_guild_key=guild, id_confidence=IdConfidence.HIGH,
    ))


async def _session(repo, key, *, observed, open_):
    await repo.insert_session(PlayerSession(
        id=None, world_id="w1", player_key=key, joined_at=_NOW - observed,
        last_confirmed_at=_NOW, left_at=None if open_ else _NOW,
        observed_seconds=observed,
        status=SessionStatus.ACTIVE if open_ else SessionStatus.CLOSED,
        leave_reason=None,
    ))


def _actor(unit_type, **kw):
    base = dict(
        unit_type=unit_type, instance_id=None, nickname=None,
        trainer_instance_id=None, trainer_nickname=None, player_userid=None,
        level=None, hp=None, max_hp=None, guild_id=None, guild_name=None,
        pal_class=None, action=ActionCategory.UNKNOWN, ai_action=ActionCategory.UNKNOWN,
        x=None, y=None, z=None, is_active=True,
    )
    base.update(kw)
    return CharacterActor(**base)


def _gd(*actors):
    return GameDataSnapshot(observed_at=_NOW, fps=60.0, average_fps=60.0,
                            characters=list(actors), palboxes=[])


# ---- ① 百分位：复用现成 list_players_by_level（超越有记录玩家的 X%）----

async def test_percentile_uses_list_players_by_level(env):
    repo, clock = env
    # 5 名有记录玩家 Lv 50/40/30/20/10；本人 Lv30 → 超越 {20,10}=2/5=40%。
    for key, name, lvl in [("k50", "A", 50), ("k40", "B", 40), ("me", "Me", 30),
                           ("k20", "D", 20), ("k10", "E", 10)]:
        await _player(repo, key, name, lvl)
    dto = await _qs(repo, clock).me_card(_W, "me")
    assert dto is not None
    assert dto.percentile == 40.0


# ---- ② 随身 join 直比：Player.player_userid == player_key，绝不再套 hash ----

async def test_companion_shown_direct_join_no_double_hash(env):
    repo, clock = env
    # player_key 直接等于快照里已脱敏的 Player.player_userid——me_card 直比命中；
    # 若错误地再套一层 hash → hash(key) != key → 落 none_out，本断言即红。
    await _player(repo, "phash-me", "Me", 30)
    await _session(repo, "phash-me", observed=600, open_=True)
    gd = _gd(
        _actor(UnitType.PLAYER, instance_id="INST-P1",
               player_userid="phash-me", level=30),
        _actor(UnitType.OTOMO, trainer_instance_id="INST-P1",
               pal_class="BP_ChickenPal_C", level=48, hp=80, max_hp=100,
               action=ActionCategory.WORKING),
    )
    dto = await _qs(repo, clock, world_cache={"w": gd}, meta=_Meta()).me_card(_W, "phash-me")
    assert dto is not None
    assert dto.companion_status == "shown"
    c = dto.companion
    assert c is not None
    assert (c.species_name, c.element, c.level, c.action_label, c.hp_ratio) == (
        "皮皮鸡", "grass", 48, "working", 0.8)


# ---- ③ 三态：会话在线 + 快照有 + 本人 actor 在 + 无 OtomoPal → none_out ----

async def test_companion_none_out_when_player_present_but_no_otomo(env):
    repo, clock = env
    await _player(repo, "phash-me", "Me", 30)
    await _session(repo, "phash-me", observed=600, open_=True)
    gd = _gd(_actor(UnitType.PLAYER, instance_id="INST-P1", player_userid="phash-me"))
    dto = await _qs(repo, clock, world_cache={"w": gd}, meta=_Meta()).me_card(_W, "phash-me")
    assert dto is not None
    assert dto.companion_status == "none_out"
    assert dto.companion is None


# ---- ③ 三态：无快照（默认部署 game-data 不轮询）→ no_data，绝不谎称没带 ----

async def test_companion_no_data_when_no_snapshot(env):
    repo, clock = env
    await _player(repo, "phash-me", "Me", 30)
    await _session(repo, "phash-me", observed=600, open_=True)
    dto = await _qs(repo, clock, world_cache={}, meta=_Meta()).me_card(_W, "phash-me")
    assert dto is not None
    assert dto.companion_status == "no_data"
    assert dto.companion is None


# ---- ③ 三态：快照有但本人不在其中（就近可见）→ no_data，不谎称没带 ----

async def test_companion_no_data_when_player_absent_from_snapshot(env):
    repo, clock = env
    await _player(repo, "phash-me", "Me", 30)
    await _session(repo, "phash-me", observed=600, open_=True)
    gd = _gd(_actor(UnitType.PLAYER, instance_id="INST-OTHER", player_userid="someone"))
    dto = await _qs(repo, clock, world_cache={"w": gd}, meta=_Meta()).me_card(_W, "phash-me")
    assert dto is not None
    assert dto.companion_status == "no_data"
    assert dto.companion is None


# ---- ④ 离线：online=False + 累计/last_seen，无实时 HP/随身，无绝对时间戳 ----

async def test_offline_fields_no_realtime_no_absolute_timestamp(env):
    repo, clock = env
    await _player(repo, "phash-me", "Me", 30,
                  first_seen=_NOW - 10 * 86400, last_seen=_NOW - 3 * 86400)
    await _session(repo, "phash-me", observed=7200, open_=False)  # 闭合会话计入累计
    # 即便快照存在，会话已闭合 → 判离线；离线态绝不给随身/实时血量。
    gd = _gd(_actor(UnitType.PLAYER, instance_id="INST-P1", player_userid="phash-me"))
    dto = await _qs(repo, clock, world_cache={"w": gd}, meta=_Meta()).me_card(_W, "phash-me")
    assert dto is not None
    assert dto.online is False
    assert dto.online_seconds == 0
    assert dto.total_seconds == 7200
    assert dto.companion is None
    assert dto.companion_status == "no_data"
    # 预粗化为相对天（隐私 P1：绝对登录/登出时刻=作息，绝不出绝对时间戳）。
    assert dto.last_seen_at == 3
    assert dto.first_seen_at == 10
    assert dto.last_seen_at < 86400 and dto.first_seen_at < 86400
    assert dto.last_seen_at != _NOW - 3 * 86400   # 非 epoch


# ---- 悬空绑定（玩家行不存在）→ None（与 profile_for_key 同语义）----

async def test_dangling_binding_returns_none(env):
    repo, clock = env
    dto = await _qs(repo, clock).me_card(_W, "ghost-key")
    assert dto is None
