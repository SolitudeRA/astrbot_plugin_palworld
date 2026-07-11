from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo

from ..adapters.sqlite_repository import Repository
from ..config import AppConfig
from ..domain.models import Base, BaseObservation, World
from ..infrastructure.cache import TTLCache
from ..infrastructure.clock import Clock
from ..presentation.dtos import (
    BaseDetailDTO,
    BaseDTO,
    EventDTO,
    GuildDetailDTO,
    GuildDTO,
    OnlineDTO,
    OnlinePlayerRow,
    RuleRow,
    RulesDTO,
    StatusDTO,
    WildTopRow,
    WorldSummaryDTO,
)

_STATUS_TTL = 15
_ONLINE_TTL = 15


class QueryService:
    _GUILDS_TTL = 90
    _BASES_TTL = 90
    _EVENTS_TTL = 15

    def __init__(
        self, repo: Repository, cache: TTLCache, cfg: AppConfig, meta, clock: Clock,
        settings_cache, world_cache=None, report=None,
    ) -> None:
        self._repo = repo
        self._cache = cache
        self._cfg = cfg
        self._meta = meta
        self._clock = clock
        self._settings_cache = settings_cache
        self._world_cache = world_cache if world_cache is not None else {}
        self._report = report

    def _smoothness_label(self, fps: float) -> str:
        w = self._cfg.world
        if fps >= w.fps_smooth:
            return "流畅"
        if fps >= w.fps_moderate:
            return "一般"
        if fps >= w.fps_laggy:
            return "卡顿"
        return "严重卡顿"

    async def _online_rows(self, world: World) -> list[OnlinePlayerRow]:
        sessions = await self._repo.list_open_sessions(world.world_id)
        rows: list[OnlinePlayerRow] = []
        for s in sessions:
            obs = await self._repo.latest_observation(world.world_id, s.player_key)
            if obs is None:
                continue
            # obs.name is always "" by design (observations are name-free);
            # resolve the display name from players.latest_name.
            ident = await self._repo.get_player(world.world_id, s.player_key)
            rows.append(
                OnlinePlayerRow(
                    name=ident.latest_name if ident is not None else "",
                    level=obs.level, ping_bucket=obs.ping_bucket,
                    online_seconds=s.observed_seconds,
                )
            )
        rows.sort(key=lambda r: (-r.level, r.name))
        return rows

    async def status(self, world: World) -> StatusDTO:
        key = f"status:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        metric = await self._repo.latest_metric(world.world_id)
        rows = await self._online_rows(world)
        day_start = self._clock.now() - 86400
        peak_today = await self._repo.peak_online(world.world_id, since=day_start)
        degraded = metric is None

        dto = StatusDTO(
            server_name=world.server_name,
            world_name=world.server_name,
            world_day=metric.world_day if metric else world.current_day,
            online=metric.online_players if metric else 0,
            max_players=metric.max_players if metric else 0,
            basecamp_count=metric.basecamp_count if metric else 0,
            fps=metric.fps if metric else 0.0,
            frame_time=metric.frame_time if metric else 0.0,
            smoothness_label=self._smoothness_label(metric.fps if metric else 0.0),
            players=[(r.name, r.level, r.ping_bucket.value) for r in rows],
            peak_online_today=peak_today,
            updated_at=metric.observed_at if metric else world.last_seen_at,
            degraded=degraded,
            last_ok=metric.observed_at if metric else None,
        )
        self._cache.set(key, dto, _STATUS_TTL)
        return dto

    async def online(self, world: World) -> OnlineDTO:
        key = f"online:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        rows = await self._online_rows(world)
        dto = OnlineDTO(rows=rows, updated_at=self._clock.now(), degraded=False)
        self._cache.set(key, dto, _ONLINE_TTL)
        return dto

    def _server_day_start(self, world: World) -> int:
        tz_name = self._cfg.world.timezone or "UTC"
        tz: tzinfo
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = UTC
        now = datetime.fromtimestamp(self._clock.now(), tz)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(midnight.timestamp())

    @staticmethod
    def _activity_score(o: BaseObservation) -> float:
        active_ratio = o.active_count / max(o.worker_count, 1)
        total = sum(o.action_distribution.values()) or 1
        known = sum(v for k, v in o.action_distribution.items() if k != "unknown")
        known_ratio = known / total
        return round(100 * (0.75 * active_ratio + 0.25 * known_ratio), 2)

    @staticmethod
    def _health_score(o: BaseObservation) -> float:
        return round(100 * (0.8 * o.average_hp_ratio + 0.2 * 1.0), 2)

    async def guilds(self, world: World) -> list[GuildDTO]:
        key = f"guilds:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        guilds = await self._repo.list_guilds(world.world_id)
        dtos = [
            GuildDTO(
                name=g.latest_name, observed_members=g.observed_member_count,
                palbox=g.palbox_count, base_pals=g.base_pal_count, active_7d=0,
            )
            for g in guilds
        ]
        self._cache.set(key, dtos, self._GUILDS_TTL)
        return dtos

    async def guild(self, world: World, name: str) -> GuildDetailDTO | None:
        key = f"guild:{world.world_id}:{name}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        guilds = await self._repo.list_guilds(world.world_id)
        target = None
        for g in guilds:
            if g.latest_name == name:
                target = g
                break
        if target is None:
            return None  # not found: do not cache None
        # active_today/active_week/average_level are v0.1 degradation
        # placeholders, consistent with GuildDTO.active_7d=0.
        dto = GuildDetailDTO(
            name=target.latest_name,
            first_seen_at=target.first_seen_at,
            last_seen_at=target.last_seen_at,
            observed_members=target.observed_member_count,
            active_today=0,
            active_week=0,
            palbox=target.palbox_count,
            base_pals=target.base_pal_count,
            average_level=0.0,
            base_event_lines=[],
        )
        self._cache.set(key, dto, self._GUILDS_TTL)
        return dto

    async def _bases_indexed(self, world: World) -> list[tuple[int, Base]]:
        bases = await self._repo.list_bases(world.world_id)
        return list(enumerate(bases, start=1))

    async def bases(self, world: World) -> list[BaseDTO]:
        key = f"bases:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        # 键放宽为 str | None：Base.guild_key 可能为 None，get(None) 返回 None 即可
        guild_names: dict[str | None, str] = {
            g.guild_key: g.latest_name for g in await self._repo.list_guilds(world.world_id)
        }
        dtos = [
            BaseDTO(
                index=i, display_name=b.display_name or f"BASE-{i}",
                guild_name=guild_names.get(b.guild_key), confidence=b.confidence,
                worker_count=0,
            )
            for i, b in await self._bases_indexed(world)
        ]
        self._cache.set(key, dtos, self._BASES_TTL)
        return dtos

    async def base(self, world: World, key_or_index: str) -> BaseDetailDTO | None:
        indexed = await self._bases_indexed(world)
        # 键放宽为 str | None：Base.guild_key 可能为 None，get(None) 返回 None 即可
        guild_names: dict[str | None, str] = {
            g.guild_key: g.latest_name for g in await self._repo.list_guilds(world.world_id)
        }
        target = None
        token = key_or_index.strip()
        if token.startswith("#"):
            try:
                idx = int(token[1:])
            except ValueError:
                return None
            for i, b in indexed:
                if i == idx:
                    target = b
                    break
        else:
            for _, b in indexed:
                if (b.display_name and b.display_name == token) or guild_names.get(b.guild_key) == token:
                    target = b
                    break
        if target is None:
            return None
        obs = await self._repo.latest_base_observation(world.world_id, target.base_key)
        worker = obs.worker_count if obs else 0
        active = obs.active_count if obs else 0
        avg_level = obs.average_level if obs else 0.0
        avg_hp = obs.average_hp_ratio if obs else 0.0
        dist = obs.action_distribution if obs else {}
        return BaseDetailDTO(
            display_name=target.display_name or "BASE",
            guild_name=guild_names.get(target.guild_key),
            confidence=target.confidence, palbox_count=1,
            worker_count=worker, active_count=active, average_level=avg_level,
            average_hp_ratio=avg_hp, action_distribution=dist,
            activity_score=self._activity_score(obs) if obs else 0.0,
            health_score=self._health_score(obs) if obs else 0.0,
        )

    async def events(self, world: World, today_only: bool) -> list[EventDTO]:
        key = f"events:{world.world_id}:{int(today_only)}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        since = self._server_day_start(world) if today_only else None
        events = await self._repo.list_events(world.world_id, since=since, limit=20)
        dtos = [
            EventDTO(
                occurred_at=e.occurred_at, event_type=e.event_type.value,
                summary=_event_summary(e),
            )
            for e in events
        ]
        self._cache.set(key, dtos, self._EVENTS_TTL)
        return dtos

    async def rules(self, world: World) -> RulesDTO:
        key = f"rules:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        raw = self._settings_cache.get(world.server_id, {})
        rows: list[RuleRow] = []
        for field, value in raw.items():
            label, unit = self._meta.setting_label(field)
            rows.append(RuleRow(label=label, value=f"{value}{unit}"))
        advanced_note = None
        if self._cfg.privacy.mode == "advanced":
            advanced_note = "advanced 隐私模式暂按 balanced 生效。"
        elif self._cfg.privacy.mode == "strict":
            advanced_note = "strict 隐私模式下据点模块停用。"
        dto = RulesDTO(rows=rows, updated_at=self._clock.now(), advanced_note=advanced_note)
        self._cache.set(key, dto, 1800)
        return dto

    async def world_summary(self, world: World) -> WorldSummaryDTO:
        key = f"world:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        gd = self._world_cache.get(world.server_id)
        metric = await self._repo.latest_metric(world.world_id)
        counts = {u: 0 for u in ("Player", "OtomoPal", "BaseCampPal", "WildPal", "NPC")}
        wild_counter: dict[str, int] = {}
        palbox = 0
        guild_ids: set = set()
        if gd is not None:
            for c in gd.characters:
                counts[c.unit_type.value] = counts.get(c.unit_type.value, 0) + 1
                if c.unit_type.value == "WildPal" and c.pal_class:
                    name = self._meta.pal_name(c.pal_class) if self._meta else c.pal_class
                    wild_counter[name] = wild_counter.get(name, 0) + 1
                if c.guild_id:
                    guild_ids.add(c.guild_id)
            palbox = len(gd.palboxes)
        wild_top = [
            WildTopRow(name=n, count=c)
            for n, c in sorted(wild_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        ]
        dto = WorldSummaryDTO(
            world_day=metric.world_day if metric else world.current_day,
            online=metric.online_players if metric else counts["Player"],
            players=counts["Player"], otomo=counts["OtomoPal"], base_pal=counts["BaseCampPal"],
            wild=counts["WildPal"], npc=counts["NPC"], palbox=palbox, guilds=len(guild_ids),
            fps=gd.fps if gd else (metric.fps if metric else 0.0),
            average_fps=gd.average_fps if gd else (metric.fps if metric else 0.0),
            wild_top=wild_top,
        )
        self._cache.set(key, dto, self._BASES_TTL)
        return dto

    async def today(self, world: World):
        key = f"today:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        report = await self._report.daily(world)
        self._cache.set(key, report, 60)
        return report


def _event_summary(e) -> str:
    from ..domain.enums import EventType as _ET
    p = e.payload or {}
    if e.event_type is _ET.PLAYER_LEVEL_UP:
        return f"玩家升级 Lv{p.get('old', '?')}→Lv{p.get('new', '?')}"
    if e.event_type is _ET.NEW_PLAYER:
        return "新玩家加入世界"
    if e.event_type is _ET.NEW_GUILD:
        return f"新公会出现：{p.get('name', e.subject_key)}"
    if e.event_type is _ET.NEW_BASE:
        return f"新据点确认：{p.get('name', e.subject_key)}"
    if e.event_type is _ET.BASE_VANISHED:
        return "据点已连续多次未被观察到"
    if e.event_type is _ET.WORKER_DELTA:
        return f"据点工作帕鲁数量变化：{p.get('prev', '?')}→{p.get('cur', '?')}"
    if e.event_type is _ET.WORLD_DAY_MILESTONE:
        return f"世界推进至第 {p.get('milestone', '?')} 天"
    if e.event_type is _ET.ONLINE_RECORD:
        return f"在线人数刷新纪录：{p.get('value', '?')} 人"
    return e.event_type.value
