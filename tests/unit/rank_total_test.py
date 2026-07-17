from types import SimpleNamespace

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.query_service import QueryService, RankBoardsDTO
from palworld_terminal.domain.models import World
from palworld_terminal.infrastructure.cache import TTLCache
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations
from palworld_terminal.presentation.commands import Commands

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


async def _add_session(repo, key, joined, seconds, left_at):
    """已结束会话（含历史天）：total 直接 Σobserved_seconds，不受当日窗口约束。"""
    await repo._db.execute_write(
        "INSERT INTO player_sessions (world_id, player_key, joined_at, "
        "last_confirmed_at, left_at, observed_seconds, status, leave_reason) "
        "VALUES ('w1', ?, ?, ?, ?, ?, 'left', NULL)",
        (key, joined, joined, left_at, seconds))


# ---- total 聚合正确（跨多日累加、无窗口封顶）----

async def test_total_aggregates_across_days(env):
    repo, clock = env
    now = clock.now()
    await _add_player(repo, "k1", "Alice", 10, now)
    # 三段历史会话，均在过去数天且早已结束——today 窗口一段都不该计入。
    await _add_session(repo, "k1", now - 3 * 86400, 3600, left_at=now - 3 * 86400 + 3600)
    await _add_session(repo, "k1", now - 2 * 86400, 1800, left_at=now - 2 * 86400 + 1800)
    await _add_session(repo, "k1", now - 1 * 86400, 600, left_at=now - 1 * 86400 + 600)
    qs = _qs(repo, clock, _cfg())
    dto = await qs.rank(_W, "total")
    assert dto.total_rows == [("Alice", 6000)]  # 3600+1800+600 全累加
    # 对照：同数据 today 榜为空（全在历史窗口外），证 total 与 today 非同套
    today_dto = await qs.rank(_W, "today")
    assert today_dto.time_rows == []


async def test_total_merges_same_name_keys(env):
    repo, clock = env
    now = clock.now()
    await _add_player(repo, "k1", "Alice", 1, now)
    await _add_player(repo, "k2", "Alice", 1, now)
    await _add_session(repo, "k1", now - 100000, 1000, left_at=now - 99000)
    await _add_session(repo, "k2", now - 100000, 500, left_at=now - 99500)
    dto = await _qs(repo, clock, _cfg()).rank(_W, "total")
    assert dto.total_rows == [("Alice", 1500)]  # 同名多 key 归并一行


# ---- 隐私红线：隐藏一个有历史时长的玩家 → 其整组名字从 total 榜消失 ----

async def test_total_hidden_key_bans_whole_name(env):
    repo, clock = env
    now = clock.now()
    await _add_player(repo, "k1", "Alice", 1, now)
    await _add_player(repo, "k2", "Alice", 1, now)  # 同名另一 key 也有历史时长
    await _add_session(repo, "k1", now - 100000, 1000, left_at=now - 99000)
    await _add_session(repo, "k2", now - 100000, 500, left_at=now - 99500)
    await repo.set_hidden("w1", "k1", "phash")  # 自助隐藏 k1
    dto = await _qs(repo, clock, _cfg()).rank(_W, "total")
    assert dto.total_rows == []  # 名字级收敛：k2 不得补位泄露 Alice 的历史时长


async def test_total_excluded_name_filtered(env):
    repo, clock = env
    now = clock.now()
    await _add_player(repo, "k1", "Alice", 1, now)
    await _add_player(repo, "k2", "Bob", 1, now)
    await _add_session(repo, "k1", now - 100000, 1000, left_at=now - 99000)
    await _add_session(repo, "k2", now - 100000, 500, left_at=now - 99500)
    dto = await _qs(repo, clock, _cfg(exclude=["Alice"])).rank(_W, "total")
    assert dto.total_rows == [("Bob", 500)]  # exclude_names 复用 load_excluded_keys


# ---- strict 下 total 回 notice（命令层双砍之一）----

class _StubQuery:
    async def rank(self, world, mode="both"):
        return RankBoardsDTO(time_rows=[("A", 60)], level_rows=[("A", 9)],
                             total_rows=[("A", 120)])


def _cmds(mode="strict"):
    from palworld_terminal.application.command_permissions import CommandOverride
    cfg = SimpleNamespace(
        permissions=SimpleNamespace(
            command_overrides={"rank": CommandOverride(enabled=True)}),
        privacy=SimpleNamespace(mode=mode),
    )
    c = Commands(routing=None, query=_StubQuery(), repo=None, cfg=cfg,
                 clock=SimpleNamespace(now=lambda: 0))

    async def _rw(umo, msg, sub, is_group):
        return (SimpleNamespace(world_id="w1", server_id="w"),
                SimpleNamespace(name=msg, server_override=None), None, "srv")
    c._resolve_world = _rw
    return c


async def test_rank_total_in_strict_returns_notice():
    out = await _cmds(mode="strict").rank("u", "total", True)
    assert "strict" in out or "停用" in out
    assert "累计时长榜" not in out
