from __future__ import annotations

from ..domain.enums import EventType


def make_dedup_key(world_id: str, event_type: EventType, *parts: object) -> str:
    segments = [world_id, event_type.name, *(str(p) for p in parts)]
    return "|".join(segments)
