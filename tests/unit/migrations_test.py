import pytest

from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import (
    MIGRATIONS,
    MigrationError,
    apply_migrations,
)

EXPECTED_TABLES = {
    "servers", "group_servers", "worlds", "players", "player_sessions",
    "player_observations", "guilds", "palboxes", "bases", "base_observations",
    "world_metrics", "world_events", "daily_aggregates", "unknown_classes",
}
EXPECTED_INDEXES = {
    "idx_events_dedup", "idx_events_world_time", "idx_sessions_player_time",
    "idx_obs_player_time", "idx_metrics_world_time", "idx_baseobs_base_time",
}


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "m.db")
    await database.open()
    yield database
    await database.close()


async def _table_names(db):
    rows = await db.query("SELECT name FROM sqlite_master WHERE type='table'")
    return {r[0] for r in rows}


async def _index_names(db):
    rows = await db.query("SELECT name FROM sqlite_master WHERE type='index'")
    return {r[0] for r in rows}


async def test_fresh_db_gets_all_tables(db):
    await apply_migrations(db)
    assert EXPECTED_TABLES <= await _table_names(db)


async def test_fresh_db_gets_all_indexes(db):
    await apply_migrations(db)
    assert EXPECTED_INDEXES <= await _index_names(db)


async def test_user_version_matches_migration_count(db):
    await apply_migrations(db)
    rows = await db.query("PRAGMA user_version")
    assert rows[0][0] == len(MIGRATIONS)


async def test_apply_is_idempotent(db):
    await apply_migrations(db)
    await apply_migrations(db)  # 第二次应为 no-op，不报错
    rows = await db.query("PRAGMA user_version")
    assert rows[0][0] == len(MIGRATIONS)
    assert EXPECTED_TABLES <= await _table_names(db)


async def test_events_dedup_index_is_unique(db):
    await apply_migrations(db)
    await db.execute_write(
        "INSERT INTO world_events "
        "(world_id, event_type, subject_type, subject_key, occurred_at, "
        " confirmed_at, payload_json, visibility, confidence, dedup_key) "
        "VALUES ('w','NEW_PLAYER','player','pk',1,1,'{}','public','high','dk1')"
    )
    import aiosqlite

    with pytest.raises(aiosqlite.IntegrityError):
        await db.execute_write(
            "INSERT INTO world_events "
            "(world_id, event_type, subject_type, subject_key, occurred_at, "
            " confirmed_at, payload_json, visibility, confidence, dedup_key) "
            "VALUES ('w','NEW_PLAYER','player','pk',2,2,'{}','public','high','dk1')"
        )


async def test_failed_migration_raises_migration_error(db):
    async def bad(conn):
        await conn.execute("CREATE TABLE broken (")  # 语法错误

    from palworld_terminal.infrastructure import migrations as m

    original = m.MIGRATIONS
    m.MIGRATIONS = original + [bad]
    try:
        with pytest.raises(MigrationError):
            await apply_migrations(db)
    finally:
        m.MIGRATIONS = original
