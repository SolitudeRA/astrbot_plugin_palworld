from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


async def _cols(db, table):
    rows = await db.query(f"PRAGMA table_info({table})")
    return {r[1] for r in rows}


async def test_migration_0003_creates_tables(tmp_path):
    db = Database(tmp_path / "m.db")
    await db.open()
    await apply_migrations(db)
    assert await _cols(db, "player_bindings") == {
        "platform_hash",
        "world_id",
        "player_key",
        "created_at",
    }
    assert await _cols(db, "hidden_players") == {
        "world_id",
        "player_key",
        "hidden_by",
        "created_at",
    }
    ver = await db.query("PRAGMA user_version")
    assert int(ver[0][0]) == 3
    await db.close()


async def test_migration_idempotent(tmp_path):
    db = Database(tmp_path / "m.db")
    await db.open()
    await apply_migrations(db)
    await apply_migrations(db)  # 第二次不应报错
    ver = await db.query("PRAGMA user_version")
    assert int(ver[0][0]) == 3
    await db.close()
