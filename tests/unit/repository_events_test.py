import json
from pathlib import Path

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.enums import Confidence, EventType
from palchronicle.domain.models import WorldEvent
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


async def _make_repo(tmp_path: Path) -> tuple[Repository, Database, FakeClock]:
    db = Database(tmp_path / "test.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=1_700_000_000)
    return Repository(db, clock), db, clock


def _event(dedup: str, etype: EventType = EventType.NEW_PLAYER) -> WorldEvent:
    return WorldEvent(
        event_id=None,
        world_id="s1:guid:0",
        event_type=etype,
        subject_type="player",
        subject_key="pk1",
        occurred_at=1_700_000_000,
        confirmed_at=1_700_000_000,
        payload={"foo": "bar"},
        visibility="public",
        confidence=Confidence.HIGH,
        dedup_key=dedup,
    )


async def test_insert_event_returns_true_on_new(tmp_path):
    repo, db, _ = await _make_repo(tmp_path)
    try:
        assert await repo.insert_event(_event("s1:guid:0|NEW_PLAYER|pk1")) is True
        rows = await db.query("SELECT dedup_key, payload_json FROM world_events")
        assert len(rows) == 1
        assert rows[0]["dedup_key"] == "s1:guid:0|NEW_PLAYER|pk1"
        assert json.loads(rows[0]["payload_json"]) == {"foo": "bar"}
    finally:
        await db.close()


async def test_insert_event_dedup_returns_false_no_duplicate(tmp_path):
    repo, db, _ = await _make_repo(tmp_path)
    try:
        assert await repo.insert_event(_event("dup|key")) is True
        assert await repo.insert_event(_event("dup|key")) is False
        rows = await db.query("SELECT COUNT(*) AS n FROM world_events")
        assert rows[0]["n"] == 1
    finally:
        await db.close()
