import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.config import ServerConfig
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


def _srv(name, enabled=True, password="pw", base_url="http://h:8212"):
    return ServerConfig(
        server_id=name, name=name, enabled=enabled,
        base_url=base_url, username="admin", password=password,
        timeout=10, verify_tls=True, timezone="",
    )


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "r.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_list_allowed_bindings_only_allowed_pairs(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    await repo.set_active("u1", "a")   # u1→a allowed+active
    await repo.set_active("u1", "b")   # u1→b allowed+active（active 唯一转到 b，a 仍 allowed=1）
    await repo.set_active("u2", "a")   # u2→a allowed
    await repo.revoke("u2", "a")       # u2 撤销（allowed 行删除）
    pairs = await repo.list_allowed_bindings()
    assert set(pairs) == {("u1", "a"), ("u1", "b")}
    # 跨 umo/跨 server 聚合由调用方做；本方法只返回原始对
    assert ("u2", "a") not in pairs


async def test_list_orphan_server_ids_excludes_valid(repo):
    await repo.sync_servers([_srv("a"), _srv("b"), _srv("ghost")])
    await repo.set_active("u1", "b")
    # ghost 在 servers 表但不在 valid → 孤儿；b 在 group_servers 但也在 valid → 非孤儿
    orphans = await repo.list_orphan_server_ids({"a", "b"})
    assert orphans == ["ghost"]


