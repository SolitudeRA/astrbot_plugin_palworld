from __future__ import annotations

from palchronicle.domain.enums import EventType


def make_dedup_key(world_id: str, event_type: EventType, *parts: object) -> str:
    segments = [world_id, event_type.name, *(str(p) for p in parts)]
    return "|".join(segments)


def level_up_payload(old_level: int, new_level: int) -> dict:
    return {"old_level": old_level, "new_level": new_level}


def worker_delta_payload(base_key: str, baseline: int, current: int) -> dict:
    return {
        "base_key": base_key,
        "baseline": baseline,
        "current": current,
        "delta": current - baseline,
    }
