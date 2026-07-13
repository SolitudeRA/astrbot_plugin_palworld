import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.domain.models import WorldMetric
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo_and_clock(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=5000)
    yield Repository(db, clock), clock
    await db.close()


def _metric(world_id, observed_at, online):
    return WorldMetric(
        world_id=world_id, observed_at=observed_at, fps=60.0, frame_time=16.0,
        online_players=online, world_day=1, basecamp_count=0,
    )


async def test_peak_online_max_across_metrics(repo_and_clock):
    repo, _ = repo_and_clock
    await repo.insert_metric(_metric("w", 100, 3))
    await repo.insert_metric(_metric("w", 200, 7))
    await repo.insert_metric(_metric("w", 300, 5))
    assert await repo.peak_online("w") == 7


async def test_peak_online_since_filter(repo_and_clock):
    repo, _ = repo_and_clock
    await repo.insert_metric(_metric("w", 100, 9))
    await repo.insert_metric(_metric("w", 300, 4))
    assert await repo.peak_online("w", since=250) == 4


async def test_peak_online_zero_when_empty(repo_and_clock):
    repo, _ = repo_and_clock
    assert await repo.peak_online("empty") == 0


async def test_upsert_unknown_classes_insert_and_increment(repo_and_clock):
    repo, clock = repo_and_clock
    await repo.upsert_unknown_classes(["Pal/Alpha", "Pal/Beta"])
    await repo.upsert_unknown_classes(["Pal/Alpha"])
    rows = await repo._db.query(
        "SELECT class_name, first_seen_at, count FROM unknown_classes"
        " ORDER BY class_name"
    )
    by_name = {r["class_name"]: (r["first_seen_at"], r["count"]) for r in rows}
    assert by_name["Pal/Alpha"][1] == 2
    assert by_name["Pal/Beta"][1] == 1
    assert by_name["Pal/Alpha"][0] == 5000  # first_seen_at = clock.now()


async def test_upsert_unknown_classes_empty_noop(repo_and_clock):
    repo, _ = repo_and_clock
    await repo.upsert_unknown_classes([])
    rows = await repo._db.query("SELECT COUNT(*) AS n FROM unknown_classes")
    assert rows[0]["n"] == 0
