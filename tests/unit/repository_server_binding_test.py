import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.config import BindingConfig, ServerConfig
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


def _srv(name, enabled=True):
    return ServerConfig(
        server_id=name, name=name, enabled=enabled,
        base_url="http://h:8212", username="admin", password="pw",
        timeout=10, verify_tls=True, timezone="",
    )


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "r.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_sync_servers_upserts(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    rows = await repo._db.query("SELECT server_id FROM servers ORDER BY server_id")
    assert [r[0] for r in rows] == ["a", "b"]


async def test_seed_bindings_inserts_when_absent(repo):
    await repo.sync_servers([_srv("a")])
    await repo.seed_bindings([BindingConfig(umo="u1", server="a", active=True)])
    assert await repo.get_binding_active("u1") == "a"
    assert await repo.get_allowed("u1") == {"a"}


async def test_seed_bindings_seed_only_does_not_overwrite_runtime(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    # 运行时管理员把 u1 切到 b
    await repo.set_active("u1", "b")
    # 预设仍指向 a → seed-only 不得覆盖运行时
    await repo.seed_bindings([BindingConfig(umo="u1", server="a", active=True)])
    assert await repo.get_binding_active("u1") == "b"


async def test_set_active_clears_other_active_for_same_umo(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    await repo.set_active("u1", "a")
    await repo.set_active("u1", "b")
    assert await repo.get_binding_active("u1") == "b"
    allowed = await repo.get_allowed("u1")
    assert allowed == {"a", "b"}  # allowed 累积，active 唯一


async def test_revoke_removes_allowed_and_clears_active(repo):
    await repo.sync_servers([_srv("a")])
    await repo.set_active("u1", "a")
    await repo.revoke("u1", "a")
    assert await repo.get_binding_active("u1") is None
    assert await repo.get_allowed("u1") == set()


async def test_cleanup_orphan_bindings_removes_unknown_servers(repo):
    await repo.sync_servers([_srv("a"), _srv("b")])
    await repo.set_active("u1", "a")
    await repo.set_active("u2", "b")
    # b 从就绪集合消失
    await repo.cleanup_orphan_bindings({"a"})
    assert await repo.get_allowed("u2") == set()
    assert await repo.get_allowed("u1") == {"a"}
