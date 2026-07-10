from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from palchronicle.domain.models import InfoSnapshot, MetricsSnapshot

_TRUE_STRINGS = frozenset({"true", "1", "yes", "on"})


def ci_get(d: Mapping, *keys: str, default: Any = None) -> Any:
    lowered = {str(k).lower(): v for k, v in d.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return default


def str_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in _TRUE_STRINGS
    return False


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def normalize_info(raw: Mapping, now: int) -> InfoSnapshot:
    return InfoSnapshot(
        observed_at=now,
        version=str(ci_get(raw, "version", default="") or ""),
        server_name=str(ci_get(raw, "servername", "server_name", default="") or ""),
        description=str(ci_get(raw, "description", default="") or ""),
        worldguid=str(ci_get(raw, "worldguid", "world_guid", default="") or ""),
    )


def normalize_metrics(raw: Mapping, now: int) -> MetricsSnapshot:
    return MetricsSnapshot(
        observed_at=now,
        fps=_as_float(ci_get(raw, "serverfps", "fps")),
        frame_time=_as_float(ci_get(raw, "serverframetime", "frametime", "frame_time")),
        online=_as_int(ci_get(raw, "currentplayernum", "online", "currentplayers")),
        max_players=_as_int(ci_get(raw, "maxplayernum", "maxplayers", "max_players")),
        uptime=_as_int(ci_get(raw, "uptime")),
        basecamp_count=_as_int(ci_get(raw, "basecampnum", "basecamp_count")),
        days=_as_int(ci_get(raw, "days", "serversdaytime", "world_day")),
    )
