from pathlib import Path

from palchronicle.adapters.metadata_repository import MetadataRepository
from palchronicle.domain.enums import ActionCategory

META = MetadataRepository(Path(__file__).resolve().parents[2] / "metadata")
META.load()


def test_pals_seed_covers_common_classes():
    for cls in ("SheepBall", "Foxparks", "Lamball", "Cattiva", "PinkCat"):
        name = META.pal_name(cls)
        assert isinstance(name, str) and name
        # 已知种子应给中文名，而非退化为原始 class 全名
        assert name != cls or cls == "PinkCat"  # PinkCat 为反例(内部名)时容许


def test_actions_seed_maps_known_actions():
    assert META.action_category("Work") == ActionCategory.WORKING
    assert META.action_category("Sleep") == ActionCategory.SLEEPING
    assert META.action_category("Combat") == ActionCategory.COMBAT
    assert META.action_category("Move") == ActionCategory.MOVING
    assert META.action_category("Eat") == ActionCategory.EATING
    assert META.action_category("Idle") == ActionCategory.IDLE
    # 未知 → UNKNOWN（不崩溃）
    assert META.action_category("ZZZ_unknown") == ActionCategory.UNKNOWN


def test_settings_seed_labels_common_fields():
    label, unit = META.setting_label("ExpRate")
    assert label and label != "ExpRate"
    label2, _ = META.setting_label("PalCaptureRate")
    assert label2 and label2 != "PalCaptureRate"
    label3, _ = META.setting_label("DeathPenalty")
    assert label3 and label3 != "DeathPenalty"
