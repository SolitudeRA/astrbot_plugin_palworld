"""领域枚举。Phase 1 仅需 AccessMode；其余枚举在 Phase 2 补齐（契约枚举节）。"""
from __future__ import annotations

from enum import StrEnum


class AccessMode(StrEnum):
    RESTRICTED = "restricted"
    OPEN = "open"


class EndpointName(StrEnum):
    INFO = "info"
    METRICS = "metrics"
    PLAYERS = "players"
    SETTINGS = "settings"
    GAME_DATA = "game_data"
