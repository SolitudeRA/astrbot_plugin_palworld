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


def _cfg(exclude=None, mode="balanced", world_mode="multi"):
    from tests.unit._perm import all_on
    return SimpleNamespace(
        permissions=SimpleNamespace(command_overrides=all_on()),
        privacy=SimpleNamespace(mode=mode),
        routing=SimpleNamespace(world_mode=world_mode),
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
            return _W, parse_arg(msg, sub), None, "主服"
        c._reads._resolve_world = _rw
        return c
    yield repo, build
    await db.close()


async def _add_player(repo, key, name, level, last_seen):
    await repo._db.execute_write(
        "INSERT INTO players (player_key, world_id, latest_name, first_seen_at, "
        "last_seen_at, latest_level, latest_guild_key, id_confidence) "
        "VALUES (?, 'w1', ?, 0, ?, ?, NULL, 'high')", (key, name, last_seen, level))


# ---- me 卡片 / 未绑定 ----

async def test_bind_then_me_shows_self(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    c = build(_cfg())
    assert "已绑定" in await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    out = await c.me("u", "me", True, "aiocqhttp:1")
    assert "👤 我的玩家 · Alice" in out and "Lv12" in out


async def test_me_unbound_multi_scoped(cmds_env):
    repo, build = cmds_env
    out = await build(_cfg()).me("u", "me", True, "aiocqhttp:9")
    assert "你在「主服」还没有绑定玩家" in out
    assert "/pal player bind" in out


async def test_me_unbound_single_no_anchor(cmds_env):
    repo, build = cmds_env
    out = await build(_cfg(world_mode="single")).me("u", "me", True, "aiocqhttp:9")
    assert out.startswith("你还没有绑定玩家")
    assert "主服" not in out


# ---- me 已隐藏角标 + hide/show 带锚（§4.25）----

async def test_me_hidden_badge(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    c = build(_cfg())
    await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    await c.me("u", "me hide", True, "aiocqhttp:1")
    out = await c.me("u", "me", True, "aiocqhttp:1")
    assert "已隐藏" in out


async def test_me_hide_show_multi_anchor(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 30, 100)
    c = build(_cfg())
    await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    hide = await c.me("u", "me hide", True, "aiocqhttp:1")
    assert "已将你从「主服」的排行与查询中隐藏" in hide
    assert "/pal me show" in hide
    show = await c.me("u", "me show", True, "aiocqhttp:1")
    assert "已恢复你在「主服」的可见性" in show


async def test_me_hide_show_single_no_anchor(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 30, 100)
    c = build(_cfg(world_mode="single"))
    await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    hide = await c.me("u", "me hide", True, "aiocqhttp:1")
    assert "隐藏" in hide and "主服" not in hide
    show = await c.me("u", "me show", True, "aiocqhttp:1")
    assert "恢复" in show and "主服" not in show


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


# ---- bind 成功 / 改绑透明化 / 同名重绑 / 找不到（§4.11）----

async def test_bind_ok_multi_anchor_and_hint(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    out = await build(_cfg()).bind("u", "bind Alice", True, "aiocqhttp:1")
    assert "✅ 已绑定玩家「Alice」 · 主服" in out
    assert "/pal me" in out


async def test_bind_ok_single_no_anchor(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    out = await build(_cfg(world_mode="single")).bind("u", "bind Alice", True, "aiocqhttp:1")
    assert out.startswith("✅ 已绑定玩家「Alice」")
    assert "主服" not in out


async def test_bind_rebind_transparency(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    await _add_player(repo, "k2", "Bob", 15, 100)
    c = build(_cfg())
    await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    out = await c.bind("u", "bind Bob", True, "aiocqhttp:1")
    assert "已改绑到玩家「Bob」（原绑定「Alice」）" in out
    assert "主服" in out


async def test_bind_same_name_no_rebind_clause(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    c = build(_cfg())
    await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    out = await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    assert "改绑" not in out and "原绑定" not in out
    assert "已绑定玩家「Alice」" in out


async def test_bind_not_found(cmds_env):
    repo, build = cmds_env
    out = await build(_cfg()).bind("u", "bind Ghost", True, "aiocqhttp:1")
    assert out.startswith("❌ 未找到玩家「Ghost」，无法绑定")
    assert "/pal online" in out


async def test_bind_to_excluded_returns_not_found(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    await repo.set_hidden("w1", "k1", "byhash")           # Alice 被隐藏
    out = await build(_cfg()).bind("u", "bind Alice", True, "aiocqhttp:1")
    assert "未找到玩家" in out                             # 存在性收敛


# ---- unbind 成功 / 悬空不出哈希 / 未绑定（§4.12）----

async def test_unbind_ok_multi_anchor(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "k1", "Alice", 12, 100)
    c = build(_cfg())
    await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    out = await c.unbind_self("u", "unbind", True, "aiocqhttp:1")
    assert "✅ 已解除绑定 · Alice · 主服" in out
    assert "/pal player bind" in out
    # 解绑后 me 显示未绑定（真 DB 验证 delete_binding 生效）
    assert "还没有绑定" in await c.me("u", "me", True, "aiocqhttp:1")


async def test_unbind_dangling_no_hash(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "hashy_key_abc", "Alice", 12, 100)
    c = build(_cfg())
    await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    # 玩家行消失 → 悬空绑定；解绑不得渲染 player_key 哈希
    await repo._db.execute_write("DELETE FROM players WHERE player_key='hashy_key_abc'")
    out = await c.unbind_self("u", "unbind", True, "aiocqhttp:1")
    assert "已解除绑定" in out
    assert "hashy_key_abc" not in out


async def test_unbind_dangling_single_no_anchor(cmds_env):
    repo, build = cmds_env
    await _add_player(repo, "hashy_key_abc", "Alice", 12, 100)
    c = build(_cfg(world_mode="single"))
    await c.bind("u", "bind Alice", True, "aiocqhttp:1")
    await repo._db.execute_write("DELETE FROM players WHERE player_key='hashy_key_abc'")
    out = await c.unbind_self("u", "unbind", True, "aiocqhttp:1")
    assert "主服" not in out
    assert "hashy_key_abc" not in out


async def test_unbind_when_not_bound_multi(cmds_env):
    repo, build = cmds_env
    out = await build(_cfg()).unbind_self("u", "unbind", True, "aiocqhttp:9")
    assert "你在「主服」还没有绑定玩家，无需解绑" in out


async def test_unbind_when_not_bound_single(cmds_env):
    repo, build = cmds_env
    out = await build(_cfg(world_mode="single")).unbind_self("u", "unbind", True, "aiocqhttp:9")
    assert out.startswith("你还没有绑定玩家，无需解绑")
    assert "主服" not in out
