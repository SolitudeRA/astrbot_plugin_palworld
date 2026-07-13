"""AstrBot 运行时以 data.plugins.<目录名>.main 的命名空间导入插件，
插件目录本身不在 sys.path 上——顶级绝对导入 palworld_terminal 会直接
ModuleNotFoundError。本测试在同等条件下导入 main.py，锁定该回归。
"""
import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_NS = "fake_astrbot_ns_plugin"


def test_main_importable_via_namespaced_package_without_repo_root_on_sys_path():
    saved_path = list(sys.path)
    saved_modules = {
        k: v for k, v in sys.modules.items()
        if k == "palworld_terminal" or k.startswith("palworld_terminal.")
    }
    try:
        # 模拟 AstrBot：仓库根不在 sys.path，palworld_terminal 未被预先导入
        sys.path = [
            p for p in sys.path
            if p and Path(p).resolve() != REPO_ROOT
        ]
        for k in list(sys.modules):
            if k == "palworld_terminal" or k.startswith("palworld_terminal."):
                del sys.modules[k]

        pkg = types.ModuleType(_NS)
        pkg.__path__ = [str(REPO_ROOT)]
        sys.modules[_NS] = pkg
        spec = importlib.util.spec_from_file_location(
            f"{_NS}.main", REPO_ROOT / "main.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"{_NS}.main"] = mod
        spec.loader.exec_module(mod)

        assert hasattr(mod, "PalWorldTerminal")
    finally:
        sys.path[:] = saved_path
        for k in list(sys.modules):
            if k == _NS or k.startswith(f"{_NS}."):
                del sys.modules[k]
        sys.modules.update(saved_modules)
