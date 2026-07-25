"""真实帕鲁 Class（BP_<Name>_C）→ 中文名 + 元素覆盖。

规范化：查找前 strip BP_ 前缀 + _C 后缀，命中现有键；对 strip 后仍不命中的实测物种
显式补条目。element(class) 复用 element_types，未收录→"unknown" 优雅降级（不报错）。"""
from pathlib import Path

from palworld_terminal.adapters.metadata_repository import MetadataRepository

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"

# 实服探测所得帕鲁 Class 全集（子集）——重建后应全部命中中文名。
MEASURED_CLASSES = (
    "BP_ChickenPal_C",
    "BP_LotusDragon_C",
    "BP_ThunderDragonMan_C",
    "BP_BlueSkyDragon_C",
    "BP_GhostDragon_Fire_C",
    "BP_LegendDeer_C",
    "BP_ClownRabbit_C",
    "BP_SnowTigerBeastman_C",
    "BP_KabukiMan_C",
    "BP_DomeArmorDragon_C",
    "BP_ThunderFluffyBird_C",
    "BP_MonochromeQueen_C",
    "BP_FlowerDoll_C",
    "BP_SweetsSheep_C",
    "BP_IceNarwhal_BOSS_C",
)


def _repo() -> MetadataRepository:
    repo = MetadataRepository(METADATA_DIR)
    repo.load()
    return repo


def test_bp_class_strip_hits_existing_zh_name():
    repo = _repo()
    # BP_ 前缀 + _C 后缀 strip 后命中现有裸键
    assert repo.pal_name("BP_ChickenPal_C") == "皮皮鸡"
    assert repo.pal_name("BP_SweetsSheep_C") == "棉花糖"


def test_measured_species_all_resolve_to_zh_name():
    repo = _repo()
    for cls in MEASURED_CLASSES:
        name = repo.pal_name(cls)
        # 命中真实中文名，而非退化为 BP_ 原始 class 缩写
        assert name and not name.startswith("BP_"), cls


def test_element_lookup_required_species():
    repo = _repo()
    # 硬断言（spec Step 1）：LotusDragon=Dinossom→grass
    assert repo.element("BP_LotusDragon_C") == "grass"
    # 元素由 code 语义高置信派生
    assert repo.element("BP_ThunderDragonMan_C") == "dragon"
    assert repo.element("BP_SnowTigerBeastman_C") == "ice"
    assert repo.element("BP_ThunderFluffyBird_C") == "electric"
    assert repo.element("BP_IceNarwhal_BOSS_C") == "ice"


def test_element_unknown_degrades_gracefully():
    repo = _repo()
    # 未收录物种 → "unknown"（不报错）
    assert repo.element("BP_TotallyUnknownMysteryPal_C") == "unknown"
    # Player 非帕鲁 → 优雅降级
    assert repo.element("BP_Player_Female_C") == "unknown"
    assert repo.element(None) == "unknown"


def test_raw_bare_code_still_resolves():
    repo = _repo()
    # 规范名裸键仍可直查（不依赖 BP_/_C 包裹）——与 BP_*_C 形指向同一条目
    assert repo.pal_name("LotusDragon") == repo.pal_name("BP_LotusDragon_C")
    assert repo.element("LotusDragon") == "grass"


def test_cosmetic_variant_normalization():
    """外观/头目变体后缀（_BOSS / _Skin### / _otomo）归一到基础种：同名同元素。

    实服随身/野生/据点常见 BP_<Base>_BOSS_C、BP_<Base>_Skin001_C、BP_<Base>_BOSS_Skin001_C、
    BP_<Base>_BOSS_otomo_C 等形，旧 strip 只去 BP_/_C → 落"未知"。此归一只剥外观后缀。"""
    repo = _repo()
    # 头目变体 → 基础种（空涡龙=JetDragon 在库）
    assert repo.pal_name("BP_JetDragon_BOSS_C") == "空涡龙"
    assert repo.element("BP_JetDragon_BOSS_C") == "dragon"
    # 皮肤变体 + 头目+皮肤组合 + 头目+otomo 组合
    assert repo.pal_name("BP_JetDragon_Skin001_C") == "空涡龙"
    assert repo.pal_name("BP_JetDragon_BOSS_Skin001_C") == "空涡龙"
    assert repo.pal_name("BP_JetDragon_BOSS_otomo_C") == "空涡龙"
    assert repo.pal_name("BP_ChickenPal_BOSS_C") == "皮皮鸡"


