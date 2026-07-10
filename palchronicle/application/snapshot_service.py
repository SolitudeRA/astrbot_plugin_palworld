from __future__ import annotations

import asyncio

from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.config import AppConfig, ServerConfig
from palchronicle.domain.models import GameDataSnapshot, World, WorldMetric
from palchronicle.infrastructure.clock import Clock


class SnapshotService:
    def __init__(
        self,
        repo,
        normalizer_mod,
        privacy_mod,
        meta,
        salt: bytes,
        cfg: AppConfig,
        clock: Clock,
        players,
        guilds,
        bases,
        events,
        *,
        shared_settings: dict | None = None,
        shared_world: dict | None = None,
    ) -> None:
        self._repo = repo
        self._normalizer = normalizer_mod
        self._privacy = privacy_mod
        self._meta = meta
        self._salt = salt
        self._cfg = cfg
        self._clock = clock
        self._players = players
        self._guilds = guilds
        self._bases = bases
        self._events = events
        self._settings_cache: dict[str, dict] = {}
        self._shared_settings = shared_settings
        self._shared_world = shared_world
        # key=world_id, value=(candidate, streak, baseline_peak)
        self._online_streak: dict[str, tuple[int, int, int]] = {}

    async def ingest_info(
        self, server: ServerConfig, resp: RestResponse
    ) -> World | None:
        if not resp.ok or resp.data is None:
            return None
        now = self._clock.now()
        info = self._normalizer.normalize_info(resp.data, now)
        current = await self._repo.get_current_world(server.server_id)
        if current is not None and current.worldguid == info.worldguid:
            current.last_seen_at = now
            current.version = info.version or current.version
            current.server_name = info.server_name or current.server_name
            await self._repo.upsert_world(current)
            return current
        if current is not None and current.worldguid != info.worldguid:
            # 换世界：旧世界活动会话置 uncertain
            await self._players.mark_uncertain(current)
        world = World(
            world_id=f"{server.server_id}:{info.worldguid}:0",
            server_id=server.server_id,
            worldguid=info.worldguid,
            epoch=0,
            server_name=info.server_name,
            version=info.version,
            first_seen_at=now,
            last_seen_at=now,
            current_day=0,
        )
        await self._repo.upsert_world(world)
        return world

    async def ingest_metrics(self, world: World, resp: RestResponse) -> None:
        if not resp.ok or resp.data is None:
            return
        snap = self._normalizer.normalize_metrics(resp.data, self._clock.now())
        metric = WorldMetric(
            world_id=world.world_id,
            observed_at=snap.observed_at,
            fps=snap.fps,
            frame_time=snap.frame_time,
            online_players=snap.online,
            world_day=snap.days,
            basecamp_count=snap.basecamp_count,
        )
        # 候选峰值的基线须取自本快照落库前 (含候选首见前) 的历史峰值,
        # 否则候选自身的落库会抬高 peak_online, 使确认时永远无法严格超越
        prev_peak = await self._repo.peak_online(world.world_id)
        await self._repo.insert_metric(metric)
        if snap.days and snap.days != world.current_day:
            world.current_day = snap.days
            world.last_seen_at = snap.observed_at
            await self._repo.upsert_world(world)
        if self._events is not None:
            await self._events.world_day(world, snap.days)
            candidate, streak, baseline = self._online_streak.get(
                world.world_id, (0, 0, 0)
            )
            if snap.online == candidate and snap.online > 0:
                streak += 1
            else:
                candidate, streak, baseline = snap.online, 1, prev_peak
            self._online_streak[world.world_id] = (candidate, streak, baseline)
            if streak >= 2:
                await self._events.online_record(
                    world, candidate, confirmed=True, baseline_peak=baseline
                )

    async def ingest_settings(self, world: World, resp: RestResponse) -> None:
        if not resp.ok or resp.data is None:
            return  # 保留旧缓存, 不谎报
        self._settings_cache[world.world_id] = {
            "data": dict(resp.data),
            "observed_at": self._clock.now(),
        }
        # 与 QueryService.rules 共享的原始 settings 映射, 按 server_id 键入
        if self._shared_settings is not None:
            self._shared_settings[world.server_id] = dict(resp.data)

    def get_settings(self, world_id: str) -> dict | None:
        return self._settings_cache.get(world_id)

    async def ingest_players(self, world: World, resp: RestResponse) -> None:
        if not resp.ok or resp.data is None:
            await self._players.mark_uncertain(world)
            return
        now = self._clock.now()
        rows = self._normalizer.normalize_players(resp.data, now)
        snap = self._privacy.redact_players(
            rows, world.world_id, self._salt, self._cfg.privacy, observed_at=now
        )
        await self._players.apply_players(world, snap)

    async def ingest_game_data(self, world: World, resp: RestResponse) -> None:
        if not resp.ok or resp.data is None:
            return  # 保留基础状态, 不误判
        now = self._clock.now()

        def _compute() -> GameDataSnapshot:
            gd = self._normalizer.normalize_game_data(resp.data, now, self._meta)
            return self._privacy.redact_game_data(
                gd, world.world_id, self._salt, self._cfg.privacy
            )

        gd = await asyncio.to_thread(_compute)
        # 隐私: 仅共享已脱敏的快照给 QueryService.world_summary, 按 server_id 键入
        if self._shared_world is not None:
            self._shared_world[world.server_id] = gd
        if gd.unknown_classes:
            await self._repo.upsert_unknown_classes(gd.unknown_classes)
        await self._guilds.apply(world, gd)
        updates = await self._bases.apply(world, gd)
        if self._events is not None:
            await self._events.base_events(world, updates)
