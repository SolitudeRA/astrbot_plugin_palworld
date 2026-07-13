"""AstrBot 运行时以 data.plugins.<目录名>.main 的命名空间导入插件，
插件目录本身不在 sys.path 上——顶级绝对导入 palworld_terminal 会直接
ModuleNotFoundError。本测试在同等条件下导入 main.py，锁定该回归。
运行时(命令层)的同类问题见 namespace_runtime_smoke_test。
"""
from tests.unit._ns_loader import namespaced_main


def test_main_importable_via_namespaced_package_without_repo_root_on_sys_path():
    with namespaced_main() as mod:
        assert hasattr(mod, "PalWorldTerminal")
