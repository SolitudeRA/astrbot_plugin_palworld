import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.enums import PingBucket
from palchronicle.domain.models import PlayerObservation
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


def _obs(observed_at, level, **kw):
    base = dict(
        observed_at=observed_at, world_id="w1", player_key="pk1", name="Alice",
        level=level, ping_bucket=PingBucket.GOOD, building_count=3,
        guild_key=None, position_cell=None, companion_class=None,
    )
    base.update(kw)
    return PlayerObservation(**base)


async def test_insert_and_latest(repo):
    await repo.insert_observation(_obs(1000, 5))
    await repo.insert_observation(_obs(2000, 8, ping_bucket=PingBucket.OK,
                                       building_count=9, companion_class="Sheepball"))
    got = await repo.latest_observation("w1", "pk1")
    assert got.observed_at == 2000
    assert got.level == 8
    assert got.ping_bucket == PingBucket.OK
    assert got.building_count == 9
    assert got.companion_class == "Sheepball"


async def test_latest_missing(repo):
    assert await repo.latest_observation("w1", "ghost") is None


async def test_position_cell_none_persists_as_null(repo):
    await repo.insert_observation(_obs(1000, 5, position_cell=None))
    rows = await repo._db.query(
        "SELECT position_cell FROM player_observations WHERE world_id='w1'", ()
    )
    assert rows[0]["position_cell"] is None
