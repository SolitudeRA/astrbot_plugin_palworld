from pathlib import Path

from palchronicle.adapters.metadata_repository import MetadataRepository
from palchronicle.adapters.normalizer import normalize_game_data
from palchronicle.domain.enums import ActionCategory, UnitType

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"


def _meta() -> MetadataRepository:
    m = MetadataRepository(METADATA_DIR)
    m.load()
    return m


def test_normalize_game_data_mixed_case_and_str_bool():
    raw = {
        "ServerFps": 55, "AverageFps": 52,
        "Characters": [
            {
                "Type": "Player", "InstanceID": "I-1", "NickName": "Alice",
                "userid": "u-1", "Level": "20", "HP": "900", "MaxHP": 1000,
                "GuildID": "g-1", "GuildName": "Noema",
                "Action": "EPalActionType::Work", "AIAction": "EPalAIActionType::MoveTo",
                "LocationX": "100.5", "LocationY": "-200.25", "LocationZ": 10,
                "IsActive": "true",
            }
        ],
        "PalBoxes": [
            {"GuildID": "g-1", "GuildName": "Noema", "Class": "PalDataParameter/SheepBall",
             "LocationX": 100, "LocationY": 200, "LocationZ": 5}
        ],
    }
    meta = _meta()
    snap = normalize_game_data(raw, now=500, meta=meta)
    assert snap.observed_at == 500
    assert snap.fps == 55.0
    assert snap.average_fps == 52.0
    assert len(snap.characters) == 1
    c = snap.characters[0]
    assert c.unit_type is UnitType.PLAYER
    assert c.instance_id == "I-1"
    assert c.nickname == "Alice"
    assert c.player_userid == "u-1"
    assert c.level == 20
    assert c.hp == 900
    assert c.max_hp == 1000
    assert c.guild_id == "g-1"
    assert c.guild_name == "Noema"
    assert c.action is ActionCategory.WORKING
    assert c.ai_action is ActionCategory.MOVING
    assert c.x == 100.5
    assert c.y == -200.25
    assert c.z == 10.0
    assert c.is_active is True
    assert len(snap.palboxes) == 1
    assert snap.palboxes[0].guild_id == "g-1"
    assert snap.palboxes[0].x == 100.0


def test_normalize_game_data_lowercase_keys():
    raw = {
        "characters": [
            {"type": "BaseCampPal", "class": "PalDataParameter/ChickenPal",
             "hp": 50, "maxhp": 100, "guildid": "g-2",
             "action": "EPalActionType::Wait", "isactive": "false",
             "locationx": 1, "locationy": 2, "locationz": 3}
        ]
    }
    snap = normalize_game_data(raw, now=1, meta=_meta())
    c = snap.characters[0]
    assert c.unit_type is UnitType.BASE_CAMP
    assert c.pal_class == "PalDataParameter/ChickenPal"
    assert c.action is ActionCategory.IDLE
    assert c.is_active is False


def test_normalize_game_data_unknown_class_registered_not_dropped():
    raw = {
        "characters": [
            {"type": "WildPal", "class": "PalDataParameter/BrandNewPal_2099",
             "action": "EPalActionType::Move", "isactive": True,
             "locationx": 0, "locationy": 0, "locationz": 0}
        ]
    }
    meta = _meta()
    snap = normalize_game_data(raw, now=1, meta=meta)
    # 整快照未丢, actor 仍在
    assert len(snap.characters) == 1
    assert "PalDataParameter/BrandNewPal_2099" in snap.unknown_classes


def test_normalize_game_data_missing_and_empty_fields():
    raw = {"characters": [{"type": "NPC"}]}
    snap = normalize_game_data(raw, now=1, meta=_meta())
    c = snap.characters[0]
    assert c.unit_type is UnitType.NPC
    assert c.level is None
    assert c.hp is None
    assert c.guild_id is None
    assert c.action is ActionCategory.UNKNOWN
    assert c.ai_action is ActionCategory.UNKNOWN
    assert c.x is None
    assert c.is_active is False


def test_normalize_game_data_unknown_unit_type():
    raw = {"characters": [{"type": "SomethingWeird"}]}
    snap = normalize_game_data(raw, now=1, meta=_meta())
    assert snap.characters[0].unit_type is UnitType.UNKNOWN


def test_normalize_game_data_palbox_missing_coords_skipped():
    raw = {"palboxes": [{"guildid": "g-9", "class": "PalDataParameter/SheepBall"}]}
    snap = normalize_game_data(raw, now=1, meta=_meta())
    assert snap.palboxes == []


def test_normalize_game_data_empty_payload():
    snap = normalize_game_data({}, now=42, meta=_meta())
    assert snap.observed_at == 42
    assert snap.characters == []
    assert snap.palboxes == []
    assert snap.unknown_classes == []
