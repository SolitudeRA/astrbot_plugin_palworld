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
