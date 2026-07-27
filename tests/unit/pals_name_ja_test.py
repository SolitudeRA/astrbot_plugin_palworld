"""帕鲁元数据日文名 name_ja 回填契约（i18n Phase 1 / Task 14）。

三条守卫：
1. 覆盖率——全部条目 name_ja 非空，或 name_en 在（当前为空的）豁免表。
2. 同物种一致性——同一 name_en 的所有键（PalDataParameter/X 与裸键/元素亚种别名）
   name_ja 完全相同。
3. 锚点抽查——招牌帕鲁硬断言，锁死数据未被错填。
"""
import json
from collections import defaultdict
from pathlib import Path

METADATA_DIR = Path(__file__).resolve().parents[2] / "metadata"

# 全部 167 独立物种均有 paldb.cc 官方日文名——无自造占位种，豁免表为空。
EXEMPTION: frozenset[str] = frozenset()


def _pals() -> dict[str, dict]:
    return json.loads((METADATA_DIR / "pals.json").read_text(encoding="utf-8"))


def test_all_pals_have_name_ja():
    pals = _pals()
    missing = [
        key
        for key, entry in pals.items()
        if not entry.get("name_ja") and entry["name_en"] not in EXEMPTION
    ]
    assert not missing, f"缺 name_ja 的键：{missing}"


def test_same_species_name_ja_consistent():
    pals = _pals()
    by_species: dict[str, set[str]] = defaultdict(set)
    keys_by_species: dict[str, list[str]] = defaultdict(list)
    for key, entry in pals.items():
        name_en = entry["name_en"]
        by_species[name_en].add(entry.get("name_ja", ""))
        keys_by_species[name_en].append(key)
    inconsistent = {
        name_en: sorted(values)
        for name_en, values in by_species.items()
        if len(values) != 1
    }
    assert not inconsistent, f"同物种 name_ja 不一致：{inconsistent}"


def test_name_ja_spot_check():
    pals = _pals()
    by_en = {entry["name_en"]: entry.get("name_ja") for entry in pals.values()}
    expected = {
        "Lamball": "モコロン",
        "Anubis": "アヌビス",
        "Jetragon": "ジェッドラン",
        "Chikipi": "タマコッコ",
    }
    for name_en, name_ja in expected.items():
        assert by_en.get(name_en) == name_ja, f"{name_en} 期望 {name_ja}，实得 {by_en.get(name_en)}"
