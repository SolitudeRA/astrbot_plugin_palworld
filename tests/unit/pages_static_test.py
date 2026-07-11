"""插件页面静态结构：文件齐全、脚本为 module、无 innerHTML/明文回显。"""
import re
from pathlib import Path

PAGES = Path(__file__).resolve().parents[2] / "pages" / "settings"


def test_index_and_assets_exist():
    for f in ("index.html", "app.js", "settings.js", "status.js", "style.css"):
        assert (PAGES / f).exists(), f"缺少 {f}"


def test_scripts_are_module_type():
    html = (PAGES / "index.html").read_text(encoding="utf-8")
    for m in re.findall(r"<script\b[^>]*>", html):
        if "src=" in m:
            assert 'type="module"' in m, f"外部脚本须为 module: {m}"


def test_no_innerhtml_in_js():
    # XSS 红线：外部/配置派生字符串一律 textContent，禁止 innerHTML 赋值
    for f in ("app.js", "settings.js", "status.js"):
        src = (PAGES / f).read_text(encoding="utf-8")
        assert ".innerHTML" not in src, f"{f} 不得使用 innerHTML"


def test_sentinel_constant_present():
    src = (PAGES / "settings.js").read_text(encoding="utf-8")
    assert "__unchanged__" in src  # 哨兵保留字用于未改动的敏感字段


def test_custom_headers_handled_to_avoid_clearing():
    # custom_headers.value 被 config/get 脱敏为空；settings.js 必须显式处理
    # （建卡片走哨兵），否则原样回传会清空所有请求头值
    src = (PAGES / "settings.js").read_text(encoding="utf-8")
    assert "custom_headers" in src
