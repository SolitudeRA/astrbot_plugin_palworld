from pathlib import Path

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.base_service import BaseUpdate
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
from palworld_terminal.domain.enums import (
    AccessMode,
    Confidence,
    IdConfidence,
    LeaveReason,
    SessionStatus,
)
from palworld_terminal.domain.models import (
    PlayerIdentity,
    PlayerSession,
    World,
    WorldMetric,
)
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations
from palworld_terminal.presentation.event_wording import render_event


def _cfg(tz: str = "Asia/Tokyo", privacy_mode: str = "balanced") -> AppConfig:
    return AppConfig(
        servers=[], skipped=[],
        routing=RoutingConfig(access_mode=AccessMode.RESTRICTED, default_server=""),
        group_bindings=[],
        polling=PollingConfig(30, 30, 600, 1800, 120, 0.1, 6),
        world=WorldConfig(timezone=tz, locale="zh-CN", fps_smooth=50,
                          fps_moderate=35, fps_laggy=20),
        bases=BasesConfig(True, 5000, 0.2, 3, 2000, 0.5),
        privacy=PrivacyConfig(privacy_mode, False, False, 60, 120, 900),
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


async def _make(tmp_path: Path, tz="Asia/Tokyo", privacy_mode="balanced"):
    db = Database(tmp_path / "rep.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(start=NOON)
    repo = Repository(db, clock)
    events = EventService(repo, clock)
    return ReportService(repo, _cfg(tz, privacy_mode), clock), repo, events, clock, db


def _ident(world_id: str, key: str, name: str) -> PlayerIdentity:
    return PlayerIdentity(key, world_id, name, NOON, NOON, 30, None, IdConfidence.HIGH)


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


async def test_daily_splits_events_and_orders(tmp_path):
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        clock.set(NOON)
        # 玩家身份供名字解析（成长节显示名而非截断哈希，spec §4.5/§6#7）。
        await repo.upsert_player(
            PlayerIdentity("pk1", w.world_id, "Neo", NOON, NOON, 12, None,
                           IdConfidence.HIGH))
        await events.world_day(w, 105)                # WORLD_DAY_MILESTONE(100)
        await repo.insert_metric(WorldMetric(
            world_id=w.world_id, observed_at=NOON, fps=60.0, frame_time=16.0,
            online_players=6, world_day=105, basecamp_count=1))
        await events.online_record(w, value=8, confirmed=True)  # ONLINE_RECORD(8>6)
        await events.new_player(w, "pk1")
        await events.level_up(w, "pk1", old=9, new=12)
        rep = await report.daily(w, day="2026-07-10")
        assert isinstance(rep, DailyReport)
        assert rep.day == "2026-07-10"
        # epoch bug 修（spec §6#1）：世界天数取窗口内 metrics 首末 world_day，非 epoch 秒。
        assert rep.world_day_start == 105
        assert rep.world_day_end == 105
        assert rep.peak_online == 6
        # 成长节名字解析 + 措辞走 render_event 渲染（application 只产 EventView，
        # 措辞在 presentation 层，spec §4.4/§4.5）。
        assert [render_event(v) for v in rep.growth] == ["Neo 升级 Lv9→Lv12"]
        # 今日纪录收里程碑 + 在线纪录 + 新玩家（三节分派）。
        assert any("100" in render_event(r) for r in rep.records)
        assert "在线人数新纪录 8 人" in [render_event(v) for v in rep.records]
        assert "新玩家 Neo 加入世界" in [render_event(v) for v in rep.records]
        assert rep.is_empty is False
        assert rep.summary  # non-empty editorial summary
    finally:
        await db.close()


async def test_daily_natural_day_boundary_excludes_prev_day(tmp_path):
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        await repo.upsert_player(_ident(w.world_id, "pk_prev", "PrevGuy"))
        await repo.upsert_player(_ident(w.world_id, "pk_in", "InGuy"))
        # event one second BEFORE local midnight of 2026-07-10 → previous day
        clock.set(DAY_START_UTC - 1)
        await events.new_player(w, "pk_prev")
        # event inside the day
        clock.set(NOON)
        await events.new_player(w, "pk_in")
        rep = await report.daily(w, day="2026-07-10")
        # 仅窗口内 pk_in 计入；pk_prev（含其名字）必须缺席。
        assert any("InGuy" in render_event(r) for r in rep.records)
        assert not any("PrevGuy" in render_event(r) for r in rep.records)
        # 名字解析落点：绝不回落内部 key。
        assert not any("pk_prev" in render_event(r) for r in rep.records)
    finally:
        await db.close()


async def test_daily_empty_day_reports_calm(tmp_path):
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        rep = await report.daily(w, day="2026-07-10")
        assert rep.is_empty is True
        assert rep.summary == "平静的一天"
        assert rep.growth == []
        assert rep.base_changes == []
        assert rep.records == []
        assert rep.active_players == 0
        assert rep.peak_online == 0
        assert rep.total_online_seconds == 0
    finally:
        await db.close()


async def test_daily_three_section_dispatch_and_dedup(tmp_path):
    # 今日纪录只收里程碑/在线纪录/新玩家/新公会；据点类全归据点变化节（去重）。
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        clock.set(NOON)
        await repo.upsert_player(
            PlayerIdentity("pk1", w.world_id, "Neo", NOON, NOON, 22, None,
                           IdConfidence.HIGH))
        await repo.insert_metric(WorldMetric(
            world_id=w.world_id, observed_at=NOON, fps=60.0, frame_time=16.0,
            online_players=6, world_day=105, basecamp_count=1))
        await events.world_day(w, 105)                           # milestone
        await events.online_record(w, value=8, confirmed=True)   # record
        await events.new_player(w, "pk1")                        # new player
        await events.new_guild(w, "gk1")                         # new guild
        await events.level_up(w, "pk1", old=21, new=22)          # growth
        await events.base_events(w, [_bu(is_new=True)])          # NEW_BASE
        await events.base_events(
            w, [_bu(prev_worker_count=5, worker_count=12)])      # WORKER_DELTA
        rep = await report.daily(w, day="2026-07-10")
        # 今日纪录
        assert "世界迎来第 100 天" in [render_event(v) for v in rep.records]
        assert "在线人数新纪录 8 人" in [render_event(v) for v in rep.records]
        assert "新玩家 Neo 加入世界" in [render_event(v) for v in rep.records]
        assert any(render_event(r).startswith("新公会") for r in rep.records)
        # 去重：据点类绝不进今日纪录
        assert not any("新据点" in render_event(r) for r in rep.records)
        assert not any("工作帕鲁" in render_event(r) for r in rep.records)
        # 据点变化节收全部据点类
        assert any("新据点" in render_event(r) for r in rep.base_changes)
        assert any("工作帕鲁" in render_event(r) for r in rep.base_changes)
        # 成长节
        assert [render_event(v) for v in rep.growth] == ["Neo 升级 Lv21→Lv22"]
        # 末行编辑部总结主分支（spec §4.5）：经 _summary 三计数拼装（1 新玩家 / 1 成长 /
        # 2 据点变化），锚定 golden 手造串之外的真实渲染路径，防 _summary 主分支回归。
        assert rep.summary == "今天：1 名新玩家加入，1 次成长，2 处据点变化。"
    finally:
        await db.close()


async def test_daily_strict_omits_growth_and_base_changes(tmp_path):
    # Finding 2：strict 下今日纪录只留 world 主体（里程碑/在线纪录）；玩家成长（player 主体）
    # 与据点变化（base 主体）整节缺席——与 events 同一 world-only 规则。聚合头行（峰值）照常。
    report, repo, events, clock, db = await _make(tmp_path, privacy_mode="strict")
    try:
        w = _world()
        clock.set(NOON)
        await repo.upsert_player(
            PlayerIdentity("pk1", w.world_id, "Neo", NOON, NOON, 22, None,
                           IdConfidence.HIGH))
        await repo.insert_metric(WorldMetric(
            world_id=w.world_id, observed_at=NOON, fps=60.0, frame_time=16.0,
            online_players=6, world_day=105, basecamp_count=1))
        await events.world_day(w, 105)                          # milestone (world)
        await events.online_record(w, value=8, confirmed=True)  # record (world)
        await events.new_player(w, "pk1")                       # new player (player)
        await events.level_up(w, "pk1", old=21, new=22)         # growth (player)
        await events.new_guild(w, "gk1")                        # new guild (guild)
        await events.base_events(w, [_bu(is_new=True)])         # NEW_BASE (base)
        rep = await report.daily(w, day="2026-07-10")
        # 今日纪录仅 world 主体：里程碑 + 在线纪录；新玩家/新公会（player/guild）缺席。
        assert any("100" in render_event(r) for r in rep.records)
        assert "在线人数新纪录 8 人" in [render_event(v) for v in rep.records]
        assert not any("新玩家" in render_event(r) for r in rep.records)
        assert not any("新公会" in render_event(r) for r in rep.records)
        assert not any("Neo" in render_event(r) for r in rep.records)
        # 玩家成长 / 据点变化整节缺席。
        assert rep.growth == []
        assert rep.base_changes == []
        # 聚合头行照常（peak 走 metric，非事件面）。
        assert rep.peak_online == 6
        assert rep.is_empty is False
    finally:
        await db.close()


async def test_daily_strict_empty_when_only_individual_events(tmp_path):
    # strict 下若仅有 player/base 个体事件且无活跃会话 → 事件全被裁、无聚合活动
    # → 平静的一天（且 format_today 空态不崩）。
    report, repo, events, clock, db = await _make(tmp_path, privacy_mode="strict")
    try:
        w = _world()
        clock.set(NOON)
        await repo.upsert_player(
            PlayerIdentity("pk1", w.world_id, "Neo", NOON, NOON, 22, None,
                           IdConfidence.HIGH))
        await events.new_player(w, "pk1")
        await events.level_up(w, "pk1", old=21, new=22)
        rep = await report.daily(w, day="2026-07-10")
        assert rep.records == []
        assert rep.growth == []
        assert rep.base_changes == []
        assert rep.is_empty is True
        assert rep.summary == "平静的一天"
    finally:
        await db.close()


async def test_daily_hidden_player_skipped(tmp_path):
    # 隐藏玩家事件整条跳过（与 events 名字级收敛同哲学，不泄漏名号，spec §4.5）。
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        clock.set(NOON)
        await repo.upsert_player(_ident(w.world_id, "pk_hidden", "Ghost"))
        await repo.set_hidden(w.world_id, "pk_hidden", "self")
        await events.new_player(w, "pk_hidden")
        await events.level_up(w, "pk_hidden", old=29, new=30)
        rep = await report.daily(w, day="2026-07-10")
        assert not any("Ghost" in render_event(r) for r in rep.records)
        assert rep.growth == []
        assert not any("pk_hidden" in render_event(r) for r in rep.records)
    finally:
        await db.close()


async def test_daily_world_day_from_window_metrics(tmp_path):
    # epoch bug 修（spec §6#1）：世界天数取窗口内 metrics 首末 world_day。
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        await repo.insert_metric(WorldMetric(
            world_id=w.world_id, observed_at=DAY_START_UTC + 3600, fps=60.0,
            frame_time=16.0, online_players=1, world_day=42, basecamp_count=1))
        await repo.insert_metric(WorldMetric(
            world_id=w.world_id, observed_at=NOON, fps=60.0, frame_time=16.0,
            online_players=1, world_day=45, basecamp_count=1))
        rep = await report.daily(w, day="2026-07-10")
        assert rep.world_day_start == 42
        assert rep.world_day_end == 45
        # 绝不再直出 epoch 秒（旧 bug 会渲染「第 1752624000 天」）。
        assert rep.world_day_start < 1000
    finally:
        await db.close()


async def test_daily_world_day_fallback_current_day_when_no_metrics(tmp_path):
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()  # current_day=105
        rep = await report.daily(w, day="2026-07-10")
        assert rep.world_day_start == 105
        assert rep.world_day_end == 105
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
        # 窗口无 metric 采样 → 世界天数回退 world.current_day（epoch 修后不再直出秒）。
        assert rep.world_day_start == 105
    finally:
        await db.close()


async def test_daily_paginates_beyond_event_page(tmp_path, monkeypatch):
    # 窗口内事件数越过单页上限时分页拉全,日报计数不再被 DESC+LIMIT 截断
    from palworld_terminal.application import report_service as rs
    monkeypatch.setattr(rs, "_EVENT_PAGE", 2)
    report, repo, events, clock, db = await _make(tmp_path)
    try:
        w = _world()
        for i in range(5):
            await repo.upsert_player(_ident(w.world_id, f"pk{i}", f"Name{i}"))
            clock.set(NOON + i)
            await events.new_player(w, f"pk{i}")
        rep = await report.daily(w, day="2026-07-10")
        for i in range(5):
            # 名字解析后展示显示名（非哈希）；分页拉全五条一个不落。
            assert any(f"Name{i}" in render_event(r) for r in rep.records), f"Name{i} 被截断丢失"
    finally:
        await db.close()
