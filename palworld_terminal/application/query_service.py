from __future__ import annotations

from dataclasses import dataclass, field

from ..adapters.sqlite_repository import Repository
from ..config import AppConfig
from ..domain.models import Base, BaseObservation, World, WorldEvent
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
    RulesDTO,
    RuleSection,
    StatusDetailDTO,
    StatusDTO,
    WildTopRow,
    WorldSummaryDTO,
)
from ..presentation.event_wording import event_wording
from .name_resolver import load_excluded_keys as _load_excluded_keys
from .name_resolver import resolve_subjects
from .report_service import day_bounds

_STATUS_TTL = 15
_ONLINE_TTL = 15


def metric_stale(observed_at: int, now: int, metrics_seconds: int) -> bool:
    """指标新鲜度判定（spec §3 降级态）：距最后成功观测超阈值即视为陈旧。

    阈值 = metrics_seconds × 3 + 60s 余量（纯派生自 polling.metrics_seconds，不新增
    配置键、随轮询周期缩放）。status 降级双态与 link list 可达三态（T12）共用本判定。
    边界：距今恰为阈值不算陈旧，超阈值方为陈旧。
    """
    return now - observed_at > metrics_seconds * 3 + 60

# 状态卡 detail.rules 子集：输出键 → 设置快照字段。措辞经 meta.setting_display
# 统一渲染（与 /pal world rules 同源）；快照缺该字段则整键省略。
_STATUS_RULE_FIELDS = (
    ("difficulty", "Difficulty"),
    ("pvp", "bEnablePlayerToPlayerDamage"),
    ("death_penalty", "DeathPenalty"),
    ("exp_rate", "ExpRate"),
)

# /pal world rules 策展分节（spec §4.3）：四节定序、每项 (展示label, settings字段, 值类型)。
# 剔除服务器技术字段（端口/RCON/REST API/日志/认证/备份/聊天限速/跨平台）与长尾细倍率
# （攻防/饱食度/耐力/生命恢复/建筑/采集/掉落）。值类型决定 value 渲染：
#   enum    → meta.setting_display（枚举措辞，如 普通/关闭/开启/掉落物品）
#   rate    → {num}x（ASCII x；spec §2.4「倍率 1.0x」，不用 metadata 的全角 ×）
#   hours   → {num} 小时（游戏设定原单位，spec §2.4 豁免，不套时长格式）
#   minutes → {num} 分钟（同上）
#   int     → {num}（裸数，剥单位）
_RULES_SECTIONS: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
    ("模式", (
        ("难度", "Difficulty", "enum"),
        ("硬核", "bHardcore", "enum"),
        ("死亡惩罚", "DeathPenalty", "enum"),
        ("帕鲁永久死亡", "bPalLost", "enum"),
        ("PVP 伤害", "bEnablePlayerToPlayerDamage", "enum"),
        ("友军伤害", "bEnableFriendlyFire", "enum"),
        ("入侵者袭击", "bEnableInvaderEnemy", "enum"),
    )),
    ("倍率", (
        ("经验", "ExpRate", "rate"),
        ("捕获", "PalCaptureRate", "rate"),
        ("工作速度", "WorkSpeedRate", "rate"),
        ("帕鲁刷新", "PalSpawnNumRate", "rate"),
        ("白天流速", "DayTimeSpeedRate", "rate"),
        ("夜晚流速", "NightTimeSpeedRate", "rate"),
    )),
    ("节奏", (
        ("蛋孵化", "PalEggDefaultHatchingTime", "hours"),
        ("空投间隔", "SupplyDropSpan", "minutes"),
    )),
    ("上限", (
        ("玩家", "ServerPlayerMaxNum", "int"),
        ("公会成员", "GuildPlayerMaxNum", "int"),
        ("据点 每公会", "BaseCampMaxNumInGuild", "int"),
        ("全服", "BaseCampMaxNum", "int"),
    )),
)


