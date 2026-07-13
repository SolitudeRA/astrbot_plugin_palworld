import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "r.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_bind_and_get(repo):
    await repo.upsert_binding("phash", "w1", "k1")
    assert await repo.get_binding("phash", "w1") == "k1"
    assert await repo.get_binding("phash", "w2") is None
    assert await repo.get_binding("other", "w1") is None


async def test_bind_last_writer_wins(repo):
    await repo.upsert_binding("phash", "w1", "k1")
    await repo.upsert_binding("phash", "w1", "k2")
    assert await repo.get_binding("phash", "w1") == "k2"


async def test_hidden_set_get_unset(repo):
    await repo.set_hidden("w1", "k1", "phash")
    await repo.set_hidden("w1", "k2", "phash")
    assert await repo.get_hidden_keys("w1") == {"k1", "k2"}
    assert await repo.get_hidden_keys("w2") == set()
    await repo.unset_hidden("w1", "k1")
    assert await repo.get_hidden_keys("w1") == {"k2"}


async def test_delete_binding_isolates_by_world(repo):
    # 同一 phash 下两个 world 各有绑定;删 w1 不得误删 w2
    # (单条 upsert→delete→get None 无法区分"漏 AND world_id"的错误 SQL,故用两条隔离)
    await repo.upsert_binding("phash", "w1", "k1")
    await repo.upsert_binding("phash", "w2", "k2")
    await repo.delete_binding("phash", "w1")
    assert await repo.get_binding("phash", "w1") is None
    assert await repo.get_binding("phash", "w2") == "k2"