async def test_list_orphan_server_ids_empty_when_all_valid(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    assert await repo.list_orphan_server_ids({"a", "b"}) == []


async def test_bind_umos_sets_allowed_and_active_when_no_prior(repo):
    await repo.sync_servers([_srv("a")])
    await repo.bind_umos_to_server(["u1", "u2"], "a")
    assert await repo.get_allowed("u1") == {"a"}
    assert await repo.get_allowed("u2") == {"a"}
    assert await repo.get_binding_active("u1") == "a"   # 无既有 active → 置 active=1
    assert await repo.get_binding_active("u2") == "a"


async def test_bind_umos_does_not_steal_existing_active(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    await repo.set_active("u1", "b")               # u1 既有 active 在别台 b
    await repo.bind_umos_to_server(["u1"], "a")     # 绑到 a
    assert await repo.get_allowed("u1") == {"a", "b"}   # allowed 累积
    assert await repo.get_binding_active("u1") == "b"   # 既有 active 不被夺
    # 断言每 umo active=1 行 ≤1
    rows = await repo._db.query(
        "SELECT COUNT(*) FROM group_servers WHERE umo='u1' AND active=1")
    assert rows[0][0] == 1


async def test_bind_umos_promotes_preexisting_inactive_row(repo):
    # active pin 边角：(umo,target) 行已存在且 active=0、该 umo 无其它 active →
    # bind 后本行 active 被置 1（不能只靠 ON CONFLICT SET allowed=1 漏置 active）。
    await repo.sync_servers([_srv("a")])
    # 造一个 allowed=1, active=0 的既存行（模拟 seed 早于绑定的历史场景）
    await repo._db.execute_write(
        "INSERT INTO group_servers (umo, server_id, allowed, active, updated_at) "
        "VALUES ('u1','a',1,0,1)")
    await repo.bind_umos_to_server(["u1"], "a")
    assert await repo.get_binding_active("u1") == "a"   # 升到 active=1


async def test_bind_umos_keeps_inactive_when_other_active_exists(repo):
    # (umo,target) 预存 active=0，但该 umo 别台已有 active → 保持 active=0、不夺。
    await repo.sync_servers([_srv("a"), _srv("b")])
    await repo.set_active("u1", "b")   # 别台 active
    await repo._db.execute_write(
        "INSERT INTO group_servers (umo, server_id, allowed, active, updated_at) "
        "VALUES ('u1','a',1,0,1)")
    await repo.bind_umos_to_server(["u1"], "a")
    assert await repo.get_binding_active("u1") == "b"
    rows = await repo._db.query(
        "SELECT active FROM group_servers WHERE umo='u1' AND server_id='a'")
    assert rows[0][0] == 0


async def test_clear_all_group_servers_wipes_and_returns_count(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    await repo.set_active("u1", "a")
    await repo.set_active("u2", "b")
    # 无关表不受影响
    await repo._db.execute_write(
        "INSERT INTO worlds (world_id, server_id, worldguid, epoch) "
        "VALUES ('a:w', 'a', 'g', 0)")
    cleared = await repo.clear_all_group_servers()
    assert cleared == 2
    assert await repo.get_allowed("u1") == set()
    assert await repo.get_allowed("u2") == set()
    # worlds 未被误删
    rows = await repo._db.query("SELECT COUNT(*) FROM worlds")
    assert rows[0][0] == 1


async def _seed_world_data(repo, server_id, world_id):
    """给 (server_id, world_id) 造齐 12 张 world_id 键表各 1 行 + servers/group_servers。

    servers/group_servers 用 INSERT OR IGNORE：转移 purge 测试里该 server 行可能已被
    harness 的 sync_servers 建过（PK 冲突），OR IGNORE 保持幂等；world_id 键表用全新
    world_id 无冲突、普通 INSERT。
    """
    await repo._db.execute_write(
        "INSERT OR IGNORE INTO servers (server_id, name, enabled) VALUES (?, ?, 1)",
        (server_id, server_id))
    await repo._db.execute_write(
        "INSERT INTO worlds (world_id, server_id, worldguid, epoch) VALUES (?, ?, 'g', 0)",
        (world_id, server_id))
    await repo._db.execute_write(
        "INSERT OR IGNORE INTO group_servers (umo, server_id, allowed, active, updated_at) "
        "VALUES (?, ?, 1, 1, 1)", (f"umo-{server_id}", server_id))
    stmts = [
        ("INSERT INTO players (player_key, world_id) VALUES ('p', ?)", (world_id,)),
        ("INSERT INTO player_sessions (world_id, player_key, joined_at, last_confirmed_at, status) "
         "VALUES (?, 'p', 1, 1, 'active')", (world_id,)),
        ("INSERT INTO player_observations (world_id, player_key, observed_at) VALUES (?, 'p', 1)", (world_id,)),
        ("INSERT INTO guilds (guild_key, world_id) VALUES ('g', ?)", (world_id,)),
        ("INSERT INTO palboxes (palbox_key, world_id, position_cell) VALUES ('pb', ?, 'c')", (world_id,)),
        ("INSERT INTO bases (base_key, world_id, palbox_key, confidence) VALUES ('b', ?, 'pb', 'high')", (world_id,)),
        ("INSERT INTO base_observations (world_id, base_key, observed_at) VALUES (?, 'b', 1)", (world_id,)),
        ("INSERT INTO world_metrics (world_id, observed_at) VALUES (?, 1)", (world_id,)),
        ("INSERT INTO world_events (world_id, event_type, subject_type, occurred_at, confirmed_at, "
         "visibility, confidence, dedup_key) VALUES (?, 'e', 's', 1, 1, 'public', 'high', ?)",
         (world_id, f"dk-{world_id}")),
        ("INSERT INTO daily_aggregates (world_id, day, key, value_json) VALUES (?, 'd', 'k', '1')", (world_id,)),
        ("INSERT INTO player_bindings (platform_hash, world_id, player_key, created_at) "
         "VALUES ('ph', ?, 'p', 1)", (world_id,)),
        ("INSERT INTO hidden_players (world_id, player_key, hidden_by, created_at) "
         "VALUES (?, 'p', 'admin', 1)", (world_id,)),
    ]
    for sql, params in stmts:
        await repo._db.execute_write(sql, params)


_WORLD_TABLES = ["players", "player_sessions", "player_observations", "guilds",
                 "palboxes", "bases", "base_observations", "world_metrics",
                 "world_events", "daily_aggregates", "player_bindings", "hidden_players"]


async def test_purge_server_data_wipes_all_world_tables(repo):
    await _seed_world_data(repo, "a", "a:w")
    counts = await repo.purge_server_data("a")
    for t in _WORLD_TABLES:
        assert counts[t] == 1, t
        rows = await repo._db.query(f"SELECT COUNT(*) FROM {t}")
        assert rows[0][0] == 0, t
    for t in ("group_servers", "worlds", "servers"):
        assert counts[t] == 1, t
        rows = await repo._db.query(f"SELECT COUNT(*) FROM {t}")
        assert rows[0][0] == 0, t


async def test_purge_server_data_empty_world_set_short_circuits(repo):
    # 从未轮询台：servers 有行、worlds 无行 → world_id 集为空。
    # 绝不发空 IN ()（SQLite 语法错），只删三张 server 行、12 表零计数、write_tx 不整台回滚。
    await repo._db.execute_write(
        "INSERT INTO servers (server_id, name, enabled) VALUES ('a','a',1)")
    await repo._db.execute_write(
        "INSERT INTO group_servers (umo, server_id, allowed, active, updated_at) "
        "VALUES ('u','a',1,1,1)")
    counts = await repo.purge_server_data("a")   # 不抛 sqlite3.OperationalError
    for t in _WORLD_TABLES:
        assert counts[t] == 0
    assert counts["servers"] == 1 and counts["group_servers"] == 1
    rows = await repo._db.query("SELECT COUNT(*) FROM servers")
    assert rows[0][0] == 0   # 三张 server 行确被删


async def test_purge_server_data_isolates_other_server(repo):
    await _seed_world_data(repo, "a", "a:w")
    await _seed_world_data(repo, "b", "b:w")
    await repo.purge_server_data("a")
    # b 的数据一行不少
    for t in _WORLD_TABLES:
        rows = await repo._db.query(f"SELECT COUNT(*) FROM {t}")
        assert rows[0][0] == 1, t
    rows = await repo._db.query("SELECT server_id FROM servers")
    assert [r[0] for r in rows] == ["b"]
