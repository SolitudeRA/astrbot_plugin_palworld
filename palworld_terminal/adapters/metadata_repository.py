from __future__ import annotations

import json
from pathlib import Path

from ..domain.enums import ActionCategory


class MetadataRepository:
    def __init__(self, metadata_dir: Path) -> None:
        self._dir = Path(metadata_dir)
        self._pals: dict[str, dict] = {}
        self._actions: dict[str, str] = {}
        self._settings: dict[str, dict] = {}
        self._unknown: list[str] = []
        self._unknown_seen: set[str] = set()

    def load(self) -> None:
        self._pals = self._read("pals.zh-CN.json")
        self._actions = self._read("actions.json")
        self._settings = self._read("settings.zh-CN.json")

    def _read(self, name: str) -> dict:
        path = self._dir / name
        return json.loads(path.read_text(encoding="utf-8"))

    def pal_name(self, internal_class: str) -> str:
        entry = self._pals.get(internal_class)
        if entry is not None:
            return entry["name_zh"]
        self._register_unknown(internal_class)
        return self._safe_abbrev(internal_class)

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
