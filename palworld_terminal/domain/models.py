"""领域模型（dataclass）。字段严格照契约领域模型节。"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.enums import (
    ActionCategory,
    Confidence,
    EventType,
    IdConfidence,
    LeaveReason,
    PingBucket,
    SessionStatus,
    UnitType,
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
    max_players: int = 0


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


@dataclass(slots=True)
class CharacterActor:
    unit_type: UnitType
    instance_id: str | None
    nickname: str | None
    trainer_instance_id: str | None
    trainer_nickname: str | None
    player_userid: str | None
    level: int | None
    hp: int | None
    max_hp: int | None
    guild_id: str | None
    guild_name: str | None
    pal_class: str | None
    action: ActionCategory
    ai_action: ActionCategory
    x: float | None
    y: float | None
    z: float | None
    is_active: bool


@dataclass(slots=True)
class PalBoxActor:
    guild_id: str | None
    guild_name: str | None
    pal_class: str | None
    x: float
    y: float
    z: float


@dataclass(slots=True)
class GameDataSnapshot:
    observed_at: int
    fps: float
    average_fps: float
    characters: list[CharacterActor] = field(default_factory=list)
    palboxes: list[PalBoxActor] = field(default_factory=list)
    unknown_classes: list[str] = field(default_factory=list)
    # 游戏内时钟（顶层 InGameDays/InGameTime 直取）——参考/氛围文案用，
    # world_day 权威真源仍是 metrics.days，不一致不告警、不覆盖。
    in_game_days: int = 0
    in_game_time: str = ""


@dataclass(slots=True)
class PlayerRow:
    userid: str | None
    player_id: str | None
    name: str
    level: int
    ping: float | None
    building_count: int


@dataclass(slots=True)
class PlayersSnapshot:
    observed_at: int
    players: list[PlayerRow] = field(default_factory=list)


@dataclass(slots=True)
class MetricsSnapshot:
    observed_at: int
    fps: float
    frame_time: float
    online: int
    max_players: int
    uptime: int
    basecamp_count: int
    days: int


@dataclass(slots=True)
class InfoSnapshot:
    observed_at: int
    version: str
    server_name: str
    description: str
    worldguid: str
