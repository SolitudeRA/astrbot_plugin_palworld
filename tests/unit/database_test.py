import asyncio

import pytest

from palchronicle.infrastructure.database import Database


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.open()
    yield database
    await database.close()


async def test_wal_and_foreign_keys_enabled(db):
    rows = await db.query("PRAGMA journal_mode")
    assert rows[0][0].lower() == "wal"
    fk = await db.query("PRAGMA foreign_keys")
    assert fk[0][0] == 1


async def test_execute_write_then_query(db):
    await db.execute_write("CREATE TABLE t (k INTEGER PRIMARY KEY, v TEXT)")
    await db.execute_write("INSERT INTO t (k, v) VALUES (?, ?)", (1, "a"))
    rows = await db.query("SELECT v FROM t WHERE k = ?", (1,))
    assert [r[0] for r in rows] == ["a"]


async def test_executemany_write(db):
    await db.execute_write("CREATE TABLE t (k INTEGER PRIMARY KEY, v TEXT)")
    await db.executemany_write(
        "INSERT INTO t (k, v) VALUES (?, ?)", [(1, "a"), (2, "b"), (3, "c")]
    )
    rows = await db.query("SELECT count(*) FROM t")
    assert rows[0][0] == 3


async def test_write_tx_commits_as_one_unit(db):
    await db.execute_write("CREATE TABLE t (k INTEGER PRIMARY KEY, v TEXT)")
    async with db.write_tx() as conn:
        await conn.execute("INSERT INTO t (k, v) VALUES (?, ?)", (1, "x"))
        await conn.execute("INSERT INTO t (k, v) VALUES (?, ?)", (2, "y"))
    rows = await db.query("SELECT count(*) FROM t")
    assert rows[0][0] == 2


async def test_write_tx_rolls_back_on_error(db):
    await db.execute_write("CREATE TABLE t (k INTEGER PRIMARY KEY, v TEXT)")
    with pytest.raises(ValueError):
        async with db.write_tx() as conn:
            await conn.execute("INSERT INTO t (k, v) VALUES (?, ?)", (1, "x"))
            raise ValueError("boom")
    rows = await db.query("SELECT count(*) FROM t")
    assert rows[0][0] == 0


async def test_write_lock_serializes_concurrent_writes(db):
    await db.execute_write("CREATE TABLE t (k INTEGER PRIMARY KEY)")

    async def writer(k):
        await db.execute_write("INSERT INTO t (k) VALUES (?)", (k,))

    await asyncio.gather(*(writer(i) for i in range(20)))
    rows = await db.query("SELECT count(*) FROM t")
    assert rows[0][0] == 20


async def test_query_row_supports_name_and_positional_access(db):
    """Verify that query results support both positional row[0] and name-based row['col'] access."""
    await db.execute_write("CREATE TABLE t (c INTEGER, name TEXT)")
    await db.execute_write("INSERT INTO t (c, name) VALUES (?, ?)", (1, "x"))
    rows = await db.query("SELECT c, name FROM t")
    assert len(rows) == 1
    # Positional access still works (backward compatible)
    assert rows[0][0] == 1
    assert rows[0][1] == "x"
    # Name-based access now works
    assert rows[0]["c"] == 1
    assert rows[0]["name"] == "x"
