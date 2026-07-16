from pathlib import Path

from palworld_terminal.adapters.metadata_repository import MetadataRepository
from palworld_terminal.domain.enums import ActionCategory

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"


def _repo() -> MetadataRepository:
    repo = MetadataRepository(METADATA_DIR)
    repo.load()
    return repo


def test_known_pal_class_returns_zh_name():
    repo = _repo()
    assert repo.pal_name("PalDataParameter/SheepBall") == "棉悠悠"  # 官方中文名（旧值 绵绵羊 为民间译名）


def test_unknown_pal_class_returns_safe_abbrev_and_registers():
    repo = _repo()
    name = repo.pal_name("PalDataParameter/TotallyUnknownMysteryPalClass")
    assert name == "TotallyUnknownMysteryPa"[:20] or name == "TotallyUnknownMyster"
    # 缩写取最后一段前 20 字符
    assert name == "TotallyUnknownMyster"
    unknown = repo.take_unknown_classes()
    assert "PalDataParameter/TotallyUnknownMysteryPalClass" in unknown


def test_take_unknown_classes_clears_after_read():
    repo = _repo()
    repo.pal_name("PalDataParameter/UnknownX")
    first = repo.take_unknown_classes()
    assert "PalDataParameter/UnknownX" in first
    second = repo.take_unknown_classes()
    assert second == []


def test_action_category_known():
    repo = _repo()
    assert repo.action_category("EPalActionType::Work") is ActionCategory.WORKING
    assert repo.action_category("EPalActionType::Battle") is ActionCategory.COMBAT
    assert repo.action_category("EPalActionType::Sleep") is ActionCategory.SLEEPING


def test_action_category_unknown_and_none():
    repo = _repo()
    assert repo.action_category("EPalActionType::NonexistentAction") is ActionCategory.UNKNOWN
    assert repo.action_category(None) is ActionCategory.UNKNOWN
    assert repo.action_category("") is ActionCategory.UNKNOWN


def test_setting_label_known_and_missing():
    repo = _repo()
    assert repo.setting_label("ExpRate") == ("经验倍率", "×")
    assert repo.setting_label("NonexistentField") == ("NonexistentField", "")


def test_setting_display_numeric_appends_unit():
    repo = _repo()
    assert repo.setting_display("ExpRate", 1.0) == "1.0×"
    assert repo.setting_display("ServerPlayerMaxNum", 32) == "32人"


def test_setting_display_enum_maps_value():
    repo = _repo()
    assert repo.setting_display("Difficulty", "Normal") == "普通"
    assert repo.setting_display("DeathPenalty", "Item") == "掉落物品"


def test_setting_display_bool_enum_uses_lowercase_key():
    repo = _repo()
    assert repo.setting_display("bEnablePlayerToPlayerDamage", False) == "关闭"
    assert repo.setting_display("bEnablePlayerToPlayerDamage", True) == "开启"


def test_setting_display_unknown_field_and_enum_value_falls_back():
    repo = _repo()
    # 未知字段：原样字符串，不附单位
    assert repo.setting_display("NonexistentField", "x") == "x"
    # 枚举字段但值不在 enum_map：原样 token（不误映射、不冒 500）
    assert repo.setting_display("Difficulty", "Weird") == "Weird"
