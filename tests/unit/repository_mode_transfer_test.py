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
