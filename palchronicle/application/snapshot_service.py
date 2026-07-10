from __future__ import annotations

from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.config import AppConfig, ServerConfig
from palchronicle.domain.models import World
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
