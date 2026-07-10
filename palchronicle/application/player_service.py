from __future__ import annotations

from palchronicle.adapters.privacy_filter import hash_user_id
from palchronicle.domain.enums import IdConfidence
from palchronicle.domain.models import PlayerRow


def _resolve_identity(row: PlayerRow, salt: bytes, world_id: str) -> tuple[str, IdConfidence]:
    if row.userid:
        # 脱敏阶段已把 /players.userId 映射为 HMAC hex
        return row.userid, IdConfidence.HIGH
    if row.player_id:
        return hash_user_id(salt, world_id, row.player_id), IdConfidence.HIGH
    return hash_user_id(salt, world_id, row.name.lower()), IdConfidence.LOW


class PlayerService:
    @staticmethod
    def player_key(salt: bytes, world_id: str, raw_user_id: str) -> str:
        return hash_user_id(salt, world_id, raw_user_id)
