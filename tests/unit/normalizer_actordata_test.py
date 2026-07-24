"""真实 game-data 契约锚点：顶层 ActorData 扁平数组按 Type 二分、类别取 UnitType、
游戏内时钟解析、ip 绝不入模型。fixture 为脱敏样本（假 ip=203.0.113.7 / 假 hex InstanceID）。"""
from dataclasses import fields
from pathlib import Path

from palworld_terminal.adapters.metadata_repository import MetadataRepository
from palworld_terminal.adapters.normalizer import normalize_game_data
from palworld_terminal.domain.enums import UnitType
from tests.fixtures.loader import load_fixture

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"

FAKE_PLAYER_IP = "203.0.113.7"


def _meta() -> MetadataRepository:
    m = MetadataRepository(METADATA_DIR)
    m.load()
    return m


def _snap():
    raw = load_fixture("live_actordata", "game-data")
    return normalize_game_data(raw, now=777, meta=_meta())


def test_actordata_container_is_read_snapshot_non_empty():
    snap = _snap()
    # 真实顶层无 characters/palboxes 键，仅 ActorData——旧解析会产空快照
    assert snap.characters, "ActorData 未被读取（characters 为空）"
    assert snap.palboxes, "ActorData 内 PalBox 未被抽取"


def test_actordata_unit_type_taken_from_UnitType_each_category_hit():
    snap = _snap()
    kinds = {c.unit_type for c in snap.characters}
    assert UnitType.PLAYER in kinds
    assert UnitType.BASE_CAMP in kinds
    assert UnitType.WILD in kinds
    assert UnitType.NPC in kinds
    # Type=="Character" 恒非 PalBox 分流；"Character" 字面绝不落成 unit_type
    assert UnitType.UNKNOWN not in kinds


def test_actordata_palbox_type_becomes_palbox_actor():
    snap = _snap()
    assert len(snap.palboxes) == 2
    guild_ids = {p.guild_id for p in snap.palboxes}
    assert guild_ids == {"G-1", "G-2"}
    # PalBox 绝不混进 characters
    assert all(c.unit_type is not UnitType.UNKNOWN for c in snap.characters)


def test_actordata_in_game_clock_parsed_from_top_level():
    snap = _snap()
    assert snap.in_game_days == 590
    assert snap.in_game_time == "17:44"


def test_actordata_ip_never_read_into_model():
    snap = _snap()
    # CharacterActor 无 ip 字段（结构层面）
    field_names = {f.name for f in fields(snap.characters[0])}
    assert "ip" not in field_names
    # 且假 ip 字符串不出现在任何 actor 的任何字段值里
    for c in snap.characters:
        for f in fields(c):
            assert getattr(c, f.name) != FAKE_PLAYER_IP
    for p in snap.palboxes:
        for f in fields(p):
            assert getattr(p, f.name) != FAKE_PLAYER_IP


def test_actordata_player_fields_mapped():
    snap = _snap()
    player = next(c for c in snap.characters if c.unit_type is UnitType.PLAYER)
    assert player.nickname == "Akari"
    assert player.player_userid == "steam_00001"
    assert player.level == 21
    assert player.guild_name == "Noema"
    assert player.pal_class == "BP_Player_Female_C"
    assert player.is_active is True
