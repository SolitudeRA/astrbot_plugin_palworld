from __future__ import annotations

import hmac
import math
from hashlib import sha256

from palchronicle.config import PrivacyConfig
from palchronicle.domain.enums import PingBucket


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
