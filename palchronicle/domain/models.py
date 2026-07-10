"""领域模型（dataclass）。字段严格照契约领域模型节。"""
from __future__ import annotations

from dataclasses import dataclass, field

from palchronicle.domain.enums import (
    Confidence,
    EventType,
    IdConfidence,
    LeaveReason,
    PingBucket,
    SessionStatus,
)


@dataclass(slots=True)
class World:
    world_id: str
    server_id: str
    worldguid: str
    epoch: int
    server_name: str
    version: str
    first_seen_at: int
    last_seen_at: int
    current_day: int


@dataclass(slots=True)
class PlayerIdentity:
    player_key: str
    world_id: str
    latest_name: str
    first_seen_at: int
    last_seen_at: int
    latest_level: int
    latest_guild_key: str | None
    id_confidence: IdConfidence


@dataclass(slots=True)
class PlayerObservation:
    observed_at: int
    world_id: str
    player_key: str
    name: str
    level: int
    ping_bucket: PingBucket
    building_count: int
    guild_key: str | None
    position_cell: str | None
    companion_class: str | None


@dataclass(slots=True)
class PlayerSession:
    id: int | None
    world_id: str
    player_key: str
    joined_at: int
    last_confirmed_at: int
    left_at: int | None
    observed_seconds: int
    status: SessionStatus
    leave_reason: LeaveReason | None


@dataclass(slots=True)
class Guild:
    guild_key: str
    world_id: str
    latest_name: str
    first_seen_at: int
    last_seen_at: int
    observed_member_count: int
    palbox_count: int
    base_pal_count: int


@dataclass(slots=True)
class PalBox:
    palbox_key: str
    world_id: str
    guild_key: str | None
    position_cell: str
    first_seen_at: int
    last_seen_at: int
    status: str


@dataclass(slots=True)
class Base:
    base_key: str
    world_id: str
    palbox_key: str
    display_name: str | None
    guild_key: str | None
    confidence: Confidence
    locked_by_admin: bool
    hidden: bool
    first_seen_at: int
    last_seen_at: int


@dataclass(slots=True)
class BaseObservation:
    base_key: str
    world_id: str
    observed_at: int
    worker_count: int
    active_count: int
    average_level: float
    average_hp_ratio: float
    action_distribution: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class WorldMetric:
    world_id: str
    observed_at: int
    fps: float
    frame_time: float
    online_players: int
    world_day: int
    basecamp_count: int


@dataclass(slots=True)
class WorldEvent:
    event_id: int | None
    world_id: str
    event_type: EventType
    subject_type: str
    subject_key: str
    occurred_at: int
    confirmed_at: int
    payload: dict
    visibility: str
    confidence: Confidence
    dedup_key: str
