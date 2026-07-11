import json
from pathlib import Path

from palchronicle.adapters.metadata_repository import MetadataRepository
from palchronicle.domain.enums import ActionCategory

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"
META = MetadataRepository(METADATA_DIR)
META.load()


def _load(name: str) -> dict:
    return json.loads((METADATA_DIR / name).read_text(encoding="utf-8"))


def test_pals_seed_covers_common_classes():
    for cls in ("SheepBall", "Foxparks", "Lamball", "Cattiva", "PinkCat"):
        name = META.pal_name(cls)
        assert isinstance(name, str) and name
        # 已知种子应给中文名，而非退化为原始 class 全名
        assert name != cls


def test_pals_seed_corrected_internal_codes():
    # 校正后: 内部代号 → 官方简体中文名 (数据源: 游戏 zh-Hans 文本, paldb.cc/biligame 交叉验证)
    expected = {
        "SheepBall": "棉悠悠",       # 旧值 绵绵羊 (民间译名)
        "PinkCat": "捣蛋猫",         # 旧值 喵咪嘟
        "ChickenPal": "皮皮鸡",      # 旧值 咕咕鸡
        "Monkey": "新叶猿",          # Tanzee 的真实代号 (旧 GrassMonkey 不存在)
        "Kitsunebi": "火绒狐",       # Foxparks 的真实代号 (旧 FoxFire 不存在)
        "FlyingManta": "鲁米儿",     # Celaray 的真实代号 (旧 WaterRay 不存在)
        "FlameBuffalo": "炽焰牛",    # Arsox, 旧值 焰火独角兽 有误
        "ElecPanda": "暴电熊",       # Grizzbolt, 旧值 闪电熊猫 有误
        "IceFox": "吹雪狐",          # IceFox 实为 Foxcicle, 旧值错映射到 Frostallion
        "IceHorse": "唤冬兽",        # Frostallion 的真实代号
        "JetDragon": "空涡龙",       # Jetragon 的真实代号 (旧 DragonJet 不存在)
    }
    for code, name_zh in expected.items():
        assert META.pal_name(code) == name_zh, code
        assert META.pal_name(f"PalDataParameter/{code}") == name_zh, code
    # 旧的臆造代号不应再存在
    pals = _load("pals.zh-CN.json")
    for bogus in ("GrassMonkey", "FoxFire", "WaterRay", "DragonJet"):
        assert bogus not in pals
        assert f"PalDataParameter/{bogus}" not in pals


def test_pals_seed_numbers_match_paldeck():
    pals = _load("pals.zh-CN.json")
    expected_numbers = {
        "SheepBall": 1,        # 旧值 40
        "PinkCat": 2,
        "ChickenPal": 3,       # 旧值 11
        "Kitsunebi": 5,
        "Monkey": 8,
        "Penguin": 10,         # Pengullet, 旧值 71
        "FlyingManta": 25,
        "FlameBuffalo": 42,    # 旧值 30
        "IceFox": 57,
        "ElecPanda": 103,      # 旧值 90
        "IceHorse": 110,
        "JetDragon": 111,
    }
    for code, number in expected_numbers.items():
        assert pals[code]["pal_number"] == number, code
        assert pals[f"PalDataParameter/{code}"]["pal_number"] == number, code


def test_pals_seed_expanded_with_paired_keys():
    pals = _load("pals.zh-CN.json")
    prefixed = {k.split("/", 1)[1] for k in pals if k.startswith("PalDataParameter/")}
    # 扩充下限: 至少 60 个帕鲁 (实际含 1-111 全图鉴 + 常见亚种)
    assert len(prefixed) >= 60
    # 每个 PalDataParameter/<代号> 均有等价裸键
    for code in prefixed:
        assert code in pals, f"missing bare key for {code}"
        assert pals[code] == pals[f"PalDataParameter/{code}"], code
    # 抽查若干扩充条目
    spot = {
        "Carbunclo": "翠叶鼠",       # Lifmunk
        "Ganesha": "壶小象",         # Teafant
        "NegativeKoala": "瞅什魔",   # Depresso
        "Boar": "草莽猪",            # Rushoar
        "GrassPanda": "叶胖达",      # Mossanda
        "Deer": "紫霞鹿",            # Eikthyrdeer
        "DrillGame": "碎岩龟",       # Digtoise
        "Anubis": "阿努比斯",        # Anubis
        "Kelpie_Fire": "火灵儿",     # Kelpsea Ignis (常见亚种)
    }
    for code, name_zh in spot.items():
        assert META.pal_name(code) == name_zh, code


def test_actions_seed_maps_known_actions():
    assert META.action_category("Work") == ActionCategory.WORKING
    assert META.action_category("Sleep") == ActionCategory.SLEEPING
    assert META.action_category("Combat") == ActionCategory.COMBAT
    assert META.action_category("Move") == ActionCategory.MOVING
    assert META.action_category("Eat") == ActionCategory.EATING
    assert META.action_category("Idle") == ActionCategory.IDLE
    # 扩充: 常见工作/搬运动作
    assert META.action_category("EPalWorkType::Transport") == ActionCategory.WORKING
    assert META.action_category("Transporting") == ActionCategory.WORKING
    # 未知 → UNKNOWN（不崩溃）
    assert META.action_category("ZZZ_unknown") == ActionCategory.UNKNOWN


def test_settings_seed_labels_common_fields():
    label, unit = META.setting_label("ExpRate")
    assert label and label != "ExpRate"
    label2, _ = META.setting_label("PalCaptureRate")
    assert label2 and label2 != "PalCaptureRate"
    label3, _ = META.setting_label("DeathPenalty")
    assert label3 and label3 != "DeathPenalty"


def test_settings_seed_covers_default_ini_fields():
    # 键名拼写以官方 DefaultPalWorldSettings.ini 为准 (官方拼写 Decreace / HP 与 Hp 混用)
    required = (
        "Difficulty",
        "DayTimeSpeedRate", "NightTimeSpeedRate",
        "PalDamageRateAttack", "PalDamageRateDefense",
        "PlayerDamageRateAttack", "PlayerDamageRateDefense",
        "PlayerStomachDecreaceRate", "PlayerStaminaDecreaceRate",
        "PlayerAutoHPRegeneRate", "PlayerAutoHpRegeneRateInSleep",
        "PalStomachDecreaceRate", "PalStaminaDecreaceRate",
        "PalAutoHPRegeneRate", "PalAutoHpRegeneRateInSleep",
        "WorkSpeedRate", "BuildObjectDamageRate", "CollectionDropRate",
        "EnemyDropItemRate", "ItemWeightRate", "CoopPlayerMaxNum",
        "BaseCampWorkerMaxNum", "AutoSaveSpan",
        "bIsMultiplay", "bIsPvP", "bEnableFastTravel", "bEnableInvaderEnemy",
        "RESTAPIEnabled", "RESTAPIPort", "bShowPlayerList",
    )
    for field in required:
        label, _ = META.setting_label(field)
        assert label and label != field, field
    settings = _load("settings.zh-CN.json")
    assert len(settings) >= 40
    # 布尔键统一携带 enum_map(true/false → 开启/关闭 类文案)
    for field, entry in settings.items():
        if field.startswith("b") or field in ("RESTAPIEnabled", "RCONEnabled"):
            assert "enum_map" in entry, field
            assert set(entry["enum_map"]) >= {"true", "false"}, field
