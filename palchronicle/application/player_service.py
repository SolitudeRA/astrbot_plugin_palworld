from __future__ import annotations

from typing import TYPE_CHECKING

from palchronicle.adapters.privacy_filter import bucketize_ping, hash_user_id
from palchronicle.domain.enums import IdConfidence, LeaveReason, SessionStatus, UnitType
from palchronicle.domain.models import (
    PlayerIdentity,
    PlayerObservation,
    PlayerRow,
    PlayerSession,
    PlayersSnapshot,
    World,
)

if TYPE_CHECKING:
    from palchronicle.application.event_service import EventService


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
        self.events: EventService | None = None  # 由 container 注入 EventService
        self._missing: dict[tuple[str, str], int] = {}

    @staticmethod
    def player_key(salt: bytes, world_id: str, raw_user_id: str) -> str:
        return hash_user_id(salt, world_id, raw_user_id)

    @staticmethod
    def link_companions(gd) -> dict[str, str]:
        owners = {a.instance_id for a in gd.characters
                  if a.unit_type == UnitType.PLAYER and a.instance_id}
        result: dict[str, str] = {}
        for a in gd.characters:
            if a.unit_type != UnitType.OTOMO:
                continue
            owner = a.trainer_instance_id
            if owner and owner in owners and owner not in result and a.pal_class:
                result[owner] = a.pal_class
        return result

    _HEALTH_TOLERANCE = 1.5

    async def apply_players(self, world: World, snap: PlayersSnapshot) -> None:
        now = snap.observed_at
        cap = int(self._cfg.polling.players_seconds * self._HEALTH_TOLERANCE)
        for row in snap.players:
            key, conf = _resolve_identity(row, self._salt, world.world_id)
            prev_ident = await self._repo.get_player_by_name(world.world_id, row.name)
            is_new_identity = prev_ident is None or prev_ident.player_key != key
            old_level = prev_ident.latest_level if (prev_ident and not is_new_identity) else None

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
            else:
                delta = max(0, now - session.last_confirmed_at)
                session.observed_seconds += min(delta, cap)
                session.last_confirmed_at = now
                session.status = SessionStatus.ACTIVE
                session.leave_reason = None
                await self._repo.update_session(session)

            self._missing.pop((world.world_id, key), None)

            if old_level is not None and row.level > old_level and self.events is not None:
                await self.events.level_up(world, key, old_level, row.level)

        present = {
            _resolve_identity(r, self._salt, world.world_id)[0] for r in snap.players
        }
        for sess in await self._repo.list_open_sessions(world.world_id):
            if sess.status != SessionStatus.ACTIVE or sess.player_key in present:
                continue
            mkey = (world.world_id, sess.player_key)
            streak = self._missing.get(mkey, 0) + 1
            if streak >= 2:
                sess.status = SessionStatus.CLOSED
                sess.leave_reason = LeaveReason.OBSERVED_TIMEOUT
                sess.left_at = now
                await self._repo.update_session(sess)
                self._missing.pop(mkey, None)
            else:
                self._missing[mkey] = streak

        # §10.1: 健康快照即收敛时机——中断期间置 uncertain 且本快照未回归的会话,
        # last_confirmed_at 超过 uncertain_timeout 立即 closed/world_offline
        await self.sweep_uncertain(world)

    async def mark_uncertain(self, world: World) -> None:
        for sess in await self._repo.list_open_sessions(world.world_id):
            if sess.status == SessionStatus.ACTIVE:
                sess.status = SessionStatus.UNCERTAIN
                await self._repo.update_session(sess)

    async def sweep_uncertain(self, world: World) -> None:
        now = self._clock.now()
        timeout = self._cfg.privacy.uncertain_timeout
        for sess in await self._repo.list_open_sessions(world.world_id):
            if sess.status != SessionStatus.UNCERTAIN:
                continue
            if now - sess.last_confirmed_at > timeout:
                sess.status = SessionStatus.CLOSED
                sess.leave_reason = LeaveReason.WORLD_OFFLINE
                sess.left_at = now
                await self._repo.update_session(sess)

    async def recover_on_start(self, world: World) -> None:
        self._missing.clear()
