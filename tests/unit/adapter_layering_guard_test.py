import pathlib

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "palworld_terminal" / "application"


def test_application_has_no_adapters_import():
    """application 层绝不 import adapters（依赖倒置守卫，Spec C §6）。"""
    offenders = []
    for py in APP_DIR.glob("*.py"):
        src = py.read_text(encoding="utf-8")
        if "from ..adapters" in src or "import palworld_terminal.adapters" in src:
            offenders.append(py.name)
    assert offenders == [], f"application 层残留 adapters import：{offenders}"
