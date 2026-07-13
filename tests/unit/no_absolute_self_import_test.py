"""包内与 main.py 函数体内禁止绝对自导入(实机故障回归钉)。

AstrBot 以 data.plugins.<目录>.main 命名空间加载插件,插件目录不在
sys.path——绝对自导入在测试环境(仓库根在 path)能过,真实环境运行时
ModuleNotFoundError(实测 /pal me 曾因 commands.py 函数内绝对导入炸掉)。

覆盖逻辑:模块顶层的环境差异由 astrbot_namespace_load_test 运行时覆盖
(main 的相对导入链拉起全依赖树);函数内 lazy 导入运行时测试抓不到,
只能静态扫描——包内一律相对导入;main.py 仅模块顶层 try/except 双份
入口允许绝对自导入(测试环境回退),函数体内禁止。
"""
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_PKG = _ROOT / "palworld_terminal"
_ABS = re.compile(r"^(\s*)(?:from\s+palworld_terminal[.\s]|import\s+palworld_terminal)")


def _offending_lines(path: Path, max_indent: int) -> list[str]:
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = _ABS.match(line)
        if m and len(m.group(1)) > max_indent:
            out.append(f"{path.name}:{i}: {line.strip()}")
    return out


def test_no_absolute_self_import_inside_package():
    offenders = []
    for py in _PKG.rglob("*.py"):
        offenders += _offending_lines(py, max_indent=-1)  # 包内任何缩进都不允许
    assert not offenders, (
        f"包内绝对自导入(真实 AstrBot 环境 ModuleNotFoundError),改相对导入: {offenders}"
    )


def test_main_absolute_self_import_only_at_module_level_fallback():
    # main.py 顶层 try/except 双份入口(缩进 4)是设计;函数体内(缩进>4)禁止
    offenders = _offending_lines(_ROOT / "main.py", max_indent=4)
    assert not offenders, (
        f"main.py 函数体内绝对自导入(真实 AstrBot 环境 ModuleNotFoundError): {offenders}"
    )
