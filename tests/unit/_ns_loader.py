"""以 AstrBot 命名空间形式加载 main.py 的测试助手。

AstrBot 运行时以 data.plugins.<目录名>.main 导入插件,插件目录不在
sys.path——本助手在同等条件下加载 main,供加载回归与运行时冒烟共用。
"""
from __future__ import annotations

import contextlib
import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

NS = "fake_astrbot_ns_plugin"


@contextlib.contextmanager
def namespaced_main():
    saved_path = list(sys.path)
    saved_modules = {
        k: v for k, v in sys.modules.items()
        if k == "palworld_terminal" or k.startswith("palworld_terminal.")
    }
    try:
        # 模拟 AstrBot:仓库根不在 sys.path,palworld_terminal 未被预先导入
        sys.path = [p for p in sys.path if p and Path(p).resolve() != REPO_ROOT]
        for k in list(sys.modules):
            if k == "palworld_terminal" or k.startswith("palworld_terminal."):
                del sys.modules[k]

        pkg = types.ModuleType(NS)
        pkg.__path__ = [str(REPO_ROOT)]
        sys.modules[NS] = pkg
        spec = importlib.util.spec_from_file_location(f"{NS}.main", REPO_ROOT / "main.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"{NS}.main"] = mod
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.path[:] = saved_path
        for k in list(sys.modules):
            if k == NS or k.startswith(f"{NS}."):
                del sys.modules[k]
        sys.modules.update(saved_modules)
