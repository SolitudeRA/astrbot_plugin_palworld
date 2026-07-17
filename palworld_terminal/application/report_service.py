from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..adapters.sqlite_repository import Repository
from ..config import AppConfig
from ..domain.enums import EventType
from ..domain.models import World, WorldEvent
from ..infrastructure.clock import Clock
from ..presentation.event_wording import event_wording
from .name_resolver import (
    keep_world_subject_under_strict,
    load_excluded_keys,
    resolve_subjects,
)

_ACTIVE_SECONDS = 600  # spec §12: 活跃日 >= 10 分钟


_EVENT_PAGE = 1000  # 日报事件分页大小(测试可缩小以覆盖分页路径)


def server_timezone(cfg: AppConfig, world: World) -> str:
    """该世界所属服务器的时区名：per-server timezone 优先，回退 world 默认 tz。
    day_bounds（日窗口）与 events formatter（日分组/HH:MM）共用同一 tz 口径，
    确保「今天」判定跨两者一致。"""
    server_tz = ""
    for s in cfg.servers:
        if s.server_id == world.server_id:
            server_tz = s.timezone
            break
    return server_tz or cfg.world.timezone


def day_bounds(
    cfg: AppConfig, world: World, now: int, day: str | None = None
) -> tuple[str, int, int]:
    """自然日 [start, end) 边界（秒）。tz：per-server timezone 优先，回退 world tz。
    用 timedelta(days=1) 而非 +86400，正确处理 DST 的 23/25 小时日。"""
    tz = ZoneInfo(server_timezone(cfg, world))
    if day is None:
        local = datetime.fromtimestamp(now, tz)
        day = local.strftime("%Y-%m-%d")
    y, m, d = (int(x) for x in day.split("-"))
    start_local = datetime(y, m, d, 0, 0, 0, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return day, int(start_local.timestamp()), int(end_local.timestamp())


@dataclass(slots=True)
class DailyReport:
    """今日日报结构化 DTO（spec §4.5）。三节措辞均由 event_wording 单一真相源渲染成串
    （名字解析后，隐藏玩家已跳过）；formatter 只做版式。

    - records：今日纪录（里程碑/在线纪录/新玩家/新公会）。
    - growth：玩家成长（升级；显示名，隐藏玩家跳过）。
    - base_changes：据点变化（新据点/消失/工作帕鲁；gamedata 锁定期自然缺席）。
    - world_day_start/end：日窗口内 metrics 首末世界天数（epoch bug 修，§6#1）。
    """
    day: str
    world_day_start: int
    world_day_end: int
    active_players: int
    peak_online: int
    total_online_seconds: int
    records: list[str]
    growth: list[str]
    base_changes: list[str]
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
        # 分页拉全窗口事件:超活跃日事件数越过单页上限时,DESC+LIMIT 截断
        # 会丢当日最早的事件,导致日报计数偏低
        raw: list = []
        offset = 0
        while True:
            batch = await self._repo.list_events(
                world.world_id, since=start, limit=_EVENT_PAGE, offset=offset
            )
            raw.extend(batch)
            if len(batch) < _EVENT_PAGE:
                break
            offset += _EVENT_PAGE
        events = [e for e in raw if e.occurred_at < end]
        # strict 隐私：三节事件源只保留 world 主体（今日纪录留里程碑/在线纪录；玩家成长派生自
        # player 主体、据点变化派生自 base 主体 → strict 下两节整节缺席）——与 events 共用同一
        # world-only 规则单一真相源（keep_world_subject_under_strict），两路径口径不漂移。
        # 聚合头行（活跃玩家/峰值在线/累计在线）走 sessions/peak，非事件面，strict 下保留。
        events = keep_world_subject_under_strict(
            events, self._cfg.privacy.mode == "strict"
        )
        peak = await self._repo.peak_online(world.world_id, since=start)

        # 世界天数（epoch bug 修，spec §6#1）：日窗口内 metrics 首末 world_day，非窗口
        # epoch 秒；窗口无采样时回退 world.current_day（无从推断天数）。
        day_range = await self._repo.world_day_bounds(world.world_id, start, end)
        if day_range is None:
            world_day_start = world_day_end = world.current_day
        else:
            world_day_start, world_day_end = day_range

        # 主体名批量解析（隐藏玩家跳过 / 据点·公会查无回退），与 events(T6) 共用同一
        # resolver；措辞走 event_wording 单一真相源（spec §4.4/§4.5）。
        excluded = await load_excluded_keys(
            self._repo, world.world_id, self._cfg.players.exclude_names
        )
        names = await resolve_subjects(self._repo, world.world_id, events, excluded)

        def _wording(evs: list[WorldEvent]) -> list[str]:
            out: list[str] = []
            for e in evs:
                # 玩家主体查无/隐藏（resolver 缺席）整条跳过——与 events 名字级收敛
                # 同哲学，不泄漏隐藏玩家；据点/公会主体恒有名（含回退）。
                if e.subject_type == "player" and e.subject_key not in names:
                    continue
                out.append(event_wording(e, names.get(e.subject_key, "")))
            return out

        by_type: dict[EventType, list[WorldEvent]] = {}
        for e in events:
            by_type.setdefault(e.event_type, []).append(e)

        def _of(et: EventType) -> list[WorldEvent]:
            return by_type.get(et, [])

        # 三节分派 + 去重（spec §4.5）：今日纪录只收里程碑/在线纪录/新玩家/新公会；
        # 据点类（新据点/消失/工作帕鲁）全归据点变化节，绝不重复进今日纪录。
        new_player_lines = _wording(_of(EventType.NEW_PLAYER))
        records = (
            _wording(_of(EventType.WORLD_DAY_MILESTONE))
            + _wording(_of(EventType.ONLINE_RECORD))
            + new_player_lines
            + _wording(_of(EventType.NEW_GUILD))
        )
        growth = _wording(_of(EventType.PLAYER_LEVEL_UP))
        base_changes = (
            _wording(_of(EventType.NEW_BASE))
            + _wording(_of(EventType.BASE_VANISHED))
            + _wording(_of(EventType.WORKER_DELTA))
        )

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

        has_content = bool(records or growth or base_changes) or active_players > 0
        if has_content:
            summary = self._summary(
                len(new_player_lines), len(growth), len(base_changes), active_players,
            )
        else:
            summary = "平静的一天"

        return DailyReport(
            day=day,
            world_day_start=world_day_start,
            world_day_end=world_day_end,
            active_players=active_players,
            peak_online=peak,
            total_online_seconds=total_online_seconds,
            records=records,
            growth=growth,
            base_changes=base_changes,
            summary=summary,
            is_empty=not has_content,
        )

    def _summary(
        self, new_players: int, growth: int, base_changes: int, active_players: int,
    ) -> str:
        """末行编辑部总结（spec §4.5）：`今天：N 名新玩家加入，N 次成长，N 处据点变化。`
        无事件但有活跃玩家时回落在线活跃句；全空回「平静的一天」。"""
        parts: list[str] = []
        if new_players:
            parts.append(f"{new_players} 名新玩家加入")
        if growth:
            parts.append(f"{growth} 次成长")
        if base_changes:
            parts.append(f"{base_changes} 处据点变化")
        if not parts and active_players:
            parts.append(f"{active_players} 名玩家在线活跃")
        return "今天：" + "，".join(parts) + "。" if parts else "平静的一天"
