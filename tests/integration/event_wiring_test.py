from pathlib import Path

from palworld_terminal.adapters import normalizer as normalizer_mod
from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.event_service import EventService
from palworld_terminal.application.snapshot_service import SnapshotService
from palworld_terminal.domain.enums import EventType
from palworld_terminal.domain.models import World
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


def _world() -> World:
    return World(
        world_id="s1:guid:0", server_id="s1", worldguid="guid", epoch=0,
        server_name="Srv", version="1.0", first_seen_at=0,
        last_seen_at=0, current_day=1,
    )


async def _wire(tmp_path: Path):
    db = Database(tmp_path / "wire.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=1000)
    repo = Repository(db, clock)
    events = EventService(repo, clock)
    return repo, events, clock, db


def _make_svc(repo, events, clock):
    # SnapshotService only needs a few collaborators for ingest_metrics;
    # other collaborators may be omitted in this focused wiring test.
    svc = SnapshotService.__new__(SnapshotService)
    svc._repo = repo
    svc._events = events
    svc._clock = clock
    svc._online_streak = {}
    svc._normalizer = normalizer_mod
    svc._shared_info = None
    return svc


async def test_ingest_metrics_emits_world_day_milestone(tmp_path):
    repo, events, clock, db = await _wire(tmp_path)
    try:
        svc = _make_svc(repo, events, clock)
        await svc.ingest_metrics(_world(), _resp({
            "ServerFps": 60, "ServerFrameTime": 16, "CurrentPlayerNum": 3,
            "MaxPlayerNum": 32, "Uptime": 1, "BaseCampNum": 0, "Days": 105,
        }))
        rows = await repo.list_events("s1:guid:0")
        types = {r.event_type for r in rows}
        assert EventType.WORLD_DAY_MILESTONE in types
    finally:
        await db.close()


async def test_ingest_metrics_online_record_needs_two_snapshots(tmp_path):
    repo, events, clock, db = await _wire(tmp_path)
    try:
        svc = _make_svc(repo, events, clock)
        world = _world()

        def snap(online):
            return {
                "ServerFps": 60, "ServerFrameTime": 16,
                "CurrentPlayerNum": online, "MaxPlayerNum": 32,
                "Uptime": 1, "BaseCampNum": 0, "Days": 1,
            }

        await svc.ingest_metrics(world, _resp(snap(8)))   # first sighting
        assert not [
            r for r in await repo.list_events("s1:guid:0")
            if r.event_type == EventType.ONLINE_RECORD
        ]
        await svc.ingest_metrics(world, _resp(snap(8)))   # sustained → confirm
        recs = [
            r for r in await repo.list_events("s1:guid:0")
            if r.event_type == EventType.ONLINE_RECORD
        ]
        assert len(recs) == 1
        assert recs[0].payload == {"value": 8}
    finally:
        await db.close()


def _resp(raw):
    # Wraps a RAW metrics dict; ingest_metrics normalizes it internally
    # (Phase 2 normalizes inside ingest_metrics). RestResponse-shaped stub.
    class _R:
        ok = True
        status = 200
        data = raw
        duration_ms = 1
        payload_bytes = 0
        error = None

    return _R()
