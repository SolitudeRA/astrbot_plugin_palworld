from __future__ import annotations

from dataclasses import dataclass

from ..domain.enums import Confidence, PingBucket


@dataclass(slots=True)
class StatusDetailDTO:
    """状态卡「详细区」的白名单子集（仅世界级信息，不含玩家个体数据）。

    version/address 恒有值；description/uptime 依赖 info/metrics 采集，缺失给空串/0；
    rules 仅含快照里存在的规则键（缺项省略，不塞空串）。
    """
    version: str
    description: str
    uptime_seconds: int
    frametime_ms: float
    address: str
    rules: dict[str, str]


@dataclass(slots=True)
class StatusDTO:
    server_name: str
    world_name: str
    world_day: int
    online: int
    max_players: int
    basecamp_count: int          # 官方 metrics.basecampnum
    fps: float
    frame_time: float
    smoothness_label: str
    players: list[tuple[str, int, str]]   # (name, level, ping_bucket value)
    peak_online_today: int
    updated_at: int
    degraded: bool
    last_ok: int | None
    # 详细区：仅 ready 且非 degraded 时装配（degraded/骨架行为 None，status_rows 不下发）
    detail: StatusDetailDTO | None = None


@dataclass(slots=True)
class OnlinePlayerRow:
    name: str
    level: int
    ping_bucket: PingBucket
    online_seconds: int


@dataclass(slots=True)
class OnlineDTO:
    rows: list[OnlinePlayerRow]
    updated_at: int
    degraded: bool


@dataclass(slots=True)
class WildTopRow:
    name: str
    count: int


@dataclass(slots=True)
class WorldSummaryDTO:
    world_day: int
    online: int
    players: int
    otomo: int
    base_pal: int
    wild: int
    npc: int
    palbox: int
    guilds: int
    fps: float
    average_fps: float
    wild_top: list[WildTopRow]


@dataclass(slots=True)
class RuleRow:
    label: str
    value: str


@dataclass(slots=True)
class RulesDTO:
    rows: list[RuleRow]
    updated_at: int
    advanced_note: str | None


@dataclass(slots=True)
class GuildDTO:
    name: str
    observed_members: int
    palbox: int
    base_pals: int
    active_7d: int


@dataclass(slots=True)
class GuildDetailDTO:
    name: str
    first_seen_at: int
    last_seen_at: int
    observed_members: int
    active_today: int
    active_week: int
    palbox: int
    base_pals: int
    average_level: float
    base_event_lines: list[str]


@dataclass(slots=True)
class BaseDTO:
    index: int
    display_name: str
    guild_name: str | None
    confidence: Confidence
    worker_count: int


@dataclass(slots=True)
class BaseDetailDTO:
    display_name: str
    guild_name: str | None
    confidence: Confidence
    palbox_count: int
    worker_count: int
    active_count: int
    average_level: float
    average_hp_ratio: float
    action_distribution: dict[str, int]
    activity_score: float
    health_score: float


@dataclass(slots=True)
class EventDTO:
    occurred_at: int
    event_type: str
    summary: str


@dataclass(slots=True)
class ServerStatusRow:
    name: str
    ready: bool
    online: bool
    allowed: bool
    active: bool
