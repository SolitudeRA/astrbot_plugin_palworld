"""QueryService 拆分结构守卫：叶子 mixin 只通过脊柱跨组协作。"""
from __future__ import annotations

import ast
import pathlib

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "palworld_terminal" / "application"

SPINE = {"load_excluded_keys", "name_banned", "resolve_event_subjects"}

def _self_call_names(class_node: ast.ClassDef) -> set[str]:
    calls: set[str] = set()
    for node in ast.walk(class_node):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            calls.add(node.func.attr)
    return calls


def _own_method_names(class_node: ast.ClassDef) -> set[str]:
    return {
        n.name for n in class_node.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_spine_is_only_cross_cut():
    # 每个 query_* mixin：self.NAME() 直接调用 ⊆ (自身方法 ∪ 脊柱三方法)。
    # 锁死「跨组只经脊柱（继承而来），绝无 leaf-to-leaf」。self._X.foo() 这类不计入
    # （func.value 是 Attribute 非 Name('self')）；self._BASES_TTL 是属性访问非 Call。
    mixin_files = sorted(APP_DIR.glob("query_*.py"))
    mixin_files = [p for p in mixin_files if p.name not in ("query_service.py", "query_support.py")]
    assert mixin_files, "未发现 query mixin，扫描范围可能失效"
    for py in mixin_files:
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                own = _own_method_names(node)
                calls = _self_call_names(node)
                leak = calls - own - SPINE
                assert not leak, f"{py.name}:{node.name} 跨组调用越出脊柱：{leak}"
