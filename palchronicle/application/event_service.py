from __future__ import annotations

from typing import TYPE_CHECKING

from palchronicle.adapters.sqlite_repository import Repository
from palchronicle.domain.enums import Confidence, EventType
from palchronicle.domain.events import make_dedup_key
from palchronicle.domain.models import World, WorldEvent
from palchronicle.infrastructure.clock import Clock

if TYPE_CHECKING:
    from palchronicle.application.base_service import BaseUpdate


class EventService:
    MILESTONES: tuple[int, ...] = (100, 200, 365, 500, 1000, 2000)

    def __init__(self, repo: Repository, clock: Clock) -> None:
        self._repo = repo
        self._clock = clock

    @staticmethod
    def dedup_key(world_id: str, event_type: EventType, *parts: object) -> str:
        return make_dedup_key(world_id, event_type, *parts)

    async def _emit(
        self,
        world: World,
        event_type: EventType,
        subject_type: str,
        subject_key: str,
        dedup: str,
        payload: dict,
        confidence: Confidence = Confidence.HIGH,
        visibility: str = "public",
    ) -> bool:
        now = self._clock.now()
        event = WorldEvent(
            event_id=None,
            world_id=world.world_id,
            event_type=event_type,
            subject_type=subject_type,
            subject_key=subject_key,
            occurred_at=now,
            confirmed_at=now,
            payload=payload,
            visibility=visibility,
            confidence=confidence,
            dedup_key=dedup,
        )
        return await self._repo.insert_event(event)

    async def level_up(
        self, world: World, player_key: str, old: int, new: int
    ) -> None:
        if new <= old:
            return
        dedup = self.dedup_key(
            world.world_id, EventType.PLAYER_LEVEL_UP, player_key, new
        )
        await self._emit(
            world,
            EventType.PLAYER_LEVEL_UP,
            "player",
            player_key,
            dedup,
            {"old": old, "new": new},
        )

    async def new_player(self, world: World, player_key: str) -> None:
        dedup = self.dedup_key(world.world_id, EventType.NEW_PLAYER, player_key)
        await self._emit(
            world, EventType.NEW_PLAYER, "player", player_key, dedup, {}
        )

    async def new_guild(self, world: World, guild_key: str) -> None:
        dedup = self.dedup_key(world.world_id, EventType.NEW_GUILD, guild_key)
        await self._emit(
            world, EventType.NEW_GUILD, "guild", guild_key, dedup, {}
        )

    async def online_record(
        self,
        world: World,
        value: int,
        confirmed: bool,
        baseline_peak: int | None = None,
    ) -> None:
        if not confirmed:
            return
        peak = (
            baseline_peak
            if baseline_peak is not None
            else await self._repo.peak_online(world.world_id)
        )
        if value <= peak:
            return
        dedup = self.dedup_key(world.world_id, EventType.ONLINE_RECORD, value)
        await self._emit(
            world,
            EventType.ONLINE_RECORD,
            "world",
            world.world_id,
            dedup,
            {"value": value},
        )

    async def base_events(
        self, world: World, updates: list[BaseUpdate]
    ) -> None:
        for u in updates:
            if u.is_new and u.confidence != Confidence.LOW:
                dedup = self.dedup_key(
                    world.world_id, EventType.NEW_BASE, u.base_key
                )
                await self._emit(
                    world,
                    EventType.NEW_BASE,
                    "base",
                    u.base_key,
                    dedup,
                    {
                        "guild_key": u.guild_key,
                        "worker_count": u.worker_count,
                        "confidence": u.confidence.value,
                    },
                    confidence=u.confidence,
                )
            if u.is_vanished:
                dedup = self.dedup_key(
                    world.world_id,
                    EventType.BASE_VANISHED,
                    u.base_key,
                    world.current_day,
                )
                await self._emit(
                    world,
                    EventType.BASE_VANISHED,
                    "base",
                    u.base_key,
                    dedup,
                    {"first_missing_day": world.current_day},
                )
            if u.prev_worker_count is not None:
                prev = u.prev_worker_count
                cur = u.worker_count
                threshold = max(3, int(prev * 0.2))
                if abs(cur - prev) >= threshold:
                    bucket = "up" if cur > prev else "down"
                    dedup = self.dedup_key(
                        world.world_id,
                        EventType.WORKER_DELTA,
                        u.base_key,
                        world.current_day,
                        bucket,
                    )
                    await self._emit(
                        world,
                        EventType.WORKER_DELTA,
                        "base",
                        u.base_key,
                        dedup,
                        {"prev": prev, "cur": cur},
                    )

    async def world_day(self, world: World, days: int) -> None:
        for m in self.MILESTONES:
            if days >= m:
                dedup = self.dedup_key(
                    world.world_id, EventType.WORLD_DAY_MILESTONE, m
                )
                await self._emit(
                    world,
                    EventType.WORLD_DAY_MILESTONE,
                    "world",
                    world.world_id,
                    dedup,
                    {"milestone": m, "day": days},
                )
