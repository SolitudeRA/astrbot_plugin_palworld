import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


@pytest.fixture
async def audit_repo(tmp_path):
    db = Database(tmp_path / "audit.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_insert_and_list_desc(audit_repo):
    await audit_repo.insert_audit(ts=100, admin_id="p:1", action="kick", server_name="s",
                                  target_name="Alice", target_hash="ab12", detail="", success=1, error=None)
    await audit_repo.insert_audit(ts=200, admin_id="p:1", action="stop", server_name="s",
                                  target_name=None, target_hash=None, detail="", success=1, error=None)
    rows = await audit_repo.list_audit(limit=10)
    assert [r["ts"] for r in rows] == [200, 100]   # 倒序
    assert rows[0]["action"] == "stop"


async def test_list_limit(audit_repo):
    for i in range(5):
        await audit_repo.insert_audit(ts=i, admin_id="p:1", action="save", server_name="s",
                                      target_name=None, target_hash=None, detail="", success=1, error=None)
    assert len(await audit_repo.list_audit(limit=2)) == 2


async def test_prune(audit_repo):
    await audit_repo.insert_audit(ts=10, admin_id="p:1", action="save", server_name="s",
                                  target_name=None, target_hash=None, detail="", success=1, error=None)
    await audit_repo.insert_audit(ts=100, admin_id="p:1", action="save", server_name="s",
                                  target_name=None, target_hash=None, detail="", success=1, error=None)
    deleted = await audit_repo.prune_audit(before_ts=50)
    assert deleted == 1
    assert [r["ts"] for r in await audit_repo.list_audit(limit=10)] == [100]
