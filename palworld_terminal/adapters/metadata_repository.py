from __future__ import annotations

import json
import re
from pathlib import Path

from ..domain.enums import ActionCategory

# 外观/头目变体后缀（大小写不敏感）：剥到基础种时只吃这些「同种同元素」的尾段。
# 元素后缀（Dark/Fire/Water/Neutral…）绝不在列——它们是不同亚种/不同元素，剥了会指错种。
_COSMETIC_SUFFIX = re.compile(r"^(?:BOSS|Skin\d+|otomo)$", re.IGNORECASE)


# 帕鲁名字段的 locale fallback 链：从所选语言起沿 name_ja→name_en→name_zh 逐级回退。
# 所选字段缺失/值空即降到下一级；非 ja/en 的 locale（含 zh-CN）只取 name_zh。
_NAME_FALLBACK: dict[str, tuple[str, ...]] = {
    "ja": ("name_ja", "name_en", "name_zh"),
    "en": ("name_en", "name_zh"),
}
_DEFAULT_NAME_FIELDS: tuple[str, ...] = ("name_zh",)


class MetadataRepository:
    def __init__(self, metadata_dir: Path, locale: str = "zh-CN") -> None:
        self._dir = Path(metadata_dir)
        # locale 供三语选字段用（settings 三语字段归 T13，此处先留属性）。
        self._locale = locale
        self._name_fields = _NAME_FALLBACK.get(locale, _DEFAULT_NAME_FIELDS)
        self._pals: dict[str, dict] = {}
        self._actions: dict[str, str] = {}
        self._settings: dict[str, dict] = {}
        self._unknown: list[str] = []
        self._unknown_seen: set[str] = set()

    def load(self) -> None:
        self._pals = self._read("pals.json")
        self._actions = self._read("actions.json")
        self._settings = self._read("settings.json")

    def _read(self, name: str) -> dict:
        path = self._dir / name
        return json.loads(path.read_text(encoding="utf-8"))

    def pal_name(self, internal_class: str) -> str:
        entry = self._lookup_pal(internal_class)
        if entry is not None:
            name = self._pick_name(entry)
            if name:
                return name
        self._register_unknown(internal_class)
        return self._safe_abbrev(internal_class)

    def _pick_name(self, entry: dict) -> str:
        """按当前 locale 的字段 fallback 链取帕鲁名（ja→en→zh / en→zh / zh）。

        所选字段缺失或值空时回退下一级；全链皆空返回 ""，交由 pal_name 走
        既有 _safe_abbrev 兜底路径（与旧行为一致）。"""
        for field in self._name_fields:
            value = entry.get(field)
            if value:
                return str(value)
        return ""

    def element(self, internal_class: str | None) -> str:
        """帕鲁 Class → 首要元素英文键（fire/water/…/neutral）。

        复用 pals.json 的 element_types；真实 Class 为 BP_<Name>_C，查找前做
        与 pal_name 一致的 strip 规范化。未收录/无元素 → "unknown" 优雅降级（不报错、
        不 register，供展示层安全消费）。"""
        if not internal_class:
            return "unknown"
        entry = self._lookup_pal(internal_class)
        if entry is None:
            return "unknown"
        types = entry.get("element_types") or []
        if not types:
            return "unknown"
        return str(types[0])

    def _lookup_pal(self, internal_class: str) -> dict | None:
        """帕鲁条目查找：先精确命中（含旧 PalDataParameter/ 与裸键），未命中再对真实
        BP_<Name>_C 形做 strip 规范化重试（BP_ChickenPal_C → ChickenPal），仍不中再
        剥外观/头目变体后缀归一到基础种（BP_JetDragon_BOSS_C → JetDragon）。"""
        entry = self._pals.get(internal_class)
        if entry is not None:
            return entry
        normalized = self._normalize_pal_class(internal_class)
        if normalized != internal_class:
            entry = self._pals.get(normalized)
            if entry is not None:
                return entry
        # 外观/头目变体后缀（_BOSS/_Skin###/_otomo）归一到基础种：同名同元素。
        # 元素后缀（_Dark/_Fire…）不剥——那是独立亚种，剥了会指错种/错元素。
        base = self._strip_cosmetic_variants(normalized)
        if base != normalized:
            return self._pals.get(base)
        return None

    @staticmethod
    def _normalize_pal_class(internal_class: str) -> str:
        s = internal_class
        if s.startswith("BP_"):
            s = s[3:]
        if s.endswith("_C"):
            s = s[:-2]
        return s

    @staticmethod
    def _strip_cosmetic_variants(normalized: str) -> str:
        """从规范化名（已去 BP_/_C）尾部逐段剥外观/头目后缀（BOSS/Skin###/otomo）到基础种。

        仅剥 `_COSMETIC_SUFFIX` 命中的尾段：JetDragon_BOSS→JetDragon、
        JetDragon_BOSS_Skin001→JetDragon、KingWhale_BOSS_otomo→KingWhale。
        LilyQueen_Dark_BOSS→LilyQueen_Dark（_Dark 是元素亚种，保留）。"""
        parts = normalized.split("_")
        while len(parts) > 1 and _COSMETIC_SUFFIX.match(parts[-1]):
            parts.pop()
        return "_".join(parts)

    def action_category(self, raw_action: str | None) -> ActionCategory:
        if not raw_action:
            return ActionCategory.UNKNOWN
        value = self._actions.get(raw_action)
        if value is None:
            return ActionCategory.UNKNOWN
        return ActionCategory(value)

    def setting_label(self, field: str) -> tuple[str, str]:
        entry = self._settings.get(field)
        if entry is None:
            return (field, "")
        return (entry.get("label_zh", field), entry.get("unit", ""))

    def setting_display(self, field: str, value) -> str:
        """把原始设置值渲染为展示串：enum_map 措辞优先，否则 value+unit。

        `/pal world rules` 与状态卡 detail 共用此函数，保证两处措辞一致（不再直出
        原始 token 如 "Normal"/"true"/"ItemAndEquipment"）。未知字段/未知枚举值
        一律原样回退，绝不冒 500。
        """
        entry = self._settings.get(field)
        if entry is None:
            return f"{value}"
        enum_map = entry.get("enum_map")
        if enum_map:
            # bool → "true"/"false" 小写键（JSON 布尔与 enum_map 键对齐）
            if isinstance(value, bool):
                key = "true" if value else "false"
            else:
                key = str(value)
            if key in enum_map:
                return enum_map[key]
            if key.lower() in enum_map:  # "True"/"False" 之类大小写兜底
                return enum_map[key.lower()]
            return key                    # 未知枚举值：原样 token，不误映射
        return f"{value}{entry.get('unit', '')}"

    def take_unknown_classes(self) -> list[str]:
        out = self._unknown
        self._unknown = []
        self._unknown_seen = set()
        return out

    def _register_unknown(self, internal_class: str) -> None:
        if internal_class not in self._unknown_seen:
            self._unknown_seen.add(internal_class)
            self._unknown.append(internal_class)

    @staticmethod
    def _safe_abbrev(internal_class: str) -> str:
        return internal_class.rsplit("/", 1)[-1][:20]
