"""元素图标加载器：按 Element 枚举名 allowlist 读 9 个 SVG，绝不 glob 目录。

红线：目录含 elements-preview.html/png，glob 会把它们读进来污染/破版；缺文件降级
（该元素无图标），供 T9 fallback emoji。
"""
from pathlib import Path

from palworld_terminal.adapters.icon_repository import IconRepository
from palworld_terminal.domain.enums import Element

ICON_DIR = Path(__file__).resolve().parents[2] / "assets" / "element-icons"

_ELEMENTS = {"fire", "water", "grass", "electric", "ice", "dragon",
             "dark", "ground", "neutral"}


def _repo() -> IconRepository:
    repo = IconRepository(ICON_DIR)
    repo.load()
    return repo


def test_element_enum_values_match_allowlist():
    # allowlist 即 Element 枚举名，杜绝二者漂移
    assert {e.value for e in Element} == _ELEMENTS


def test_loads_all_nine_element_svgs():
    icons = _repo().icons()
    assert set(icons) == _ELEMENTS
    for key, svg in icons.items():
        assert "<svg" in svg, key
        assert svg.strip().endswith("</svg>"), key


def test_does_not_read_preview_html_or_png():
    # allowlist 取法：绝不把 elements-preview.html/png 读进来
    icons = _repo().icons()
    assert "elements-preview" not in icons
    for key, svg in icons.items():
        assert "<!doctype" not in svg.lower(), key
        assert "<html" not in svg.lower(), key
        # PNG 二进制头（若误读 png）绝不出现
        assert "\x89PNG" not in svg, key


def test_get_returns_svg_for_known_and_none_for_unknown():
    repo = _repo()
    assert repo.get("fire") is not None
    assert "<svg" in repo.get("fire")
    assert repo.get("nonexistent") is None
    assert repo.get(None) is None
    assert repo.get("") is None


def test_missing_file_degrades_no_crash(tmp_path):
    # 只放 fire.svg + 两个诱饵；load 只取 allowlist 命中的 fire，其余降级缺席
    (tmp_path / "fire.svg").write_text("<svg>f</svg>", encoding="utf-8")
    (tmp_path / "elements-preview.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    (tmp_path / "elements-preview.png").write_bytes(b"\x89PNG\r\n")
    repo = IconRepository(tmp_path)
    repo.load()
    icons = repo.icons()
    assert set(icons) == {"fire"}
    assert icons["fire"] == "<svg>f</svg>"


def test_load_on_empty_dir_returns_empty_no_crash(tmp_path):
    repo = IconRepository(tmp_path)
    repo.load()
    assert repo.icons() == {}
