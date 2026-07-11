from pathlib import Path

import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.enums import Confidence, EventType
from palchronicle.domain.models import Base, BaseObservation, Guild, WorldEvent, WorldMetric
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations

WID = "alpha:guid-1:0"


@pytest.fixture
async def repo(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_latest_metric_returns_most_recent(repo):
    await repo.insert_metric(WorldMetric(WID, 1000, 58.0, 17.0, 3, 42, 5))
    await repo.insert_metric(WorldMetric(WID, 1100, 55.0, 18.0, 4, 42, 6))
    m = await repo.latest_metric(WID)
    assert m.observed_at == 1100
    assert m.online_players == 4


async def test_peak_online(repo):
    await repo.insert_metric(WorldMetric(WID, 1000, 58.0, 17.0, 3, 42, 5))
    await repo.insert_metric(WorldMetric(WID, 1100, 55.0, 18.0, 7, 42, 6))
    assert await repo.peak_online(WID) == 7
    assert await repo.peak_online(WID, since=1050) == 7
    assert await repo.peak_online(WID, since=2000) == 0


async def test_list_guilds(repo):
    await repo.upsert_guild(Guild("g1", WID, "Noema", 900, 1000, 4, 2, 10))
    guilds = await repo.list_guilds(WID)
    assert len(guilds) == 1
    assert guilds[0].latest_name == "Noema"


async def test_list_bases_hides_low_by_default(repo):
    await repo.upsert_base(Base("b-high", WID, "pb1", "Noema-1", "g1", Confidence.HIGH, False, False, 900, 1000))
    await repo.upsert_base(Base("b-low", WID, "pb2", "Noema-2", "g1", Confidence.LOW, False, False, 900, 1000))
    default = await repo.list_bases(WID)
    assert {b.base_key for b in default} == {"b-high"}
    both = await repo.list_bases(WID, include_low=True)
    assert {b.base_key for b in both} == {"b-high", "b-low"}


async def test_latest_base_observation(repo):
    await repo.insert_base_observation(
        BaseObservation("b1", WID, 1000, 8, 6, 17.5, 0.9, {"working": 6, "idle": 2})
    )
    o = await repo.latest_base_observation(WID, "b1")
    assert o.worker_count == 8
    assert o.action_distribution == {"working": 6, "idle": 2}


async def test_list_events_ordered_desc_with_limit(repo):
    for i, ts in enumerate((1000, 1100, 1200)):
        await repo.insert_event(WorldEvent(
            None, WID, EventType.NEW_PLAYER, "player", f"p{i}", ts, ts,
            {}, "public", Confidence.HIGH, f"{WID}|NEW_PLAYER|p{i}",
        ))
    events = await repo.list_events(WID, limit=2)
    assert [e.occurred_at for e in events] == [1200, 1100]
    since = await repo.list_events(WID, since=1150)
    assert [e.occurred_at for e in since] == [1200]
