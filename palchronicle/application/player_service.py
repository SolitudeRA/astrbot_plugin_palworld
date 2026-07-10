from __future__ import annotations

from palchronicle.adapters.privacy_filter import bucketize_ping, hash_user_id
from palchronicle.domain.enums import IdConfidence, SessionStatus
from palchronicle.domain.models import (
    PlayerIdentity, PlayerObservation, PlayerRow, PlayerSession, PlayersSnapshot, World,
)


def _resolve_identity(row: PlayerRow, salt: bytes, world_id: str) -> tuple[str, IdConfidence]:
    if row.userid:
        # 脱敏阶段已把 /players.userId 映射为 HMAC hex
        return row.userid, IdConfidence.HIGH
    if row.player_id:
        return hash_user_id(salt, world_id, row.player_id), IdConfidence.HIGH
    return hash_user_id(salt, world_id, row.name.lower()), IdConfidence.LOW


class PlayerService:
    def __init__(self, repo, salt: bytes, cfg, clock):
        self._repo = repo
        self._salt = salt
        self._cfg = cfg
        self._clock = clock
        self.events = None  # 由 container 注入 EventService

    @staticmethod
    def player_key(salt: bytes, world_id: str, raw_user_id: str) -> str:
        return hash_user_id(salt, world_id, raw_user_id)

    async def apply_players(self, world: World, snap: PlayersSnapshot) -> None:
        now = snap.observed_at
        for row in snap.players:
            key, conf = _resolve_identity(row, self._salt, world.world_id)
            existing_ident = await self._repo.get_player_by_name(world.world_id, row.name)
            is_new_identity = existing_ident is None or existing_ident.player_key != key

            bucket = bucketize_ping(row.ping, self._cfg.privacy)
            await self._repo.insert_observation(PlayerObservation(
                observed_at=now, world_id=world.world_id, player_key=key,
                name=row.name, level=row.level, ping_bucket=bucket,
                building_count=row.building_count, guild_key=None,
                position_cell=None, companion_class=None,
            ))
            await self._repo.upsert_player(PlayerIdentity(
                player_key=key, world_id=world.world_id, latest_name=row.name,
                first_seen_at=now, last_seen_at=now, latest_level=row.level,
                latest_guild_key=None, id_confidence=conf,
            ))

            session = await self._repo.get_open_session(world.world_id, key)
            if session is None:
                await self._repo.insert_session(PlayerSession(
                    id=None, world_id=world.world_id, player_key=key,
                    joined_at=now, last_confirmed_at=now, left_at=None,
                    observed_seconds=0, status=SessionStatus.ACTIVE, leave_reason=None,
                ))
                if is_new_identity and self.events is not None:
                    await self.events.new_player(world, key)
