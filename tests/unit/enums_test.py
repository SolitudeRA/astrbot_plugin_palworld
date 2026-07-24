from enum import StrEnum

from palworld_terminal.domain.enums import (
    AccessMode,
    ActionCategory,
    Confidence,
    Element,
    EndpointName,
    EventType,
    IdConfidence,
    LeaveReason,
    PingBucket,
    SessionStatus,
    UnitType,
)


def test_all_are_str_enum():
    for enum_cls in (
        UnitType, ActionCategory, EventType, Confidence, LeaveReason,
        SessionStatus, AccessMode, PingBucket, EndpointName, IdConfidence,
    ):
        assert issubclass(enum_cls, StrEnum)


def test_unit_type_values():
    assert UnitType.PLAYER == "Player"
    assert UnitType.OTOMO == "OtomoPal"
    assert UnitType.BASE_CAMP == "BaseCampPal"
    assert UnitType.WILD == "WildPal"
    assert UnitType.NPC == "NPC"
    assert UnitType.UNKNOWN == "Unknown"


def test_action_category_values():
    assert ActionCategory.WORKING == "working"
    assert ActionCategory.MOVING == "moving"
    assert ActionCategory.IDLE == "idle"
    assert ActionCategory.SLACKING == "slacking"
    assert ActionCategory.COMBAT == "combat"
    assert ActionCategory.SLEEPING == "sleeping"
    assert ActionCategory.EATING == "eating"
    assert ActionCategory.INCAPACITATED == "incapacitated"
    assert ActionCategory.UNKNOWN == "unknown"


def test_element_values():
    assert Element.FIRE == "fire"
    assert Element.WATER == "water"
    assert Element.GRASS == "grass"
    assert Element.ELECTRIC == "electric"
    assert Element.ICE == "ice"
    assert Element.DRAGON == "dragon"
    assert Element.DARK == "dark"
    assert Element.GROUND == "ground"
    assert Element.NEUTRAL == "neutral"
    assert issubclass(Element, StrEnum)


def test_event_type_values_are_lowercase_names():
    assert EventType.PLAYER_LEVEL_UP == "player_level_up"
    assert EventType.NEW_PLAYER == "new_player"
    assert EventType.NEW_GUILD == "new_guild"
    assert EventType.NEW_BASE == "new_base"
    assert EventType.BASE_VANISHED == "base_vanished"
    assert EventType.WORKER_DELTA == "worker_delta"
    assert EventType.WORLD_DAY_MILESTONE == "world_day_milestone"
    assert EventType.ONLINE_RECORD == "online_record"


def test_scalar_enums():
    assert Confidence.HIGH == "high"
    assert Confidence.MEDIUM == "medium"
    assert Confidence.LOW == "low"
    assert LeaveReason.OBSERVED_TIMEOUT == "observed_timeout"
    assert LeaveReason.WORLD_OFFLINE == "world_offline"
    assert LeaveReason.UNKNOWN == "unknown"
    assert SessionStatus.ACTIVE == "active"
    assert SessionStatus.CLOSED == "closed"
    assert SessionStatus.UNCERTAIN == "uncertain"
    assert AccessMode.RESTRICTED == "restricted"
    assert AccessMode.OPEN == "open"
    assert PingBucket.GOOD == "good"
    assert PingBucket.OK == "ok"
    assert PingBucket.HIGH == "high"
    assert PingBucket.UNKNOWN == "unknown"
    assert EndpointName.INFO == "info"
    assert EndpointName.METRICS == "metrics"
    assert EndpointName.PLAYERS == "players"
    assert EndpointName.SETTINGS == "settings"
    assert EndpointName.GAME_DATA == "game_data"
    assert IdConfidence.HIGH == "high"
    assert IdConfidence.LOW == "low"
