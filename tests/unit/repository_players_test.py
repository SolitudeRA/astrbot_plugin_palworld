import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.models import PlayerIdentity
from palchronicle.domain.enums import IdConfidence
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_upsert_player_then_get_by_name(repo):
    p = PlayerIdentity(
        player_key="pk1", world_id="w1", latest_name="Alice",
        first_seen_at=1000, last_seen_at=1000, latest_level=5,
        latest_guild_key=None, id_confidence=IdConfidence.HIGH,
    )
    await repo.upsert_player(p)
    got = await repo.get_player_by_name("w1", "Alice")
    assert got is not None
    assert got.player_key == "pk1"
    assert got.latest_level == 5
    assert got.id_confidence == IdConfidence.HIGH


async def test_upsert_player_updates_existing(repo):
    p = PlayerIdentity("pk1", "w1", "Alice", 1000, 1000, 5, None, IdConfidence.HIGH)
    await repo.upsert_player(p)
    p2 = PlayerIdentity("pk1", "w1", "Alice", 1000, 2000, 7, "g1", IdConfidence.HIGH)
    await repo.upsert_player(p2)
    got = await repo.get_player_by_name("w1", "Alice")
    assert got.latest_level == 7
    assert got.latest_guild_key == "g1"
    assert got.last_seen_at == 2000


async def test_get_player_by_name_missing(repo):
    assert await repo.get_player_by_name("w1", "Nobody") is None
