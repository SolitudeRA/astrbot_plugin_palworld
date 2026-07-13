from pathlib import Path

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.event_service import EventService
from palworld_terminal.application.report_service import DailyReport, ReportService
from palworld_terminal.config import (
    AppConfig,
    BasesConfig,
    HistoryConfig,
    PollingConfig,
    PrivacyConfig,
    RoutingConfig,
    WorldConfig,
)
from palworld_terminal.domain.enums import AccessMode, LeaveReason, SessionStatus
from palworld_terminal.domain.models import PlayerSession, World, WorldMetric
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations


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
        _new_player_keys = [
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


def _session(world_id, player_key, joined_at, observed_seconds, *, left_at=None):
    closed = left_at is not None
    return PlayerSession(
        id=None, world_id=world_id, player_key=player_key,
        joined_at=joined_at,
        last_confirmed_at=left_at if closed else joined_at + observed_seconds,
        left_at=left_at, observed_seconds=observed_seconds,
        status=SessionStatus.CLOSED if closed else SessionStatus.ACTIVE,
        leave_reason=LeaveReason.OBSERVED_TIMEOUT if closed else None,
    )


async def test_daily_total_online_and_active_players_dedup_by_player(tmp_path):
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        # pk_a: 两段各低于 600s 的会话，合计 700s ≥ 600 → 算 1 名活跃玩家
        await repo.insert_session(_session(
            w.world_id, "pk_a", DAY_START_UTC + 3600, 400,
            left_at=DAY_START_UTC + 4000))
        await repo.insert_session(_session(
            w.world_id, "pk_a", DAY_START_UTC + 7200, 300,
            left_at=DAY_START_UTC + 7500))
        # pk_b: 两段各 ≥ 600s 的会话 → 去重后仍只算 1 名活跃玩家
        await repo.insert_session(_session(
            w.world_id, "pk_b", DAY_START_UTC + 3600, 700,
            left_at=DAY_START_UTC + 4300))
        await repo.insert_session(_session(
            w.world_id, "pk_b", NOON, 700))  # 进行中（left_at NULL）也计入
        # pk_c: 合计 100s < 600 → 不活跃，但时长计入总观察在线
        await repo.insert_session(_session(
            w.world_id, "pk_c", NOON, 100,
            left_at=NOON + 100))
        # 前一日已关闭的会话不计入
        await repo.insert_session(_session(
            w.world_id, "pk_prev", DAY_START_UTC - 7200, 5000,
            left_at=DAY_START_UTC - 100))
        rep = await report.daily(w, day="2026-07-10")
        assert rep.total_online_seconds == 400 + 300 + 700 + 700 + 100
        assert rep.active_players == 2  # pk_a + pk_b（按玩家去重，非按会话）
        assert rep.is_empty is False
        assert "2 名玩家在线活跃" in rep.summary
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
