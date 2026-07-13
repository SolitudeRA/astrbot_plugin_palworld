from pathlib import Path

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


async def _make_repo(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    await db.open()
    await apply_migrations(db)
    return Repository(db, FakeClock(start=1_700_000_000)), db


async def test_get_daily_aggregate_missing_returns_none(tmp_path):
    repo, db = await _make_repo(tmp_path)
    try:
        assert await repo.get_daily_aggregate("s1:g:0", "2026-07-10", "peak") is None
    finally:
        await db.close()


async def test_upsert_and_get_daily_aggregate_roundtrip(tmp_path):
    repo, db = await _make_repo(tmp_path)
    try:
        await repo.upsert_daily_aggregate("s1:g:0", "2026-07-10", "peak", 12)
        assert await repo.get_daily_aggregate("s1:g:0", "2026-07-10", "peak") == 12
        await repo.upsert_daily_aggregate(
            "s1:g:0", "2026-07-10", "summary", {"active": 3, "names": ["a", "b"]}
        )
        assert await repo.get_daily_aggregate("s1:g:0", "2026-07-10", "summary") == {
            "active": 3,
            "names": ["a", "b"],
        }
    finally:
        await db.close()


async def test_upsert_daily_aggregate_overwrites_on_conflict(tmp_path):
    repo, db = await _make_repo(tmp_path)
    try:
        await repo.upsert_daily_aggregate("s1:g:0", "2026-07-10", "peak", 5)
        await repo.upsert_daily_aggregate("s1:g:0", "2026-07-10", "peak", 9)
        assert await repo.get_daily_aggregate("s1:g:0", "2026-07-10", "peak") == 9
        rows = await db.query("SELECT COUNT(*) AS n FROM daily_aggregates")
        assert rows[0]["n"] == 1
    finally:
        await db.close()
