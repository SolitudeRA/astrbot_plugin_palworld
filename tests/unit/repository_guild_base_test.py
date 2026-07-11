import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.enums import Confidence
from palchronicle.domain.models import Base, BaseObservation, Guild, PalBox
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "t.db"); await db.open(); await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_guild_upsert_and_list(repo):
    g = Guild("gk1", "w1", "Noema", 1000, 1000, 4, 2, 6)
    await repo.upsert_guild(g)
    g2 = Guild("gk1", "w1", "Noema", 1000, 2000, 5, 3, 8)
    await repo.upsert_guild(g2)
    guilds = await repo.list_guilds("w1")
    assert len(guilds) == 1
    assert guilds[0].observed_member_count == 5
    assert guilds[0].palbox_count == 3
    assert guilds[0].last_seen_at == 2000


async def test_palbox_upsert_and_list(repo):
    await repo.upsert_palbox(PalBox("pb1", "w1", "gk1", "10:20:0", 1000, 1000, "active"))
    await repo.upsert_palbox(PalBox("pb1", "w1", "gk1", "10:20:0", 1000, 2000, "active"))
    boxes = await repo.list_palboxes("w1")
    assert len(boxes) == 1
    assert boxes[0].last_seen_at == 2000


async def test_base_list_filters_low_and_hidden(repo):
    await repo.upsert_base(Base("bH", "w1", "pbH", None, "gk1", Confidence.HIGH, False, False, 1000, 1000))
    await repo.upsert_base(Base("bL", "w1", "pbL", None, "gk1", Confidence.LOW, False, False, 1000, 1000))
    await repo.upsert_base(Base("bHid", "w1", "pbHid", None, "gk1", Confidence.HIGH, False, True, 1000, 1000))
    default = {b.base_key for b in await repo.list_bases("w1")}
    assert default == {"bH"}
    with_low = {b.base_key for b in await repo.list_bases("w1", include_low=True)}
    assert with_low == {"bH", "bL"}
    with_hidden = {b.base_key for b in await repo.list_bases("w1", include_hidden=True)}
    assert with_hidden == {"bH", "bHid"}


async def test_base_observation_roundtrip_json(repo):
    o = BaseObservation("bH", "w1", 1000, 6, 4, 12.5, 0.9, {"working": 4, "idle": 2})
    await repo.insert_base_observation(o)
    got = await repo.latest_base_observation("w1", "bH")
    assert got.worker_count == 6
    assert got.average_level == 12.5
    assert got.action_distribution == {"working": 4, "idle": 2}


async def test_latest_base_observation_missing(repo):
    assert await repo.latest_base_observation("w1", "ghost") is None
