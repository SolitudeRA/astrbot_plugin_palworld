from types import SimpleNamespace

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.query_service import QueryService
from palworld_terminal.domain.models import World
from palworld_terminal.infrastructure.cache import TTLCache
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations
from palworld_terminal.presentation.commands import Commands

_W = World(world_id="w1", server_id="w", worldguid="g", epoch=0,
           server_name="S", version="1", first_seen_at=0, last_seen_at=0, current_day=1)
_SALT = b"x" * 32


def _cfg(exclude=None, mode="balanced"):
    return SimpleNamespace(
        features=SimpleNamespace(enabled=lambda g: True),
        privacy=SimpleNamespace(mode=mode),
        players=SimpleNamespace(rank_top_n=5, exclude_names=exclude or []),
        world=SimpleNamespace(timezone="Asia/Tokyo"),
        servers=[SimpleNamespace(server_id="w", timezone="")],
    )


@pytest.fixture
async def cmds_env(tmp_path):
    db = Database(tmp_path / "c.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1_700_000_000)
    repo = Repository(db, clock)

    def build(cfg):
        query = QueryService(repo, TTLCache(clock), cfg, None, clock, {}, world_cache={}, report=None)
        c = Commands(routing=None, query=query, repo=repo, cfg=cfg, clock=clock, salt=_SALT)
        async def _rw(umo, msg, sub, is_group):
            from palworld_terminal.presentation.server_arg import parse_arg
            return _W, parse_arg(msg, sub), None
        c._resolve_world = _rw
        return c
    yield repo, build
    await db.close()


async def _add_player(repo, key, name, level, last_seen):
    await repo._db.execute_write(
        "INSERT INTO players (player_key, world_id, latest_name, first_seen_at, "
        "last_seen_at, latest_level, latest_guild_key, id_confidence) "
        "VALUES (?, 'w1', ?, 0, ?, ?, NULL, 'high')", (key, name, last_seen, level))


async def test_bind_then_me_shows_self(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    c = build(_cfg())
    assert "已绑定" in await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    out = await c.me("u", "me", True, "aiocqhttp:1")
    assert "Alice" in out and "Lv12" in out


async def test_me_unbound(cmds_env):
    repo, build = cmds_env
    out = await build(_cfg()).me("u", "me", True, "aiocqhttp:9")
    assert "还没绑定" in out


async def test_bind_not_found(cmds_env):
    repo, build = cmds_env
    out = await build(_cfg()).bind("u", "bind Ghost", True, "aiocqhttp:1")
    assert "未找到玩家" in out


async def test_bind_to_excluded_returns_not_found(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    await repo.set_hidden("w1", "k1", "byhash")           # Alice 被隐藏
    out = await build(_cfg()).bind("u", "bind Alice", True, "aiocqhttp:1")
    assert "未找到玩家" in out                             # 存在性收敛


async def test_me_hide_then_excluded_from_rank(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 30, 100)
    c = build(_cfg())
    await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    assert "隐藏" in await c.me("u", "me hide", True, "aiocqhttp:1")
    dto = await c._query.rank(_W)
    assert dto.level_rows == []                            # Alice 自助隐藏后不出榜
    assert "恢复" in await c.me("u", "me show", True, "aiocqhttp:1")
    dto2 = await c._query.rank(_W)
    assert dto2.level_rows == [("Alice", 30)]


async def test_bind_then_unbind_clears_binding(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    c = build(_cfg())
    await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    out = await c.unbind_self("u", "unbind", True, "aiocqhttp:1")
    assert "Alice" in out and "解除" in out
    # 解绑后 me 显示未绑定(真 DB 验证 delete_binding 生效;no-op 删除会让此断言转红)
    assert "还没绑定" in await c.me("u", "me", True, "aiocqhttp:1")


async def test_unbind_when_not_bound(cmds_env):
    repo, build = cmds_env
    out = await build(_cfg()).unbind_self("u", "unbind", True, "aiocqhttp:9")
    assert "还没有绑定" in out
