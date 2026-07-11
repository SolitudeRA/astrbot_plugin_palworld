"""合成脱敏 API 快照 fixtures 的加载器。所有 fixture 均为已脱敏样本（无真实 IP/账号/坐标语义）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def fixtures_root() -> Path:
    return Path(__file__).resolve().parent


def load_fixture(scenario: str, endpoint: str) -> dict[str, Any]:
    path = fixtures_root() / scenario / f"{endpoint}.json"
    if not path.is_file():
        raise FileNotFoundError(f"fixture not found: {scenario}/{endpoint}.json")
    return json.loads(path.read_text(encoding="utf-8"))


def load_series(scenario: str) -> list[dict[str, Any]]:
    path = fixtures_root() / scenario / "series.json"
    if not path.is_file():
        raise FileNotFoundError(f"series fixture not found: {scenario}/series.json")
    frames = json.loads(path.read_text(encoding="utf-8"))
    return sorted(frames, key=lambda f: f["tick"])
