import dataclasses

from palchronicle.domain.enums import ActionCategory, UnitType
from palchronicle.domain.models import (
    CharacterActor,
    GameDataSnapshot,
    InfoSnapshot,
    MetricsSnapshot,
    PalBoxActor,
    PlayerRow,
    PlayersSnapshot,
)


def _field_names(cls):
    return [f.name for f in dataclasses.fields(cls)]


def test_character_actor_fields():
    assert _field_names(CharacterActor) == [
        "unit_type", "instance_id", "nickname", "trainer_instance_id",
        "trainer_nickname", "player_userid", "level", "hp", "max_hp",
        "guild_id", "guild_name", "pal_class", "action", "ai_action",
        "x", "y", "z", "is_active",
    ]
    a = CharacterActor(
        unit_type=UnitType.PLAYER, instance_id="i1", nickname="Bob",
        trainer_instance_id=None, trainer_nickname=None,
        player_userid="uid", level=10, hp=100, max_hp=100, guild_id="g1",
        guild_name="G", pal_class=None, action=ActionCategory.IDLE,
        ai_action=ActionCategory.UNKNOWN, x=1.0, y=2.0, z=3.0, is_active=True,
    )
    assert a.unit_type is UnitType.PLAYER
    assert a.action is ActionCategory.IDLE


def test_palbox_actor_fields():
    assert _field_names(PalBoxActor) == [
        "guild_id", "guild_name", "pal_class", "x", "y", "z",
    ]
    pb = PalBoxActor(guild_id="g", guild_name="G", pal_class="PalBox", x=1.0, y=2.0, z=3.0)
    assert pb.x == 1.0


def test_game_data_snapshot_fields():
    assert _field_names(GameDataSnapshot) == [
        "observed_at", "fps", "average_fps", "characters", "palboxes",
        "unknown_classes",
    ]
    gd = GameDataSnapshot(
        observed_at=1, fps=60.0, average_fps=58.0, characters=[],
        palboxes=[], unknown_classes=[],
    )
    assert gd.characters == []


def test_player_row_fields():
    assert _field_names(PlayerRow) == [
        "userid", "player_id", "name", "level", "ping", "building_count",
    ]
    r = PlayerRow(userid="h", player_id=None, name="n", level=3, ping=42.0, building_count=1)
    assert r.name == "n"


def test_players_snapshot_fields():
    assert _field_names(PlayersSnapshot) == ["observed_at", "players"]


def test_metrics_snapshot_fields():
    assert _field_names(MetricsSnapshot) == [
        "observed_at", "fps", "frame_time", "online", "max_players",
        "uptime", "basecamp_count", "days",
    ]


def test_info_snapshot_fields():
    assert _field_names(InfoSnapshot) == [
        "observed_at", "version", "server_name", "description", "worldguid",
    ]
