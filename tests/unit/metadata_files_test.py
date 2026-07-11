import json
from pathlib import Path

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"

VALID_CATEGORIES = {
    "working", "moving", "idle", "combat", "sleeping", "eating",
    "incapacitated", "unknown",
}


def test_pals_file_structure_and_min_count():
    data = json.loads((METADATA_DIR / "pals.zh-CN.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    # 1-111 全图鉴 + 常见亚种, 双键形式 (PalDataParameter/<代号> 与裸代号)
    assert len(data) >= 200
    for cls, entry in data.items():
        assert isinstance(cls, str) and cls
        assert set(entry) >= {
            "pal_number", "name_zh", "name_en", "element_types", "rarity",
            "metadata_version",
        }
        assert isinstance(entry["pal_number"], int)
        assert isinstance(entry["name_zh"], str) and entry["name_zh"]
        assert isinstance(entry["element_types"], list)
        assert isinstance(entry["rarity"], int)


def test_actions_file_covers_all_categories():
    data = json.loads((METADATA_DIR / "actions.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    values = set(data.values())
    assert values <= VALID_CATEGORIES
    # 覆盖除 unknown 之外每个类别至少一条
    for cat in VALID_CATEGORIES - {"unknown"}:
        assert cat in values, f"missing action mapping for category {cat}"


def test_settings_file_covers_rules_fields():
    data = json.loads((METADATA_DIR / "settings.zh-CN.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    required = {
        "ExpRate", "PalCaptureRate", "PalSpawnNumRate", "DropItemMaxNum",
        "PalEggDefaultHatchingTime", "bEnablePlayerToPlayerDamage",
        "bEnableFriendlyFire", "ServerPlayerMaxNum", "GuildPlayerMaxNum",
        "BaseCampMaxNum",
    }
    assert required <= set(data)
    for _field, entry in data.items():
        assert "label_zh" in entry and isinstance(entry["label_zh"], str)
        assert "unit" in entry and isinstance(entry["unit"], str)
