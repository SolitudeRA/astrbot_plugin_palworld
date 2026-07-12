from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..adapters.sqlite_repository import Repository
from ..config import AppConfig
from ..domain.enums import EventType
from ..domain.models import World
from ..infrastructure.clock import Clock

_ACTIVE_SECONDS = 600  # spec §12: 活跃日 >= 10 分钟


def day_bounds(
    cfg: AppConfig, world: World, now: int, day: str | None = None
) -> tuple[str, int, int]:
    """自然日 [start, end) 边界（秒）。tz：per-server timezone 优先，回退 world tz。
    用 timedelta(days=1) 而非 +86400，正确处理 DST 的 23/25 小时日。"""
    server_tz = ""
    for s in cfg.servers:
        if s.server_id == world.server_id:
            server_tz = s.timezone
            break
    tz = ZoneInfo(server_tz or cfg.world.timezone)
    if day is None:
        local = datetime.fromtimestamp(now, tz)
        day = local.strftime("%Y-%m-%d")
    y, m, d = (int(x) for x in day.split("-"))
    start_local = datetime(y, m, d, 0, 0, 0, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return day, int(start_local.timestamp()), int(end_local.timestamp())


@dataclass(slots=True)
class LevelEvent:
    player_name: str
    old_level: int
    new_level: int

    def __str__(self) -> str:
        # player_name holds the HMAC subject_key; display names are not
        # resolvable here in v0.1, so show a truncated hash (privacy-consistent).
        return f"{self.player_name[:8]}… Lv{self.old_level}→Lv{self.new_level}"


@dataclass(slots=True)
class BaseEvent:
    base_key: str
    kind: str          # "new" / "vanished" / "worker_delta"
    detail: str

    def __str__(self) -> str:
        return f"{self.detail}"


@dataclass(slots=True)
class DailyReport:
    day: str
    world_day_start: int
    world_day_end: int
    active_players: int
    peak_online: int
    total_online_seconds: int
    level_events: list[LevelEvent]
    base_events: list[BaseEvent]
    records: list[str]
    summary: str
    is_empty: bool


class ReportService:
    def __init__(self, repo: Repository, cfg: AppConfig, clock: Clock) -> None:
        self._repo = repo
        self._cfg = cfg
        self._clock = clock

    def _day_bounds(self, world: World, day: str | None) -> tuple[str, int, int]:
        return day_bounds(self._cfg, world, self._clock.now(), day)

    async def daily(self, world: World, day: str | None = None) -> DailyReport:
        day, start, end = self._day_bounds(world, day)
        events = [
            e
            for e in await self._repo.list_events(
                world.world_id, since=start, limit=1000
            )
            if e.occurred_at < end
        ]
        peak = await self._repo.peak_online(world.world_id, since=start)

        milestones = [e for e in events if e.event_type == EventType.WORLD_DAY_MILESTONE]
        records_ev = [e for e in events if e.event_type == EventType.ONLINE_RECORD]
        new_players = [e for e in events if e.event_type == EventType.NEW_PLAYER]
        new_guilds = [e for e in events if e.event_type == EventType.NEW_GUILD]
        new_bases = [e for e in events if e.event_type == EventType.NEW_BASE]
        level_ups = [e for e in events if e.event_type == EventType.PLAYER_LEVEL_UP]
        vanished = [e for e in events if e.event_type == EventType.BASE_VANISHED]
        worker_delta = [e for e in events if e.event_type == EventType.WORKER_DELTA]

        level_events = [
            LevelEvent(
                player_name=e.subject_key,
                old_level=int(e.payload.get("old", 0)),
                new_level=int(e.payload.get("new", 0)),
            )
            for e in level_ups
        ]
        base_events: list[BaseEvent] = []
        for e in new_bases:
            base_events.append(BaseEvent(e.subject_key, "new", "新据点出现"))
        for e in vanished:
            base_events.append(BaseEvent(e.subject_key, "vanished", "据点消失"))
        for e in worker_delta:
            base_events.append(BaseEvent(e.subject_key, "worker_delta", "工作帕鲁变化"))

        # 排序: 里程碑 → 新纪录 → 新玩家/公会/据点 → 成长 → 变化 → 编辑部总结
        records: list[str] = []
        for e in milestones:
            records.append(f"世界推进至第 {e.payload.get('milestone')} 天")
        for e in records_ev:
            records.append(f"同时在线新纪录 {e.payload.get('value')} 人")
        for e in new_players:
            records.append(f"新玩家 {e.subject_key} 加入")
        for e in new_guilds:
            records.append(f"新公会 {e.subject_key} 出现")
        for e in new_bases:
            records.append(f"新据点 {e.subject_key} 出现")

        # v0.1 近似：与当日窗口交叠的会话，其 observed_seconds 全额计入当日，
        # 跨午夜会话不做按日切分。
        sessions = await self._repo.sessions_in_day(world.world_id, start, end)
        total_online_seconds = sum(s.observed_seconds for s in sessions)
        # spec §12: 活跃日 = 某自然日累计观察在线 ≥ 10 分钟 → 按玩家累计并去重，
        # 同一 player_key 多段会话合计达标才算 1 名活跃玩家。
        per_player: dict[str, int] = {}
        for s in sessions:
            per_player[s.player_key] = per_player.get(s.player_key, 0) + s.observed_seconds
        active_players = sum(
            1 for total in per_player.values() if total >= _ACTIVE_SECONDS
        )

        has_content = bool(events) or active_players > 0
        if has_content:
            summary = self._summary(
                milestones, records_ev, new_players, new_guilds,
                new_bases, level_events, base_events, active_players,
            )
        else:
            summary = "平静的一天"

        return DailyReport(
            day=day,
            world_day_start=start,
            world_day_end=end,
            active_players=active_players,
            peak_online=peak,
            total_online_seconds=total_online_seconds,
            level_events=level_events,
            base_events=base_events,
            records=records,
            summary=summary,
            is_empty=not has_content,
        )

    def _summary(
        self, milestones, records_ev, new_players, new_guilds, new_bases,
        level_events, base_events, active_players,
    ) -> str:
        parts: list[str] = []
        if milestones:
            parts.append(f"世界跨越 {len(milestones)} 个里程碑")
        if records_ev:
            parts.append("刷新在线纪录")
        if new_players:
            parts.append(f"{len(new_players)} 名新玩家加入")
        if level_events:
            parts.append(f"{len(level_events)} 次成长")
        if base_events:
            parts.append(f"{len(base_events)} 处据点变化")
        if not parts and active_players:
            parts.append(f"{active_players} 名玩家在线活跃")
        return "，".join(parts) + "。" if parts else "平静的一天"
