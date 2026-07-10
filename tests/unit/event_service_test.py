from pathlib import Path

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.event_service import EventService
from palchronicle.domain.enums import EventType
from palchronicle.domain.models import World
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


def _world() -> World:
    return World(
        world_id="s1:guid:0", server_id="s1", worldguid="guid", epoch=0,
        server_name="Srv", version="1.0", first_seen_at=100,
        last_seen_at=100, current_day=1,
    )


async def _make(tmp_path: Path):
    db = Database(tmp_path / "e.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=1000)
    repo = Repository(db, clock)
    return EventService(repo, clock), repo, db, clock


def test_dedup_key_format():
    key = EventService.dedup_key("s1:g:0", EventType.PLAYER_LEVEL_UP, "pk", 42)
    assert key == "s1:g:0|PLAYER_LEVEL_UP|pk|42"


async def test_level_up_emits_once(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.level_up(_world(), "pk1", old=10, new=13)
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
        ev = rows[0]
        assert ev.event_type == EventType.PLAYER_LEVEL_UP
        assert ev.subject_key == "pk1"
        assert ev.payload == {"new": 13, "old": 10}
        assert ev.dedup_key == "s1:guid:0|PLAYER_LEVEL_UP|pk1|13"
    finally:
        await db.close()


async def test_level_up_dedup_same_new_level_no_duplicate(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.level_up(_world(), "pk1", old=10, new=13)
        await svc.level_up(_world(), "pk1", old=12, new=13)  # same new
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
    finally:
        await db.close()


async def test_level_up_multi_level_records_old_to_new(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.level_up(_world(), "pk1", old=10, new=15)
        rows = await repo.list_events("s1:guid:0")
        assert rows[0].payload == {"new": 15, "old": 10}
    finally:
        await db.close()


async def test_level_down_emits_nothing(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.level_up(_world(), "pk1", old=20, new=18)
        await svc.level_up(_world(), "pk1", old=20, new=20)  # equal
        rows = await repo.list_events("s1:guid:0")
        assert rows == []
    finally:
        await db.close()


async def test_new_player_emits_once_and_dedups(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.new_player(_world(), "pk1")
        await svc.new_player(_world(), "pk1")  # duplicate
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
        assert rows[0].event_type == EventType.NEW_PLAYER
        assert rows[0].subject_type == "player"
        assert rows[0].subject_key == "pk1"
        assert rows[0].dedup_key == "s1:guid:0|NEW_PLAYER|pk1"
    finally:
        await db.close()


async def test_new_guild_emits_once_and_dedups(tmp_path):
    svc, repo, db, _ = await _make(tmp_path)
    try:
        await svc.new_guild(_world(), "gk1")
        await svc.new_guild(_world(), "gk1")
        rows = await repo.list_events("s1:guid:0")
        assert len(rows) == 1
        assert rows[0].event_type == EventType.NEW_GUILD
        assert rows[0].subject_type == "guild"
        assert rows[0].subject_key == "gk1"
        assert rows[0].dedup_key == "s1:guid:0|NEW_GUILD|gk1"
    finally:
        await db.close()
