from __future__ import annotations

from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.config import AppConfig, ServerConfig
from palchronicle.domain.models import World, WorldMetric
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
        await self._repo.insert_metric(metric)
        if snap.days and snap.days != world.current_day:
            world.current_day = snap.days
            world.last_seen_at = snap.observed_at
            await self._repo.upsert_world(world)

    async def ingest_settings(self, world: World, resp: RestResponse) -> None:
        if not resp.ok or resp.data is None:
            return  # 保留旧缓存, 不谎报
        self._settings_cache[world.world_id] = {
            "data": dict(resp.data),
            "observed_at": self._clock.now(),
        }

    def get_settings(self, world_id: str) -> dict | None:
        return self._settings_cache.get(world_id)
