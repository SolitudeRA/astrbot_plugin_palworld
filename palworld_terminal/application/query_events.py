from __future__ import annotations

from typing import Any

from ..domain.models import World
from ..infrastructure.cache import TTLCache
from ..infrastructure.clock import Clock
from .dtos import (
    EventView,
    RulesDTO,
    RuleSection,
    WildTopRow,
    WorldSummaryDTO,
    event_view,
)
from .name_resolver import keep_world_subject_under_strict
from .query_privacy import _PrivacyBase
from .query_support import _RULES_SECTIONS, _fmt_rules_num
from .report_service import day_bounds


class _EventSummaryQueries(_PrivacyBase):
    """世界事件 / 规则 / 摘要 / 今日查询（events、rules、world_summary、today）。"""

    _cache: TTLCache
    _clock: Clock
    _meta: Any
    _settings_cache: Any
    _world_cache: Any
    _report: Any
    _EVENTS_TTL: int
    _BASES_TTL: int

    async def events(self, world: World, today_only: bool) -> list[EventView]:
        key = f"events:{world.world_id}:{int(today_only)}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        # 「今日」窗口与 rank/日报同源(day_bounds:per-server tz 优先、DST 安全)
        since = (day_bounds(self._cfg, world, self._clock.now())[1]
                 if today_only else None)
        # 候选池=近 20 条（折叠在 formatter 侧作用于该池之上，spec §4.4）。
        events = await self._repo.list_events(world.world_id, since=since, limit=20)
        # strict 隐私：只保留 world 主体事件（聚合、无个体归因）；player/base/guild 主体
        # （个体作息·时刻、据点、公会）不经 events 绕出 strict——与 status 双砍/据点不可绕
        # 同哲学（world-only 规则与 today 同一真相源 keep_world_subject_under_strict）。
        events = keep_world_subject_under_strict(
            events, self._cfg.privacy.mode == "strict"
        )
        # 主体名批量解析（含隐藏收敛 + 据点/公会回退，spec §4.4）；视图经 event_view 单一
        # 构造入口（措辞渲染下沉 presentation.render_event）。
        names = await self.resolve_event_subjects(world, events)
        views: list[EventView] = []
        for e in events:
            # 隐藏/查无玩家事件整条跳过（resolver 对 player 主体缺席即跳，不泄漏隐藏玩家）。
            if e.subject_type == "player" and e.subject_key not in names:
                continue
            views.append(event_view(e, names.get(e.subject_key, "")))
        self._cache.set(key, views, self._EVENTS_TTL)
        return views

    def _render_rule_value(self, field: str, value, kind: str) -> str:
        if kind == "enum":
            # 枚举措辞与状态卡 detail 同源（setting_display：enum_map 优先）。
            return self._meta.setting_display(field, value) if self._meta else str(value)
        if kind == "rate":
            # 倍率恒一位小数（spec §2.4：默认 1.0 渲染 1.0x，不去尾成 1x）；
            # 非数字（异常快照值）回退去尾渲染，不冒 500。
            try:
                return f"{float(value):.1f}x"
            except (TypeError, ValueError):
                return f"{_fmt_rules_num(value)}x"
        num = _fmt_rules_num(value)
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
