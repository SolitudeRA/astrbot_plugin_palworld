"""XSS 红线转移到前端源码：Vue 组件禁 v-html / innerHTML（对源码而非压缩产物）。"""
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_no_v_html_in_vue_sources():
    for f in SRC.rglob("*.vue"):
        assert "v-html" not in f.read_text(encoding="utf-8"), f"{f.name} 不得用 v-html"


def test_no_innerhtml_in_frontend_sources():
    for f in list(SRC.rglob("*.vue")) + list(SRC.rglob("*.ts")):
        assert ".innerHTML" not in f.read_text(encoding="utf-8"), f"{f.name} 不得用 innerHTML"
