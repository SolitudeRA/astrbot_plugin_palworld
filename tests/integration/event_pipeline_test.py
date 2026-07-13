from pathlib import Path

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.base_service import BaseUpdate
from palworld_terminal.application.event_service import EventService
from palworld_terminal.application.report_service import ReportService
from palworld_terminal.config import (
    AppConfig,
    BasesConfig,
    HistoryConfig,
    PollingConfig,
    PrivacyConfig,
    RoutingConfig,
    WorldConfig,
)
from palworld_terminal.domain.enums import AccessMode, Confidence, EventType
from palworld_terminal.domain.models import World, WorldMetric
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations

DAY_START_UTC = 1783609200          # 2026-07-10 00:00 Asia/Tokyo
NOON = DAY_START_UTC + 12 * 3600


def _cfg() -> AppConfig:
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig("Asia/Tokyo", "zh-CN", 50, 35, 20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world() -> World:
    return World("s1:guid:0", "s1", "guid", 0, "Srv", "1.0", 0, 0, 105)


def _bu(**kw) -> BaseUpdate:
    d = dict(
        base_key="s1:guid:0|BASE|pb1", world_id="s1:guid:0", palbox_key="pb1",
        guild_key="gk1", confidence=Confidence.HIGH, worker_count=6,
        active_count=4, average_level=10.0, average_hp_ratio=0.9,
        action_distribution={"working": 4}, is_new=False, is_vanished=False,
        prev_worker_count=None,
    )
    d.update(kw)
    return BaseUpdate(**d)


async def test_all_event_types_and_dedup_and_report(tmp_path: Path):
    db = Database(tmp_path / "pipe.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=NOON)
    repo = Repository(db, clock)
    events = EventService(repo, clock)
    report = ReportService(repo, _cfg(), clock)
    w = _world()
    try:
        # metrics for peak baseline
        await repo.insert_metric(WorldMetric(
            "s1:guid:0", NOON, 60.0, 16.0, 4, 105, 1))

        await events.world_day(w, 105)                          # milestone 100
        await events.online_record(w, value=7, confirmed=True)  # record
        await events.new_player(w, "pk1")
        await events.new_guild(w, "gk1")
        await events.level_up(w, "pk1", old=9, new=12)
        await events.base_events(w, [_bu(is_new=True)])         # NEW_BASE
        await events.base_events(w, [_bu(is_vanished=True)])    # BASE_VANISHED
        await events.base_events(
            w, [_bu(prev_worker_count=5, worker_count=9)])      # WORKER_DELTA

        # dedup: repeat everything → no new rows
        await events.world_day(w, 150)
        await events.new_player(w, "pk1")
        await events.level_up(w, "pk1", old=11, new=12)

        rows = await repo.list_events("s1:guid:0")
        got = {r.event_type for r in rows}
        assert got == {
            EventType.WORLD_DAY_MILESTONE, EventType.ONLINE_RECORD,
            EventType.NEW_PLAYER, EventType.NEW_GUILD,
            EventType.PLAYER_LEVEL_UP, EventType.NEW_BASE,
            EventType.BASE_VANISHED, EventType.WORKER_DELTA,
        }
        assert len(rows) == 8  # dedup held

        rep = await report.daily(w, day="2026-07-10")
        assert rep.is_empty is False
        assert len(rep.level_events) == 1
        assert len(rep.base_events) == 3
        assert any("100" in r for r in rep.records)
    finally:
        await db.close()
