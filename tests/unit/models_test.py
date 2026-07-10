import dataclasses

from palchronicle.domain.enums import (
    Confidence,
    EventType,
    IdConfidence,
    LeaveReason,
    PingBucket,
    SessionStatus,
)
from palchronicle.domain.models import (
    Base,
    BaseObservation,
    Guild,
    PalBox,
    PlayerIdentity,
    PlayerObservation,
    PlayerSession,
    World,
    WorldEvent,
    WorldMetric,
)


def _field_names(cls):
    return [f.name for f in dataclasses.fields(cls)]


def test_all_models_are_slotted_dataclasses():
    for cls in (
        World, PlayerIdentity, PlayerObservation, PlayerSession, Guild,
        PalBox, Base, BaseObservation, WorldMetric, WorldEvent,
    ):
        assert dataclasses.is_dataclass(cls)
        assert not hasattr(cls, "__dict__") or "__slots__" in cls.__dict__


def test_world_fields_and_construct():
    assert _field_names(World) == [
        "world_id", "server_id", "worldguid", "epoch", "server_name",
        "version", "first_seen_at", "last_seen_at", "current_day",
    ]
    w = World(
        world_id="s1:guid:0", server_id="s1", worldguid="guid", epoch=0,
        server_name="S", version="v", first_seen_at=100, last_seen_at=200,
        current_day=3,
    )
    assert w.world_id == "s1:guid:0"


def test_player_identity_fields():
    assert _field_names(PlayerIdentity) == [
        "player_key", "world_id", "latest_name", "first_seen_at",
        "last_seen_at", "latest_level", "latest_guild_key", "id_confidence",
    ]
    p = PlayerIdentity(
        player_key="k", world_id="w", latest_name="n", first_seen_at=1,
        last_seen_at=2, latest_level=5, latest_guild_key=None,
        id_confidence=IdConfidence.HIGH,
    )
    assert p.id_confidence is IdConfidence.HIGH


def test_player_observation_fields():
    assert _field_names(PlayerObservation) == [
        "observed_at", "world_id", "player_key", "name", "level",
        "ping_bucket", "building_count", "guild_key", "position_cell",
        "companion_class",
    ]
    o = PlayerObservation(
        observed_at=1, world_id="w", player_key="k", name="n", level=3,
        ping_bucket=PingBucket.GOOD, building_count=2, guild_key=None,
        position_cell=None, companion_class=None,
    )
    assert o.ping_bucket is PingBucket.GOOD


def test_player_session_fields():
    assert _field_names(PlayerSession) == [
        "id", "world_id", "player_key", "joined_at", "last_confirmed_at",
        "left_at", "observed_seconds", "status", "leave_reason",
    ]
    s = PlayerSession(
        id=None, world_id="w", player_key="k", joined_at=1,
        last_confirmed_at=1, left_at=None, observed_seconds=0,
        status=SessionStatus.ACTIVE, leave_reason=None,
    )
    assert s.status is SessionStatus.ACTIVE
    assert s.leave_reason is None


def test_guild_fields():
    assert _field_names(Guild) == [
        "guild_key", "world_id", "latest_name", "first_seen_at",
        "last_seen_at", "observed_member_count", "palbox_count",
        "base_pal_count",
    ]


def test_palbox_fields():
    assert _field_names(PalBox) == [
        "palbox_key", "world_id", "guild_key", "position_cell",
        "first_seen_at", "last_seen_at", "status",
    ]


def test_base_fields():
    assert _field_names(Base) == [
        "base_key", "world_id", "palbox_key", "display_name", "guild_key",
        "confidence", "locked_by_admin", "hidden", "first_seen_at",
        "last_seen_at",
    ]
    b = Base(
        base_key="b", world_id="w", palbox_key="pb", display_name=None,
        guild_key=None, confidence=Confidence.MEDIUM, locked_by_admin=False,
        hidden=False, first_seen_at=1, last_seen_at=2,
    )
    assert b.confidence is Confidence.MEDIUM


def test_base_observation_fields():
    assert _field_names(BaseObservation) == [
        "base_key", "world_id", "observed_at", "worker_count",
        "active_count", "average_level", "average_hp_ratio",
        "action_distribution",
    ]
    o = BaseObservation(
        base_key="b", world_id="w", observed_at=1, worker_count=4,
        active_count=3, average_level=12.5, average_hp_ratio=0.9,
        action_distribution={"working": 3},
    )
    assert o.action_distribution == {"working": 3}


def test_world_metric_fields():
    assert _field_names(WorldMetric) == [
        "world_id", "observed_at", "fps", "frame_time", "online_players",
        "world_day", "basecamp_count", "max_players",
    ]


def test_world_event_fields():
    assert _field_names(WorldEvent) == [
        "event_id", "world_id", "event_type", "subject_type", "subject_key",
        "occurred_at", "confirmed_at", "payload", "visibility",
        "confidence", "dedup_key",
    ]
    e = WorldEvent(
        event_id=None, world_id="w", event_type=EventType.NEW_PLAYER,
        subject_type="player", subject_key="k", occurred_at=1,
        confirmed_at=1, payload={"a": 1}, visibility="public",
        confidence=Confidence.HIGH, dedup_key="w|new_player|k",
    )
    assert e.event_type is EventType.NEW_PLAYER
    assert e.payload == {"a": 1}
