"""领域枚举。契约全部枚举（均 StrEnum，成员值严格照契约）。"""
from __future__ import annotations

from enum import StrEnum, auto


class _LowerNameEnum(StrEnum):
    @staticmethod
    def _generate_next_value_(name, start, count, last_values):
        return name.lower()


class UnitType(StrEnum):
    PLAYER = "Player"
    OTOMO = "OtomoPal"
    BASE_CAMP = "BaseCampPal"
    WILD = "WildPal"
    NPC = "NPC"
    UNKNOWN = "Unknown"


class ActionCategory(StrEnum):
    WORKING = "working"
    MOVING = "moving"
    IDLE = "idle"
    COMBAT = "combat"
    SLEEPING = "sleeping"
    EATING = "eating"
    INCAPACITATED = "incapacitated"
    UNKNOWN = "unknown"


class EventType(_LowerNameEnum):
    PLAYER_LEVEL_UP = auto()
    NEW_PLAYER = auto()
    NEW_GUILD = auto()
    NEW_BASE = auto()
    BASE_VANISHED = auto()
    WORKER_DELTA = auto()
    WORLD_DAY_MILESTONE = auto()
    ONLINE_RECORD = auto()


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LeaveReason(StrEnum):
    OBSERVED_TIMEOUT = "observed_timeout"
    WORLD_OFFLINE = "world_offline"
    UNKNOWN = "unknown"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    UNCERTAIN = "uncertain"


class AccessMode(StrEnum):
    RESTRICTED = "restricted"
    OPEN = "open"


class PingBucket(StrEnum):
    GOOD = "good"
    OK = "ok"
    HIGH = "high"
    UNKNOWN = "unknown"


class EndpointName(StrEnum):
    INFO = "info"
    METRICS = "metrics"
    PLAYERS = "players"
    SETTINGS = "settings"
    GAME_DATA = "game_data"


class IdConfidence(StrEnum):
    HIGH = "high"
    LOW = "low"


# 合法 admin 写动作集（域概念）：写端点路径白名单，杜绝拼错端点静默打偏。
ADMIN_ACTIONS: frozenset[str] = frozenset(
    {"announce", "save", "kick", "unban", "ban", "shutdown", "stop"}
)
