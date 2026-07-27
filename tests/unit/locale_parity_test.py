"""三语键集奇偶校验（i18n Phase 1 · §6）：locale JSON 之间键集 + 每键占位符集严格相等。

漏译（缺键）即红；占位符名称/数量与 zh-CN 基线不一致即红（位置可重排，集合须等）。
Phase 1 以 zh↔en 两文件生效；T11 扩三文件（ja 加入 LOCALES 后自动纳入笛卡尔对）。
"""
import json
import string
from pathlib import Path

import pytest

_LOCALES_DIR = Path(__file__).resolve().parents[2] / "palworld_terminal" / "presentation" / "locales"

# 参与校验的 locale（zh-CN 为唯一基线）。ja 上线后追加即自动纳入两两比对。
LOCALES = ("zh-CN", "en", "ja")


def _load(locale: str) -> dict[str, str]:
    return json.loads((_LOCALES_DIR / f"{locale}.json").read_text(encoding="utf-8"))


def _placeholders(template: str) -> set[str]:
    """经 string.Formatter().parse 抽取 {placeholder} 名称集（忽略纯字面段）。

    field_name 为 None 的是尾随字面文本；`{h}时{mm}分` 之类多占位串抽出 {h, mm}。
    取 field_name 的根名（切掉 .attr / [idx]），本套键均为简单名，等价于全名。
    """
    names: set[str] = set()
    for _literal, field_name, _spec, _conv in string.Formatter().parse(template):
        if field_name is None:
            continue
        root = field_name.split(".")[0].split("[")[0]
        names.add(root)
    return names


@pytest.mark.parametrize("locale", [loc for loc in LOCALES if loc != "zh-CN"])
def test_key_sets_equal_to_zh_baseline(locale: str):
    base = _load("zh-CN")
    other = _load(locale)
    missing = set(base) - set(other)
    extra = set(other) - set(base)
    assert not missing, f"{locale} 缺键（漏译）：{sorted(missing)}"
    assert not extra, f"{locale} 多余键（zh 基线无）：{sorted(extra)}"


@pytest.mark.parametrize("locale", [loc for loc in LOCALES if loc != "zh-CN"])
def test_placeholder_sets_match_per_key(locale: str):
    base = _load("zh-CN")
    other = _load(locale)
    mismatched: dict[str, tuple[set[str], set[str]]] = {}
    for key, zh_template in base.items():
        if key not in other:
            continue  # 键集相等由上一测试专责
        zh_ph = _placeholders(zh_template)
        other_ph = _placeholders(other[key])
        if zh_ph != other_ph:
            mismatched[key] = (zh_ph, other_ph)
    assert not mismatched, f"{locale} 占位符集不一致：{mismatched}"
