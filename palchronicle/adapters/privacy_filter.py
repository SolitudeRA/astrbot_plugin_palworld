from __future__ import annotations

import hmac
import math
from hashlib import sha256

from palchronicle.config import PrivacyConfig
from palchronicle.domain.enums import PingBucket
from palchronicle.domain.models import PlayerRow, PlayersSnapshot


def hash_user_id(salt: bytes, world_id: str, raw_user_id: str) -> str:
    message = f"{world_id}:{raw_user_id}".encode("utf-8")
    return hmac.new(salt, message, sha256).hexdigest()


def bucketize_ping(ms: float | None, cfg: PrivacyConfig) -> PingBucket:
    if ms is None:
        return PingBucket.UNKNOWN
    if ms <= cfg.ping_good_ms:
        return PingBucket.GOOD
    if ms <= cfg.ping_ok_ms:
        return PingBucket.OK
    return PingBucket.HIGH


def quantize_cell(x: float, y: float, z: float, grid: int) -> str:
    cx = math.floor(x / grid)
    cy = math.floor(y / grid)
    cz = math.floor(z / grid)
    return f"{cx}:{cy}:{cz}"


def _hash_or_none(salt: bytes, world_id: str, raw_id) -> str | None:
    if raw_id is None or raw_id == "":
        return None
    return hash_user_id(salt, world_id, str(raw_id))


def redact_players(
    rows: list[dict],
    world_id: str,
    salt: bytes,
    cfg: PrivacyConfig,
    observed_at: int = 0,
) -> PlayersSnapshot:
    players: list[PlayerRow] = []
    for row in rows:
        players.append(
            PlayerRow(
                userid=_hash_or_none(salt, world_id, row.get("userId")),
                player_id=_hash_or_none(salt, world_id, row.get("playerId")),
                name=row.get("name", ""),
                level=int(row.get("level", 0) or 0),
                ping=row.get("ping"),
                building_count=int(row.get("building_count", 0) or 0),
            )
        )
    return PlayersSnapshot(observed_at=observed_at, players=players)
