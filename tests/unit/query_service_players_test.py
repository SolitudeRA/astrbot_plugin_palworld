from types import SimpleNamespace

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.query_service import QueryService
from palchronicle.domain.models import World
from palchronicle.infrastructure.cache import TTLCache
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

_W = World(world_id="w1", server_id="w", worldguid="g", epoch=0,
           server_name="S", version="1", first_seen_at=0, last_seen_at=0, current_day=1)


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


async def _add_session(repo, key, joined, seconds, status="active"):
    await repo._db.execute_write(
        "INSERT INTO player_sessions (world_id, player_key, joined_at, "
        "last_confirmed_at, left_at, observed_seconds, status, leave_reason) "
        "VALUES ('w1', ?, ?, ?, NULL, ?, ?, NULL)",
        (key, joined, joined, seconds, status))


async def test_rank_level_board_desc_and_dedup(env):
    repo, clock = env
    await _add_player(repo, "k1", "Alice", 30, 100)
    await _add_player(repo, "k2", "Bob", 20, 100)
    await _add_player(repo, "k3", "Alice", 25, 200)  # 同名第二 key → 去重
    dto = await _qs(repo, clock, _cfg()).rank(_W)
    assert dto.level_rows == [("Alice", 30), ("Bob", 20)]


async def test_rank_time_board_sums_and_top_n(env):
    repo, clock = env
    now = clock.now()
    await _add_player(repo, "k1", "Alice", 1, now); await _add_player(repo, "k2", "Bob", 1, now)
    await _add_session(repo, "k1", now, 3600); await _add_session(repo, "k1", now, 600)
    await _add_session(repo, "k2", now, 1800)
    dto = await _qs(repo, clock, _cfg(top_n=1)).rank(_W)
    assert dto.time_rows == [("Alice", 4200)]  # 3600+600 求和、Top1


async def test_excluded_names_and_hidden_filtered_from_rank(env):
    repo, clock = env
    await _add_player(repo, "k1", "Alice", 30, 100)
    await _add_player(repo, "k2", "Bob", 20, 100)
    await repo.set_hidden("w1", "k2", "phash")           # Bob 自助隐藏
    dto = await _qs(repo, clock, _cfg(exclude=["Alice"])).rank(_W)  # Alice 排除名单
    assert dto.level_rows == []                          # 两人都被过滤


async def test_player_profile_online_and_not_found(env):
    repo, clock = env
    now = clock.now()
    await _add_player(repo, "k1", "Alice", 12, now)
    await _add_session(repo, "k1", now, 900)
    dto = await _qs(repo, clock, _cfg()).player_profile(_W, "Alice")
    assert dto.name == "Alice" and dto.level == 12 and dto.online is True and dto.online_seconds == 900
    assert await _qs(repo, clock, _cfg()).player_profile(_W, "Ghost") is None


async def test_player_profile_hidden_returns_none(env):
    repo, clock = env
    await _add_player(repo, "k1", "Alice", 12, 100)
    await repo.set_hidden("w1", "k1", "phash")
    assert await _qs(repo, clock, _cfg()).player_profile(_W, "Alice") is None
