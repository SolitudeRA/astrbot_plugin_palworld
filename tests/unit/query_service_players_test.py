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
    # joined 在过去且 observed ≤ 墙钟跨度(真实不变量:player_service 按 delta 累加)
    await _add_player(repo, "k1", "Alice", 1, now); await _add_player(repo, "k2", "Bob", 1, now)
    await _add_session(repo, "k1", now - 4000, 3600); await _add_session(repo, "k1", now - 4000, 600)
    await _add_session(repo, "k2", now - 2000, 1800)
    dto = await _qs(repo, clock, _cfg(top_n=1)).rank(_W)
    assert dto.time_rows == [("Alice", 4200)]  # 3600+600 求和、Top1


async def test_rank_time_board_clamps_overnight_session_to_today(env):
    # 跨午夜会话只计今日交叠,不再整段灌入(昨日 23:00 JST 上线持续至今)
    repo, clock = env
    now = clock.now()  # 1_700_000_000 = 2023-11-15 07:13 JST
    today_start_jst = 1_699_974_000  # 2023-11-15 00:00 JST
    joined = today_start_jst - 3600  # 昨日 23:00 JST
    await _add_player(repo, "k1", "Alice", 1, now)
    await _add_session(repo, "k1", joined, now - joined)  # 持续在线,整段 observed
    dto = await _qs(repo, clock, _cfg()).rank(_W)
    assert dto.time_rows == [("Alice", now - today_start_jst)]  # 只计今日部分


async def test_rank_time_board_merges_same_name_keys(env):
    # 同名多 key 按显示名归并为一行
    repo, clock = env
    now = clock.now()
    await _add_player(repo, "k1", "Alice", 1, now)
    await _add_player(repo, "k2", "Alice", 1, now)
    await _add_session(repo, "k1", now - 2000, 1000)
    await _add_session(repo, "k2", now - 2000, 500)
    dto = await _qs(repo, clock, _cfg()).rank(_W)
    assert dto.time_rows == [("Alice", 1500)]


async def test_rank_time_board_hidden_key_bans_whole_name(env):
    # 被隐藏 key 的名字整组剔除:同名另一 key 不得补位泄露
    repo, clock = env
    now = clock.now()
    await _add_player(repo, "k1", "Alice", 1, now)
    await _add_player(repo, "k2", "Alice", 1, now)
    await _add_session(repo, "k1", now - 2000, 1000)
    await _add_session(repo, "k2", now - 2000, 500)
    await repo.set_hidden("w1", "k1", "phash")
    dto = await _qs(repo, clock, _cfg()).rank(_W)
    assert dto.time_rows == []


async def test_rank_level_board_hidden_key_bans_whole_name(env):
    # 等级榜同语义:名字被任一隐藏 key 占用即整组不上榜(修复前 k2 会补位)
    repo, clock = env
    await _add_player(repo, "k1", "Alice", 30, 100)
    await _add_player(repo, "k2", "Alice", 25, 200)
    await _add_player(repo, "k3", "Bob", 20, 100)
    await repo.set_hidden("w1", "k1", "phash")
    dto = await _qs(repo, clock, _cfg()).rank(_W)
    assert dto.level_rows == [("Bob", 20)]


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


async def test_level_board_order_fully_deterministic(env):
    # 同 level 同 last_seen 由第三排序键 player_key ASC 钉死顺序
    repo, clock = env
    await _add_player(repo, "kb", "B", 30, 100)
    await _add_player(repo, "ka", "A", 30, 100)
    rows = await repo.list_players_by_level("w1")
    assert [p.player_key for p in rows] == ["ka", "kb"]


async def test_player_profile_same_name_collision_converges(env):
    # 名字级收敛:同名任一 key 被隐藏,/pal player 整组不可查
    # (同一玩家改名/多 key 时,自助隐藏不因另一 key 未隐藏被绕过)
    repo, clock = env
    await _add_player(repo, "k1", "Alice", 30, 100)
    await _add_player(repo, "k2", "Alice", 25, 200)
    await repo.set_hidden("w1", "k1", "phash")
    assert await _qs(repo, clock, _cfg()).player_profile(_W, "Alice") is None
