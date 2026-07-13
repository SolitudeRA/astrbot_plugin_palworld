import json
from pathlib import Path

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.domain.enums import Confidence, EventType
from palworld_terminal.domain.models import WorldEvent, WorldMetric
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


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


async def test_list_events_ordered_desc_and_since_filter(tmp_path):
    repo, db, _ = await _make_repo(tmp_path)
    try:
        e_old = _event("k1")
        e_old.occurred_at = 100
        e_new = _event("k2")
        e_new.occurred_at = 300
        e_mid = _event("k3")
        e_mid.occurred_at = 200
        for e in (e_old, e_new, e_mid):
            await repo.insert_event(e)
        got = await repo.list_events("s1:guid:0", limit=10)
        assert [e.occurred_at for e in got] == [300, 200, 100]
        assert [e.dedup_key for e in got] == ["k2", "k3", "k1"]
        since = await repo.list_events("s1:guid:0", since=200, limit=10)
        assert [e.occurred_at for e in since] == [300, 200]
        assert since[0].event_type == EventType.NEW_PLAYER
        assert since[0].payload == {"foo": "bar"}
    finally:
        await db.close()


async def test_list_events_respects_limit_and_world_isolation(tmp_path):
    repo, db, _ = await _make_repo(tmp_path)
    try:
        for i in range(5):
            e = _event(f"w1-{i}")
            e.occurred_at = 100 + i
            await repo.insert_event(e)
        other = _event("other")
        other.world_id = "s2:guid:0"
        await repo.insert_event(other)
        got = await repo.list_events("s1:guid:0", limit=3)
        assert len(got) == 3
        assert [e.occurred_at for e in got] == [104, 103, 102]
    finally:
        await db.close()


async def test_peak_online(tmp_path):
    repo, db, _ = await _make_repo(tmp_path)
    try:
        assert await repo.peak_online("s1:guid:0") == 0
        for at, online in ((100, 3), (200, 7), (300, 5)):
            await repo.insert_metric(
                WorldMetric(
                    world_id="s1:guid:0", observed_at=at, fps=60.0,
                    frame_time=16.0, online_players=online, world_day=1,
                    basecamp_count=2,
                )
            )
        assert await repo.peak_online("s1:guid:0") == 7
        assert await repo.peak_online("s1:guid:0", since=250) == 5
    finally:
        await db.close()
