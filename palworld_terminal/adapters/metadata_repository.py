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
