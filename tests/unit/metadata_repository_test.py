from pathlib import Path

from palworld_terminal.adapters.metadata_repository import MetadataRepository
from palworld_terminal.domain.enums import ActionCategory

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"


def _repo() -> MetadataRepository:
    repo = MetadataRepository(METADATA_DIR)
    repo.load()
    return repo


def _repo_locale(locale: str) -> MetadataRepository:
    repo = MetadataRepository(METADATA_DIR, locale)
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


# ---- T13：settings 三语（label_ja/label_en + enum_map 嵌套三语 + unit 三语）----

def test_setting_label_locale_en():
    repo = _repo_locale("en")
    assert repo.setting_label("Difficulty") == ("Difficulty", "")
    assert repo.setting_label("ExpRate") == ("EXP Rate", "×")
    assert repo.setting_label("ServerPlayerMaxNum") == ("Max Players", " players")


def test_setting_label_locale_ja():
    repo = _repo_locale("ja")
    assert repo.setting_label("Difficulty") == ("難易度", "")
    assert repo.setting_label("ExpRate") == ("経験値倍率", "×")
    # unit_ja 缺省 → 回退基准 unit（日本語も「人」）
    assert repo.setting_label("ServerPlayerMaxNum") == ("サーバーの最大人数", "人")


def test_setting_display_enum_locale_en():
    repo = _repo_locale("en")
    assert repo.setting_display("bHardcore", True) == "On"
    assert repo.setting_display("bHardcore", False) == "Off"
    assert repo.setting_display("Difficulty", "Normal") == "Normal"
    assert repo.setting_display("DeathPenalty", "Item") == "Drop items"
    assert repo.setting_display("LogFormatType", "Json") == "JSON"


def test_setting_display_enum_locale_ja():
    repo = _repo_locale("ja")
    assert repo.setting_display("bHardcore", True) == "オン"
    assert repo.setting_display("bHardcore", False) == "オフ"
    assert repo.setting_display("Difficulty", "Normal") == "ノーマル"
    assert repo.setting_display("DeathPenalty", "Item") == "アイテムのみ"


def test_setting_display_unit_locale():
    # en：拼接后缀本地化（人 → " players"）；数值倍率 × 语言中立
    en = _repo_locale("en")
    assert en.setting_display("ServerPlayerMaxNum", 32) == "32 players"
    assert en.setting_display("ExpRate", 1.0) == "1.0×"
    # ja：人 缺 unit_ja → 回退基准「人」；秒 同理
    ja = _repo_locale("ja")
    assert ja.setting_display("ServerPlayerMaxNum", 32) == "32人"


def test_setting_zh_values_unchanged_under_new_structure():
    # 双保险：结构改造后 zh 现值逐字不变（既有断言之外再钉一遍关键面）
    repo = _repo_locale("zh-CN")
    assert repo.setting_label("Difficulty") == ("游戏难度", "")
    assert repo.setting_label("ServerPlayerMaxNum") == ("最大玩家数", "人")
    assert repo.setting_display("bHardcore", True) == "开启"
    assert repo.setting_display("bHardcore", False) == "关闭"
    assert repo.setting_display("Difficulty", "Normal") == "普通"
    assert repo.setting_display("DeathPenalty", "ItemAndEquipment") == "掉落物品与装备"
    assert repo.setting_display("ServerPlayerMaxNum", 32) == "32人"
