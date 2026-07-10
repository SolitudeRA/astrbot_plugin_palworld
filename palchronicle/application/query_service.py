from __future__ import annotations

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.config import AppConfig
from palchronicle.domain.models import World
from palchronicle.infrastructure.cache import TTLCache
from palchronicle.infrastructure.clock import Clock
from palchronicle.presentation.dtos import OnlineDTO, OnlinePlayerRow, StatusDTO

_STATUS_TTL = 15
_ONLINE_TTL = 15


class QueryService:
    def __init__(
        self, repo: Repository, cache: TTLCache, cfg: AppConfig, meta, clock: Clock, settings_cache
    ) -> None:
        self._repo = repo
        self._cache = cache
        self._cfg = cfg
        self._meta = meta
        self._clock = clock
        self._settings_cache = settings_cache

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
            max_players=0,
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
