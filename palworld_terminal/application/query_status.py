from __future__ import annotations

from typing import Any

from ..domain.models import World
from ..infrastructure.cache import TTLCache
from ..infrastructure.clock import Clock
from .dtos import OnlineDTO, OnlinePlayerRow, StatusDetailDTO, StatusDTO
from .query_privacy import _PrivacyBase
from .query_support import _ONLINE_TTL, _STATUS_RULE_FIELDS, _STATUS_TTL, metric_stale
from .report_service import day_bounds


class _StatusQueries(_PrivacyBase):
    """状态卡 / 在线名单查询（status、online）。"""

    _cache: TTLCache
    _clock: Clock
    _meta: Any
    _settings_cache: Any
    _info_cache: Any

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
        # 头行供数（spec §3/§4.24）：/max 取 metric.max_players、今日峰值取当日 peak_online
        # 聚合（与 status 同源，按本地自然日 day_bounds 起点；缺 metric 则 0）。头行在线数分子
        # 恒 = len(rows)（收敛后名单数），不取 metric.online_players——T3 隐私收敛在此闭合。
        now = self._clock.now()
        metric = await self._repo.latest_metric(world.world_id)
        _day, day_start, _end = day_bounds(self._cfg, world, now)
        peak_today = await self._repo.peak_online(world.world_id, since=day_start)
        dto = OnlineDTO(
            rows=rows, updated_at=now, degraded=False,
            max_players=metric.max_players if metric else 0,
            peak_online=peak_today,
        )
        self._cache.set(key, dto, _ONLINE_TTL)
        return dto