def _fmt_rules_num(value) -> str:
    """规则数值渲染：整值去小数点（32.0→32 / 1.0→1），非整保留（1.2→1.2）；
    非数字原样回退（未知枚举/异常值不冒 500）。"""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f == int(f):
        return str(int(f))
    return f"{f:g}"


@dataclass(slots=True)
class PlayerProfileDTO:
    name: str
    level: int
    online: bool
    online_seconds: int


@dataclass(slots=True)
class RankBoardsDTO:
    time_rows: list[tuple[str, int]]   # (name, seconds) 今日在线时长
    level_rows: list[tuple[str, int]]  # (name, level)
    total_rows: list[tuple[str, int]] = field(default_factory=list)  # (name, seconds) 留存期累计


class QueryService:
    _GUILDS_TTL = 90
    _BASES_TTL = 90
    _EVENTS_TTL = 15

    def __init__(
        self, repo: Repository, cache: TTLCache, cfg: AppConfig, meta, clock: Clock,
        settings_cache, world_cache=None, report=None, info_cache=None,
    ) -> None:
        self._repo = repo
        self._cache = cache
        self._cfg = cfg
        self._meta = meta
        self._clock = clock
        self._settings_cache = settings_cache
        self._world_cache = world_cache if world_cache is not None else {}
        self._report = report
        self._info_cache = info_cache if info_cache is not None else {}

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
        # 名字级隐私收敛（spec §3）：与 rank/player_profile 同语义——某显示名下任一 key
        # 被排除/隐藏，则该名整组从 status「在线玩家」节与 online 名单一并剔除（存在性收敛，
        # 防同名另一 key 补位泄露被隐藏者的在线状态）。status 与 online 共用本供数，一次堵死
        # /pal me hide 现状经两入口落空的缺陷（§6#2）。收敛后行数即头行在线数分子（§3，供 T4/T9）。
        excluded = await self.load_excluded_keys(world)
        candidates: list[OnlinePlayerRow] = []
        banned_names: set[str] = set()
        for s in sessions:
            obs = await self._repo.latest_observation(world.world_id, s.player_key)
            if obs is None:
                continue
            # obs.name is always "" by design (observations are name-free);
            # resolve the display name from players.latest_name.
            ident = await self._repo.get_player(world.world_id, s.player_key)
            name = ident.latest_name if ident is not None else ""
            # 本会话 key 直接被排除/隐藏：整名 ban（覆盖 ident 缺失、name_banned 按名查不到的边角）。
            if s.player_key in excluded:
                banned_names.add(name)
                continue
            candidates.append(
                OnlinePlayerRow(
                    name=name, level=obs.level, ping_bucket=obs.ping_bucket,
                    online_seconds=s.observed_seconds,
                )
            )
        # 同名多 key 存在性收敛：候选名下任一 key（含离线/未在开放会话中）被排除/隐藏即整组剔除。
        for name in {r.name for r in candidates}:
            if name not in banned_names and await self.name_banned(world, name, excluded):
                banned_names.add(name)
        rows = [r for r in candidates if r.name not in banned_names]
        rows.sort(key=lambda r: (-r.level, r.name))
        return rows

    async def status(self, world: World) -> StatusDTO:
        key = f"status:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        metric = await self._repo.latest_metric(world.world_id)
        now = self._clock.now()
        rows = await self._online_rows(world)
        # 「今日最高」按本地自然日(day_bounds:per-server tz 优先),与日报/排行同源;
        # 曾为 now-86400 滚动窗口,清晨查询会把昨日晚高峰算进「今日」
        _day, day_start, _end = day_bounds(self._cfg, world, now)
        peak_today = await self._repo.peak_online(world.world_id, since=day_start)
        # 降级双态（spec §3）：无 metric=从未成功（last_ok=None）；有 metric 但超新鲜度
        # 阈值=陈旧（degraded 且 last_ok=observed_at，供「最后成功于 N 分钟前」死分支复活）。
        stale = metric is not None and metric_stale(
            metric.observed_at, now, self._cfg.polling.metrics_seconds
        )
        degraded = metric is None or stale

        dto = StatusDTO(
            server_name=self._config_server_name(world),  # 降级标题锚点=配置名（spec §2.1）
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
            now=now,
            # detail 仅在 live（非 degraded）时装配；degraded（含陈旧）行不下发详细区
            detail=None if degraded else self._build_status_detail(world, metric),
        )
        self._cache.set(key, dto, _STATUS_TTL)
        return dto

    def _server_address(self, server_id: str) -> str:
        for s in self._cfg.servers:
            if s.server_id == server_id:
                return s.base_url
        return ""

    def _config_server_name(self, world: World) -> str:
        """降级标题锚点用插件配置名（spec §2.1：server_id≡name，与 @override/link 同词汇）；
        配置缺失（未注册/测试替身）回退游戏内 world.server_name。"""
        for s in self._cfg.servers:
            if s.server_id == world.server_id:
                return s.name
        return world.server_name

    def _status_rules(self, server_id: str) -> dict[str, str]:
        """detail.rules 白名单子集：从 settings 快照取 4 项，经 setting_display
        统一措辞（与 /pal world rules 一致）；缺该字段或 meta 不可用则整键省略。"""
        rules: dict[str, str] = {}
        if self._meta is None:
            return rules
        raw = self._settings_cache.get(server_id, {})
        for out_key, field_name in _STATUS_RULE_FIELDS:
            if field_name in raw:
                rules[out_key] = self._meta.setting_display(field_name, raw[field_name])
        return rules

    def _build_status_detail(self, world: World, metric) -> StatusDetailDTO:
        # 缺采集项降级为空串/0（不冒 500、不拖垮整行）：description/uptime 依赖
        # info/metrics 共享缓存，version 走 World（持久化），address 走 config。
        info = self._info_cache.get(world.server_id, {})
        return StatusDetailDTO(
            version=world.version,
            description=str(info.get("description", "") or ""),
            uptime_seconds=int(info.get("uptime", 0) or 0),
            frametime_ms=round(metric.frame_time, 1),
            address=self._server_address(world.server_id),
            rules=self._status_rules(world.server_id),
        )

    async def online(self, world: World) -> OnlineDTO:
        key = f"online:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        rows = await self._online_rows(world)
        dto = OnlineDTO(rows=rows, updated_at=self._clock.now(), degraded=False)
        self._cache.set(key, dto, _ONLINE_TTL)
        return dto

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
        # 统一序号空间（spec §3 据点名口径）：BASE-n 编号 / guild bases 列表序号 /
        # guild base #序号 查找 / 事件主体解析全部基于同一张含 low 置信度、hidden 排除
        # 的清单——否则事件里的 #N 与 /pal guild base #N 会对不上。
        bases = await self._repo.list_bases(world.world_id, include_low=True)
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
        # 「今日」窗口与 rank/日报同源(day_bounds:per-server tz 优先、DST 安全)
        since = (day_bounds(self._cfg, world, self._clock.now())[1]
                 if today_only else None)
        # 候选池=近 20 条（折叠在 formatter 侧作用于该池之上，spec §4.4）。
        events = await self._repo.list_events(world.world_id, since=since, limit=20)
        # 主体名批量解析（含隐藏收敛 + 据点/公会回退，spec §4.4）；措辞走 event_wording 单一真相源。
        names = await self.resolve_event_subjects(world, events)
        dtos: list[EventDTO] = []
        for e in events:
            # 隐藏/查无玩家事件整条跳过（resolver 对 player 主体缺席即跳，不泄漏隐藏玩家）。
            if e.subject_type == "player" and e.subject_key not in names:
                continue
            dtos.append(EventDTO(
                occurred_at=e.occurred_at, event_type=e.event_type.value,
                summary=event_wording(e, names.get(e.subject_key, "")),
            ))
        self._cache.set(key, dtos, self._EVENTS_TTL)
        return dtos

    def _render_rule_value(self, field: str, value, kind: str) -> str:
        if kind == "enum":
            # 枚举措辞与状态卡 detail 同源（setting_display：enum_map 优先）。
            return self._meta.setting_display(field, value) if self._meta else str(value)
        num = _fmt_rules_num(value)
        if kind == "rate":
            return f"{num}x"
        if kind == "hours":
            return f"{num} 小时"
        if kind == "minutes":
            return f"{num} 分钟"
        return num  # int：裸数

    async def rules(self, world: World) -> RulesDTO:
        key = f"rules:{world.world_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        raw = self._settings_cache.get(world.server_id, {})
        # 具体目标已定位但快照缺失 = 取数失败态（spec §9 空态/错误态分派）：
        # settings 未获取（空映射）→ available=False，formatter 走 ⚠️。
        available = bool(raw)
        sections: list[RuleSection] = []
        if available:
            for title, entries in _RULES_SECTIONS:
                items: list[tuple[str, str]] = [
                    (label, self._render_rule_value(field, raw[field], kind))
                    for label, field, kind in entries
                    if field in raw    # 快照缺该字段则整项省略（不塞空串，同 status detail）
                ]
                if items:
                    sections.append(RuleSection(title=title, items=items))
        # 隐私模式注两句分叉（spec §4.3，勿混）：strict = 据点模块停用；advanced = 暂按 balanced。
        privacy_note = None
        if self._cfg.privacy.mode == "strict":
            privacy_note = "据点模块在 strict 隐私模式下停用"
        elif self._cfg.privacy.mode == "advanced":
            privacy_note = "advanced 隐私模式暂按 balanced 生效"
        dto = RulesDTO(
            sections=sections, available=available,
            privacy_note=privacy_note, updated_at=self._clock.now(),
        )
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
        # 取数失败态（spec §4.2/§6#8）：概览人口普查依赖 game-data 快照——缺失时 available=False，
        # formatter 走 ⚠️「尚未获取到世界快照」，不再静默渲染全 0 假数据。
        # 在线/容量/据点数取 latest_metric 官方口径（与 status 同源）；FPS 归 status 不入本 DTO。
        dto = WorldSummaryDTO(
            world_day=metric.world_day if metric else world.current_day,
            online=metric.online_players if metric else counts["Player"],
            max_players=metric.max_players if metric else 0,
            players=counts["Player"], otomo=counts["OtomoPal"], base_pal=counts["BaseCampPal"],
            wild=counts["WildPal"], npc=counts["NPC"], palbox=palbox, guilds=len(guild_ids),
            basecamp_count=metric.basecamp_count if metric else 0,
            wild_top=wild_top,
            available=gd is not None,
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

    async def load_excluded_keys(self, world: World) -> set[str]:
        # 与 ReportService/name_resolver 共用同一真相源（避免口径复制漂移）。
        return await _load_excluded_keys(
            self._repo, world.world_id, self._cfg.players.exclude_names
        )

    async def resolve_event_subjects(
        self, world: World, events: list[WorldEvent]
    ) -> dict[str, str]:
        """事件主体名批量解析入口（events() 接 resolver，供 T6 events 复用）。
        隐藏/被排除玩家主体缺席（调用方跳过整条）；据点用统一序号空间、hidden 回退
        「据点」；公会查无回退「公会」。ReportService（T7 today）另经 name_resolver
        自由函数复用同一逻辑。"""
        excluded = await self.load_excluded_keys(world)
        return await resolve_subjects(self._repo, world.world_id, events, excluded)

    def _converge_by_name(
        self, pairs: list[tuple[str, int]], excluded_names: set[str], n: int,
    ) -> list[tuple[str, int]]:
        """(name, secs) 列表按显示名归并求和,被排除/隐藏名字整组剔除,取 Top-N。
        今日/total 两榜共用同一名字级收敛剔除(存在性收敛:不让同名另一 key 补位,
        泄露被隐藏者的活动)。"""
        name_totals: dict[str, int] = {}
        for name, secs in pairs:
            if secs <= 0:
                continue
            name_totals[name] = name_totals.get(name, 0) + secs
        for name in excluded_names:
            name_totals.pop(name, None)
        return sorted(name_totals.items(), key=lambda kv: (-kv[1], kv[0]))[:n]

    async def rank(self, world: World, mode: str = "both") -> RankBoardsDTO:
        excluded = await self.load_excluded_keys(world)
        n = self._cfg.players.rank_top_n
        now = self._clock.now()

        time_rows: list[tuple[str, int]] = []
        if mode in ("both", "today", "time"):
            _day, start, end = day_bounds(self._cfg, world, now)
            sessions = await self._repo.sessions_in_day(world.world_id, start, end)
            # 时长按会话与今日窗口的墙钟交叠计入、以 observed_seconds 封顶——
            # 跨午夜会话不再把昨日时长整段灌进今日榜,采样缺口也不虚增。
            pairs: list[tuple[str, int]] = []
            banned_names: set[str] = set()
            for s in sessions:
                ident = await self._repo.get_player(world.world_id, s.player_key)
                name = ident.latest_name if ident is not None else s.player_key[:8]
                if s.player_key in excluded:
                    banned_names.add(name)
                    continue
                wall_end = s.left_at if s.left_at is not None else now
                overlap = min(end, wall_end) - max(start, s.joined_at)
                secs = min(s.observed_seconds, max(overlap, 0))
                pairs.append((name, secs))
            time_rows = self._converge_by_name(pairs, banned_names, n)

        total_rows: list[tuple[str, int]] = []
        if mode == "total":
            # total = 留存期内(受 prune session_days 裁剪)累计 Σobserved_seconds,
            # 直接求和、无墙钟窗口封顶(与今日榜逻辑不同套)。隐私必须复用同一名字级
            # 收敛:被排除/隐藏 key 的整组名字剔除,不得只按 player_key 裸过滤。
            durations = await self._repo.total_durations(world.world_id)
            pairs = []
            banned_names = set()
            for player_key, secs in durations.items():
                ident = await self._repo.get_player(world.world_id, player_key)
                name = ident.latest_name if ident is not None else player_key[:8]
                if player_key in excluded:
                    banned_names.add(name)
                    continue
                pairs.append((name, secs))
            total_rows = self._converge_by_name(pairs, banned_names, n)

        level_rows: list[tuple[str, int]] = []
        if mode in ("both", "level"):
            players = await self._repo.list_players_by_level(world.world_id)
            # 与时长榜同一收敛语义:名字被任何被排除/隐藏 key 占用即整组不上榜
            hidden_names = {p.latest_name for p in players if p.player_key in excluded}
            seen: set[str] = set()
            for p in players:
                if p.latest_name in hidden_names or p.latest_name in seen:
                    continue
                seen.add(p.latest_name)
                level_rows.append((p.latest_name, p.latest_level))
                if len(level_rows) >= n:
                    break

        return RankBoardsDTO(time_rows=time_rows, level_rows=level_rows, total_rows=total_rows)

    async def name_banned(self, world: World, name: str, excluded: set[str]) -> bool:
        """名字级收敛判定(与 rank 两榜同语义):同名任一 key 被排除/隐藏
        即整组不可见——同一玩家改名/多 key 时,自助隐藏不因另一 key
        未隐藏而被绕过。"""
        keys = await self._repo.list_players_by_name(world.world_id, name)
        return any(k in excluded for k in keys)

    async def player_profile(self, world: World, name: str) -> PlayerProfileDTO | None:
        ident = await self._repo.get_player_by_name(world.world_id, name)
        if ident is None:
            return None
        excluded = await self.load_excluded_keys(world)
        if await self.name_banned(world, ident.latest_name, excluded):
            return None
        session = await self._repo.get_open_session(world.world_id, ident.player_key)
        return PlayerProfileDTO(
            name=ident.latest_name, level=ident.latest_level,
            online=session is not None,
            online_seconds=session.observed_seconds if session is not None else 0,
        )