# 实服探测物种 → 官方简体中文名 + 主元素（Phase B 回填：paldb.cc 简中本地化 + 对抗验证）。
# 覆盖基种 / 外观头目变体 / 元素亚种 / 修正的直译占位（默世鹿等，原名/元素错）。
_BACKFILLED = {
    "BP_Mothman_C": ("暮尘蛾", "grass"),
    "BP_Mothman_BOSS_C": ("暮尘蛾", "grass"),          # 头目变体归一
    "BP_SnakeGirl_C": ("梅杜娜", "dark"),
    "BP_GhostDragon_C": ("灵曦龙", "dragon"),
    "BP_WingGolem_C": ("泰锋", "ground"),
    "BP_WingGolem_Fire_C": ("丹烽", "fire"),           # 火元素亚种（独立条目，非归一）
    "BP_KingSunfish_Thunder_C": ("曼波皇", "water"),   # 雷元素亚种
    "BP_WhiteDeer_Dark_BOSS_C": ("织夜鹿", "dark"),    # 暗亚种 + 头目变体
    "BP_LegendDeer_C": ("默世鹿", "neutral"),          # 修正：原「传说角鹿」直译 + 空元素
    "BP_ClownRabbit_C": ("拉比耶尔", "fire"),          # 修正：原「小丑兔」直译 + 空元素
    "BP_KabukiMan_C": ("燎火舞伶", "fire"),            # 修正：原「歌舞伎武者」直译 + 空元素
    "BP_MonochromeQueen_C": ("墨罗娜", "dark"),        # 修正：原「黑白女王」直译 + 空元素
}


def test_backfilled_species_resolve_name_and_element():
    repo = _repo()
    for cls, (name, elem) in _BACKFILLED.items():
        assert repo.pal_name(cls) == name, cls
        assert repo.element(cls) == elem, cls
        assert not repo.pal_name(cls).startswith("BP_"), cls   # 绝不退化原始类名


def test_element_suffix_not_stripped_as_cosmetic():
    """元素后缀（_Dark / _Fire / _Neutral …）绝不当外观后缀剥掉——剥了会指向错种/错元素。

    用**复合形**（元素后缀 + 外观后缀）确保真正触达 _strip_cosmetic_variants（先剥 _BOSS 到
    元素亚种、_Dark/_Fire 须留住），并用**元素对照**强断言——基种与元素亚种元素不同，误剥即抓。"""
    repo = _repo()
    # _Dark 保留：BOSS 变体归一到 LilyQueen_Dark（而非 LilyQueen），命中且非退化
    lily = repo.pal_name("BP_LilyQueen_Dark_BOSS_C")
    assert lily == repo.pal_name("BP_LilyQueen_Dark_C")
    assert not lily.startswith("BP_")
    # _Fire 保留：BP_GhostDragon_Fire_BOSS_C 剥 _BOSS 后命中 GhostDragon_Fire（焰魂龙/fire），
    # 绝不连 _Fire 一起剥成基种 GhostDragon（灵曦龙/dragon）。元素对照锁死：误剥则 fire→dragon。
    assert repo.element("BP_GhostDragon_Fire_BOSS_C") == "fire"
    assert repo.element("BP_GhostDragon_C") == "dragon"        # 基种（元素不同，形成对照）
    assert repo.pal_name("BP_GhostDragon_Fire_BOSS_C") == "焰魂龙"
