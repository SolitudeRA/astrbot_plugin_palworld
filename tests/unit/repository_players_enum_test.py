import pytest

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


async def _add_player(repo, key, world, name, level, last_seen):
    await repo._db.execute_write(
        "INSERT INTO players (player_key, world_id, latest_name, first_seen_at, "
        "last_seen_at, latest_level, latest_guild_key, id_confidence) "
        "VALUES (?, ?, ?, 0, ?, ?, NULL, 'high')",
        (key, world, name, last_seen, level),
    )


@pytest.fixture
async def repo(tmp_path):
    db = Database(tmp_path / "r.db")
    await db.open()
    await apply_migrations(db)
    yield Repository(db, FakeClock(1000))
    await db.close()


async def test_list_players_by_name_returns_all_matches(repo):
    await _add_player(repo, "k1", "w1", "Alice", 10, 100)
    await _add_player(repo, "k2", "w1", "Alice", 8, 200)   # 同名不同 key（HIGH/LOW）
    await _add_player(repo, "k3", "w1", "Bob", 5, 100)
    keys = set(await repo.list_players_by_name("w1", "Alice"))
    assert keys == {"k1", "k2"}
    assert await repo.list_players_by_name("w1", "Nobody") == []


async def test_list_players_by_level_orders_and_filters(repo):
    await _add_player(repo, "k1", "w1", "Alice", 10, 100)
    await _add_player(repo, "k2", "w1", "Bob", 20, 100)
    await repo._db.execute_write(  # 无等级/无名的脏行——须被滤除
        "INSERT INTO players (player_key, world_id, latest_name, first_seen_at, "
        "last_seen_at, latest_level, latest_guild_key, id_confidence) "
        "VALUES ('k3', 'w1', NULL, 0, 100, NULL, NULL, 'low')", ())
    ranked = await repo.list_players_by_level("w1")
    assert [p.latest_name for p in ranked] == ["Bob", "Alice"]
    assert all(p.latest_level is not None for p in ranked)
