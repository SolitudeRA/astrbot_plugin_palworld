from __future__ import annotations

from typing import TYPE_CHECKING

from ..domain.enums import UnitType
from ..domain.models import GameDataSnapshot, Guild, World
from ..domain.privacy import hash_user_id

if TYPE_CHECKING:
    from ..application.event_service import EventService


class GuildService:
    def __init__(self, repo, salt: bytes, clock):
        self._repo = repo
        self._salt = salt
        self._clock = clock
        self.events: EventService | None = None  # 由 container 注入 EventService

    def _guild_key(self, world_id: str, guild_id: str) -> str:
        return hash_user_id(self._salt, world_id, "GUILD:" + guild_id)

    async def apply(self, world: World, gd: GameDataSnapshot) -> list[Guild]:
        now = gd.observed_at
        members: dict[str, int] = {}
        base_pals: dict[str, int] = {}
        names: dict[str, str] = {}
        for a in gd.characters:
            if not a.guild_id:
                continue
            gk = self._guild_key(world.world_id, a.guild_id)
            if a.guild_name:
                names[gk] = a.guild_name
            if a.unit_type == UnitType.PLAYER:
                members[gk] = members.get(gk, 0) + 1
            elif a.unit_type == UnitType.BASE_CAMP:
                base_pals[gk] = base_pals.get(gk, 0) + 1
        boxes: dict[str, int] = {}
        for pb in gd.palboxes:
            if not pb.guild_id:
                continue
            gk = self._guild_key(world.world_id, pb.guild_id)
            boxes[gk] = boxes.get(gk, 0) + 1
            if pb.guild_name and gk not in names:
                names[gk] = pb.guild_name

        all_keys = set(members) | set(base_pals) | set(boxes)
        existing = {g.guild_key for g in await self._repo.list_guilds(world.world_id)}
        result: list[Guild] = []
        for gk in sorted(all_keys):
            name = names.get(gk) or ("公会-" + gk[:6])
            g = Guild(
                guild_key=gk, world_id=world.world_id, latest_name=name,
                first_seen_at=now, last_seen_at=now,
                observed_member_count=members.get(gk, 0),
                palbox_count=boxes.get(gk, 0),
                base_pal_count=base_pals.get(gk, 0),
            )
            await self._repo.upsert_guild(g)
            if gk not in existing and self.events is not None:
                await self.events.new_guild(world, gk)
            result.append(g)
        return result
