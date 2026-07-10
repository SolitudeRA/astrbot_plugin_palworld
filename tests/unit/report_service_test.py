from pathlib import Path

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.application.event_service import EventService
from palchronicle.application.report_service import DailyReport, ReportService
from palchronicle.config import (
    AppConfig, BasesConfig, HistoryConfig, PollingConfig, PrivacyConfig,
    RoutingConfig, WorldConfig,
)
from palchronicle.domain.enums import AccessMode
from palchronicle.domain.models import World, WorldMetric
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.infrastructure.database import Database
from palchronicle.infrastructure.migrations import apply_migrations


def _cfg(tz: str = "Asia/Tokyo") -> AppConfig:
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig(timezone=tz, locale="zh-CN", fps_smooth=50,
                          fps_moderate=35, fps_laggy=20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig("balanced", False, False, 60, 120, 900),
        history=HistoryConfig(7, 90, 365, 180),
    )


def _world() -> World:
    return World(
        world_id="s1:guid:0", server_id="s1", worldguid="guid", epoch=0,
        server_name="Srv", version="1.0", first_seen_at=0,
        last_seen_at=0, current_day=105,
    )


# 2026-07-10 00:00 Asia/Tokyo (UTC+9) == 2026-07-09 15:00 UTC
DAY_START_UTC = 1783609200
NOON = DAY_START_UTC + 12 * 3600


async def _make(tmp_path: Path, tz="Asia/Tokyo"):
    db = Database(tmp_path / "rep.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=NOON)
    repo = Repository(db, clock)
    events = EventService(repo, clock)
    return ReportService(repo, _cfg(tz), clock), repo, events, clock, db


async def test_daily_splits_events_and_orders(tmp_path):
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        clock.set(NOON)
        await events.world_day(w, 105)                # WORLD_DAY_MILESTONE(100)
        await repo.insert_metric(WorldMetric(
            world_id=w.world_id, observed_at=NOON, fps=60.0, frame_time=16.0,
            online_players=6, world_day=105, basecamp_count=1))
        await events.online_record(w, value=6, confirmed=True)  # ONLINE_RECORD
        await events.new_player(w, "pk1")
        await events.level_up(w, "pk1", old=9, new=12)
        rep = await report.daily(w, day="2026-07-10")
        assert isinstance(rep, DailyReport)
        assert rep.day == "2026-07-10"
        assert rep.world_day_start == DAY_START_UTC
        assert rep.world_day_end == DAY_START_UTC + 86400
        assert rep.peak_online == 6
        assert [le.new_level for le in rep.level_events] == [12]
        assert rep.level_events[0].old_level == 9
        # milestone + record present in records
        assert any("100" in r for r in rep.records)
        assert rep.is_empty is False
        assert rep.summary  # non-empty editorial summary
    finally:
        await db.close()


async def test_daily_natural_day_boundary_excludes_prev_day(tmp_path):
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        # event one second BEFORE local midnight of 2026-07-10 → previous day
        clock.set(DAY_START_UTC - 1)
        await events.new_player(w, "pk_prev")
        # event inside the day
        clock.set(NOON)
        await events.new_player(w, "pk_in")
        rep = await report.daily(w, day="2026-07-10")
        new_player_keys = [
            r for r in rep.records if "pk_in" in r or "pk_prev" in r
        ]
        # pk_prev must NOT appear; only pk_in counted
        assert not any("pk_prev" in r for r in rep.records)
    finally:
        await db.close()


async def test_daily_empty_day_reports_calm(tmp_path):
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        rep = await report.daily(w, day="2026-07-10")
        assert rep.is_empty is True
        assert rep.summary == "平静的一天"
        assert rep.level_events == []
        assert rep.base_events == []
        assert rep.records == []
        assert rep.active_players == 0
        assert rep.peak_online == 0
        assert rep.total_online_seconds == 0
    finally:
        await db.close()


async def test_daily_none_day_uses_clock_local_date(tmp_path):
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        # clock at NOON of 2026-07-10 local (Asia/Tokyo) → day resolves to that date
        rep = await report.daily(w, day=None)
        assert rep.day == "2026-07-10"
        assert rep.world_day_start == DAY_START_UTC
    finally:
        await db.close()
