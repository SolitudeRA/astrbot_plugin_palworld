import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.models import WorldMetric
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=1_000_000)
    yield Repository(db, clock)
    await db.close()


async def test_insert_and_latest_metric(repo):
    m1 = WorldMetric(
        world_id="s1:guid:0", observed_at=1000, fps=60.0, frame_time=16.6,
        online_players=3, world_day=5, basecamp_count=2,
    )
    m2 = WorldMetric(
        world_id="s1:guid:0", observed_at=2000, fps=55.0, frame_time=18.0,
        online_players=4, world_day=5, basecamp_count=3,
    )
    await repo.insert_metric(m1)
    await repo.insert_metric(m2)
    latest = await repo.latest_metric("s1:guid:0")
    assert latest is not None
    assert latest.observed_at == 2000
    assert latest.fps == 55.0
    assert latest.online_players == 4
    assert latest.basecamp_count == 3


async def test_latest_metric_none_when_absent(repo):
    assert await repo.latest_metric("nonexistent:guid:0") is None


async def test_latest_metric_isolated_by_world(repo):
    await repo.insert_metric(WorldMetric(
        world_id="wA", observed_at=100, fps=1.0, frame_time=1.0,
        online_players=1, world_day=1, basecamp_count=1,
    ))
    await repo.insert_metric(WorldMetric(
        world_id="wB", observed_at=200, fps=2.0, frame_time=2.0,
        online_players=9, world_day=2, basecamp_count=2,
    ))
    a = await repo.latest_metric("wA")
    assert a.online_players == 1
    assert a.observed_at == 100
