import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.config import HistoryConfig
from palchronicle.domain.models import World
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "w.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


def _world(server_id="s1", guid="G1", last_seen=1000, day=5):
    return World(
        world_id=f"{server_id}:{guid}:0", server_id=server_id, worldguid=guid,
        epoch=0, server_name="Srv", version="1.0",
        first_seen_at=100, last_seen_at=last_seen, current_day=day,
    )


async def test_upsert_and_get_current_world(repo):
    await repo.upsert_world(_world())
    got = await repo.get_current_world("s1")
    assert got is not None
    assert got.world_id == "s1:G1:0"
    assert got.current_day == 5


async def test_upsert_world_is_idempotent_updates_last_seen(repo):
    await repo.upsert_world(_world(last_seen=1000, day=5))
    await repo.upsert_world(_world(last_seen=2000, day=6))
    got = await repo.get_current_world("s1")
    assert got.last_seen_at == 2000
    assert got.current_day == 6
    rows = await repo._db.query("SELECT count(*) FROM worlds")
    assert rows[0][0] == 1


async def test_get_current_world_picks_latest_last_seen(repo):
    await repo.upsert_world(_world(guid="G1", last_seen=1000))
    await repo.upsert_world(_world(guid="G2", last_seen=3000))
    got = await repo.get_current_world("s1")
    assert got.worldguid == "G2"


async def test_get_current_world_none_when_absent(repo):
    assert await repo.get_current_world("nope") is None


async def test_prune_deletes_old_metrics_and_observations(repo):
    now = 100 * 86400  # day 100 (epoch)
    history = HistoryConfig(
        raw_metrics_days=7, aggregate_days=90, session_days=365, observation_days=180
    )
    # 一条旧指标(8 天前)、一条新指标(1 天前)
    await repo._db.execute_write(
        "INSERT INTO world_metrics (world_id, observed_at, fps, frame_time, online_players, world_day, basecamp_count) "
        "VALUES ('w', ?, 60, 16, 1, 5, 0)",
        (now - 8 * 86400,),
    )
    await repo._db.execute_write(
        "INSERT INTO world_metrics (world_id, observed_at, fps, frame_time, online_players, world_day, basecamp_count) "
        "VALUES ('w', ?, 60, 16, 1, 5, 0)",
        (now - 1 * 86400,),
    )
    # 一条旧观察(200 天前)、一条新观察(10 天前)
    await repo._db.execute_write(
        "INSERT INTO player_observations (world_id, player_key, observed_at, level, ping_bucket, building_count) "
        "VALUES ('w','pk', ?, 1, 'good', 0)",
        (now - 200 * 86400,),
    )
    await repo._db.execute_write(
        "INSERT INTO player_observations (world_id, player_key, observed_at, level, ping_bucket, building_count) "
        "VALUES ('w','pk', ?, 1, 'good', 0)",
        (now - 10 * 86400,),
    )
    await repo.prune(history, now)
    m = await repo._db.query("SELECT count(*) FROM world_metrics")
    o = await repo._db.query("SELECT count(*) FROM player_observations")
    assert m[0][0] == 1
    assert o[0][0] == 1


async def test_prune_keeps_events(repo):
    now = 100 * 86400
    history = HistoryConfig(
        raw_metrics_days=7, aggregate_days=90, session_days=365, observation_days=180
    )
    await repo._db.execute_write(
        "INSERT INTO world_events "
        "(world_id, event_type, subject_type, subject_key, occurred_at, confirmed_at, payload_json, visibility, confidence, dedup_key) "
        "VALUES ('w','NEW_PLAYER','player','pk', ?, ?, '{}', 'public', 'high', 'dk-old')",
        (now - 400 * 86400, now - 400 * 86400),
    )
    await repo.prune(history, now)
    rows = await repo._db.query("SELECT count(*) FROM world_events")
    assert rows[0][0] == 1  # 事件长期保留
