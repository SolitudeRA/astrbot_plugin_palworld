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
