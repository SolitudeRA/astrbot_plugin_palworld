from types import SimpleNamespace

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.query_service import QueryService
from palworld_terminal.domain.models import World
from palworld_terminal.infrastructure.cache import TTLCache
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations

_W = World(world_id="w1", server_id="w", worldguid="g", epoch=0,
           server_name="S", version="1", first_seen_at=0, last_seen_at=0, current_day=1)
_WEEK = 7 * 86400


def _cfg(top_n=5, exclude=None, mode="balanced"):
    return SimpleNamespace(
        players=SimpleNamespace(rank_top_n=top_n, exclude_names=exclude or []),
        privacy=SimpleNamespace(mode=mode),
        world=SimpleNamespace(timezone="Asia/Tokyo"),
        servers=[SimpleNamespace(server_id="w", timezone="")],
    )


@pytest.fixture
async def env(tmp_path):
    db = Database(tmp_path / "q.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1_700_000_000)
    repo = Repository(db, clock)
    yield repo, clock
    await db.close()


def _qs(repo, clock, cfg):
    return QueryService(repo, TTLCache(clock), cfg, None, clock, {}, world_cache={}, report=None)


async def _add_player(repo, key, name, level, last_seen):
    await repo._db.execute_write(
        "INSERT INTO players (player_key, world_id, latest_name, first_seen_at, "
        "last_seen_at, latest_level, latest_guild_key, id_confidence) "
        "VALUES (?, 'w1', ?, 0, ?, ?, NULL, 'high')", (key, name, last_seen, level))


async def _add_obs(repo, key, observed_at, level):
    await repo._db.execute_write(
        "INSERT INTO player_observations (world_id, player_key, observed_at, level, "
        "ping_bucket, building_count, guild_key, companion_class, position_cell) "
        "VALUES ('w1', ?, ?, ?, 'good', 0, NULL, NULL, NULL)",
        (key, observed_at, level))


# ---- baseline = 窗前最新观测；gain = current − baseline ----

async def test_climb_gain_from_pre_window_baseline(env):
    repo, clock = env
    now = clock.now()
    ws = now - _WEEK
    await _add_player(repo, "k1", "Alice", 25, now)
    await _add_obs(repo, "k1", ws - 1000, 10)   # 窗前基线（<= window_start）
    await _add_obs(repo, "k1", ws - 500, 12)    # 窗前更新——baseline 取最新的 12
    await _add_obs(repo, "k1", now - 100, 25)   # current
    dto = await _qs(repo, clock, _cfg()).rank_climb(_W)
    assert [(e.name, e.gain) for e in dto.rows] == [("Alice", 13)]  # 25 − 12
    assert dto.shallow is False


# ---- 负增量（掉级：同名换人/存档重置）归零 → 不上榜 ----

async def test_climb_negative_gain_dropped(env):
    repo, clock = env
    now = clock.now()
    ws = now - _WEEK
    await _add_player(repo, "k1", "Cara", 30, now)
    await _add_obs(repo, "k1", ws - 1000, 40)
    await _add_obs(repo, "k1", now - 100, 30)   # 掉级 → max(0, -10) = 0
    dto = await _qs(repo, clock, _cfg()).rank_climb(_W)
    assert dto.rows == []


# ---- gain == 0 不上榜 ----

async def test_climb_zero_gain_not_listed(env):
    repo, clock = env
    now = clock.now()
    ws = now - _WEEK
    await _add_player(repo, "k1", "Dan", 20, now)
    await _add_obs(repo, "k1", ws - 1000, 20)
    await _add_obs(repo, "k1", now - 100, 20)   # 无涨幅
    dto = await _qs(repo, clock, _cfg()).rank_climb(_W)
    assert dto.rows == []


# ---- 无窗前观测（新玩家）→ baseline 取窗内最早；shallow 标记 ----

async def test_climb_fallback_baseline_and_shallow(env):
    repo, clock = env
    now = clock.now()
    ws = now - _WEEK
    await _add_player(repo, "k1", "Eve", 12, now)
    await _add_obs(repo, "k1", ws + 1000, 5)    # 窗内最早（无窗前观测）
    await _add_obs(repo, "k1", now - 100, 12)
    dto = await _qs(repo, clock, _cfg()).rank_climb(_W)
    assert [(e.name, e.gain) for e in dto.rows] == [("Eve", 7)]  # 12 − 5
    assert dto.shallow is True   # 全无窗前观测 → 历史不足 7 天


async def test_climb_not_shallow_when_any_pre_window(env):
    repo, clock = env
    now = clock.now()
    ws = now - _WEEK
    await _add_player(repo, "k1", "Alice", 25, now)
    await _add_obs(repo, "k1", ws - 500, 10)
    await _add_obs(repo, "k1", now - 100, 25)
    await _add_player(repo, "k2", "Eve", 12, now)   # 新玩家 fallback
    await _add_obs(repo, "k2", ws + 1000, 5)
    await _add_obs(repo, "k2", now - 100, 12)
    dto = await _qs(repo, clock, _cfg()).rank_climb(_W)
    assert dto.shallow is False
    assert [(e.name, e.gain) for e in dto.rows] == [("Alice", 15), ("Eve", 7)]


# ---- 窗语义：只用窗前/窗内观测；last obs 早于窗口 → baseline==current → gain 0 ----

async def test_climb_stale_player_zero_gain(env):
    repo, clock = env
    now = clock.now()
    ws = now - _WEEK
    await _add_player(repo, "k1", "Ghost", 15, now)
    await _add_obs(repo, "k1", ws - 5000, 15)   # 仅窗前观测，窗内没再露面
    dto = await _qs(repo, clock, _cfg()).rank_climb(_W)
    assert dto.rows == []   # baseline == current == 15 → gain 0


# ---- 隐私收敛：排除名单 / 自助隐藏整组剔除 ----

async def test_climb_excluded_name_removed(env):
    repo, clock = env
    now = clock.now()
    ws = now - _WEEK
    await _add_player(repo, "k1", "Alice", 25, now)
    await _add_obs(repo, "k1", ws - 500, 10)
    await _add_obs(repo, "k1", now - 100, 25)
    await _add_player(repo, "k2", "Bob", 20, now)
    await _add_obs(repo, "k2", ws - 500, 12)
    await _add_obs(repo, "k2", now - 100, 20)
    dto = await _qs(repo, clock, _cfg(exclude=["Alice"])).rank_climb(_W)
    assert [(e.name, e.gain) for e in dto.rows] == [("Bob", 8)]


async def test_climb_hidden_key_bans_name(env):
    repo, clock = env
    now = clock.now()
    ws = now - _WEEK
    await _add_player(repo, "k1", "Alice", 25, now)
    await _add_obs(repo, "k1", ws - 500, 10)
    await _add_obs(repo, "k1", now - 100, 25)
    await repo.set_hidden("w1", "k1", "phash")
    dto = await _qs(repo, clock, _cfg()).rank_climb(_W)
    assert dto.rows == []


# ---- viewer 榜位「你第 N，离前一位差 X」（全体涨幅玩家中，非仅 top-N）----

async def _three_climbers(repo, clock):
    now = clock.now()
    ws = now - _WEEK
    # Alice +15, Bob +8, Eve +7
    for key, name, base, cur in (("k1", "Alice", 10, 25), ("k2", "Bob", 12, 20),
                                 ("k3", "Eve", 5, 12)):
        await _add_player(repo, key, name, cur, now)
        await _add_obs(repo, key, ws - 500, base)
        await _add_obs(repo, key, now - 100, cur)


async def test_climb_viewer_rank_and_gap(env):
    repo, clock = env
    await _three_climbers(repo, clock)
    dto = await _qs(repo, clock, _cfg()).rank_climb(_W, viewer_key="k2")  # Bob 第 2
    assert dto.viewer_rank == 2
    assert dto.viewer_gain == 8
    assert dto.viewer_gap == 7   # 15 − 8


async def test_climb_viewer_top_no_gap(env):
    repo, clock = env
    await _three_climbers(repo, clock)
    dto = await _qs(repo, clock, _cfg()).rank_climb(_W, viewer_key="k1")  # Alice 榜首
    assert dto.viewer_rank == 1
    assert dto.viewer_gap is None


async def test_climb_viewer_unbound_no_footer(env):
    repo, clock = env
    await _three_climbers(repo, clock)
    dto = await _qs(repo, clock, _cfg()).rank_climb(_W)  # 无 viewer
    assert dto.viewer_rank is None and dto.viewer_gap is None
