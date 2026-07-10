from pathlib import Path

from palchronicle.adapters.metadata_repository import MetadataRepository
from palchronicle.domain.enums import ActionCategory

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"


def _repo() -> MetadataRepository:
    repo = MetadataRepository(METADATA_DIR)
    repo.load()
    return repo


def test_known_pal_class_returns_zh_name():
    repo = _repo()
    assert repo.pal_name("PalDataParameter/SheepBall") == "绵绵羊"


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
