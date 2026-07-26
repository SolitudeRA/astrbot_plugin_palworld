"""中文残留守卫（i18n §3.5 末 / §6「中文残留检测（定案）」）：presentation 层全部
**非 docstring、非注释、非 _log 参数** 的字符串字面量不得含 CJK 统一表意文字——防抽键
遗漏 / 措辞回流源码。

Task 8 收口：textkit / card_render / event_wording / admin_write_flow / commands /
web_api 的运行时中文串已全量抽键入 `locales/*.json`，经 `L()` 渲染。本守卫把「抽键完整性」
固化为断言：任何新增的 presentation 硬编码中文措辞即红。

普查口径（AST，等价 tokenize 的 STRING 面但可精确分类，参照 T6
`no_cjk_in_lower_layers_test.py` 范式）：
- 收集全部 ``str`` 常量（含 f-string 字面段），命中 = 含 CJK（``[一-鿿]``）；
- 排除 docstring（Module/Class/Function 体首个 ``Expr`` 字符串）；
- 排除 ``_log.*`` 调用参数（开发者日志不译，spec §4/§8）；
- Python ``#`` 注释天然非 STRING、不入扫描面；
- 剩余命中须全部落在豁免面（``_EXEMPT`` 精确 (file,value) 清单 或 card_render 的
  ``<style>`` 模板 CSS 注释），否则红。

标点（``「」（）、：…`` 等全角符号）不在 CJK 表意文字区间，天然不触发——与 spec §6
「en：CJK 统一表意文字零容忍」口径一致（标点三语通用问题归 T4 文案期）。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PKG = _REPO_ROOT / "palworld_terminal"
_PRESENTATION = _PKG / "presentation"

_CJK = re.compile(r"[一-鿿]")

# _log.debug/info/warning/... 及等价方法名——base 变量名含 "log" 即视为日志器。
_LOG_ATTRS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}

_CARD_RENDER = "presentation/card_render.py"


# 精确豁免清单：(相对 palworld_terminal 的 posix 路径, 字面量值) -> 理由。
# 按 (file, value) 而非行号定位，避免上方编辑漂移导致误锁。
_EXEMPT: dict[tuple[str, str], str] = {
    # command_support._ME_CARD_TOKENS = frozenset({"card", "卡", "图"})：`/pal me` 后触发
    # 图片卡的**输入别名**（三语通收——中文别名在任何 locale 下继续可用）。输入别名非输出
    # 文案，spec §3.5 明列扫描豁免。
    ("presentation/command_support.py", "卡"): "_ME_CARD_TOKENS 输入别名（三语通收，非输出文案；spec §3.5 豁免）",
    ("presentation/command_support.py", "图"): "_ME_CARD_TOKENS 输入别名（同上）",
    # web_api.handle_mode_transfer：single_allowed_groups 的 note 字段兜底值，写入 config /
    # 落库（data-at-rest）。spec §3.5/§4：落盘迁移注记不译（存当时状态、不追溯翻译）。
    ("presentation/web_api.py", "从多世界绑定迁移"): "single_allowed_groups note 落库兜底（data-at-rest，spec §3.5/§4 不译）",
}


def _is_card_css_comment(rel: str, value: str) -> bool:
    """card_render.build_me_card_html 的 ``<style>`` 模板内嵌 CSS 开发者注释（``/* … */``）。

    这些是**开发者文档**（HiDPI/截图裁剪原理），非 UX 文案，随模板 f-string 一并落进输出串；
    图片渲染时 CSS 注释不可见，无任何观感差异。**「zh 输出逐字节不变」是铁律** → 保留原样、
    不改动模板字节。以 CSS 注释定界符判定（避免逐字硬编码多行巨串），仅限 card_render.py。
    """
    return rel == _CARD_RENDER and ("*/" in value or "<style>" in value)


def _docstring_const_ids(tree: ast.AST) -> set[int]:
    """所有 docstring 字符串常量节点的 id()（Module/Class/Function 体首个 Expr 串）。"""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr):
                v = body[0].value
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    ids.add(id(v))
    return ids


def _is_log_call(func: ast.AST) -> bool:
    """func 是否形如 _log.info / logger.warning / self._log.debug。"""
    if isinstance(func, ast.Attribute) and func.attr in _LOG_ATTRS:
        base = func.value
        if isinstance(base, ast.Name) and "log" in base.id.lower():
            return True
        if isinstance(base, ast.Attribute) and "log" in base.attr.lower():
            return True
    return False


def _log_arg_const_ids(tree: ast.AST) -> set[int]:
    """所有位于 _log.* 调用子树内的字符串常量节点 id()（含 f-string 段）。"""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_log_call(node.func):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    ids.add(id(sub))
    return ids


def _scan_presentation_cjk() -> list[tuple[str, int, str]]:
    """返回 presentation 全部「运行时」CJK 字面量：(相对路径, 行号, 值)。

    运行时 = 含 CJK 的 str 常量，且非 docstring、非 _log 参数。
    """
    hits: list[tuple[str, int, str]] = []
    for py in sorted(_PRESENTATION.rglob("*.py")):
        src = py.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(py))
        excluded = _docstring_const_ids(tree) | _log_arg_const_ids(tree)
        rel = py.relative_to(_PKG).as_posix()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and _CJK.search(node.value)
                and id(node) not in excluded
            ):
                hits.append((rel, node.lineno, node.value))
    return hits


def _is_exempt(rel: str, value: str) -> bool:
    return (rel, value) in _EXEMPT or _is_card_css_comment(rel, value)


def test_no_unexpected_cjk_in_presentation_runtime():
    """presentation 无未豁免的运行时中文字面量——防抽键遗漏 / 措辞回流（红→绿守卫）。"""
    hits = _scan_presentation_cjk()
    unexpected = [(rel, ln, val) for rel, ln, val in hits if not _is_exempt(rel, val)]
    assert not unexpected, (
        "presentation 出现未豁免的运行时中文字面量（须经 L()+MESSAGES 抽键上提 "
        "locales/zh-CN.json，或在 _EXEMPT 显式豁免并写明理由）：\n"
        + "\n".join(f"  {rel}:{ln}  {val!r}" for rel, ln, val in unexpected)
    )


def test_exact_exemptions_are_all_live():
    """每条精确豁免须对应真实命中——防豁免清单腐烂（措辞已移除仍留豁免会掩盖回流）。"""
    present = {(rel, val) for rel, _ln, val in _scan_presentation_cjk()}
    stale = [key for key in _EXEMPT if key not in present]
    assert not stale, (
        "_EXEMPT 存在陈旧条目（对应字面量已不在 presentation，应删除该豁免）：\n"
        + "\n".join(f"  {rel}  {val!r}" for rel, val in stale)
    )


def test_card_css_comment_exemption_is_bounded():
    """card_render CSS 注释豁免须锚定其边界——防「*/ 定界符」谓词无声吞掉新增措辞。

    build_me_card_html 的 <style> 模板恰有 2 段内嵌 CJK 的 CSS 注释块（HiDPI 缩放说明 +
    只截卡片说明）；两段均含 `zoom`（模板骨架标记）。数量/标记漂移即红 → 强制重审模板。
    """
    css = [
        (rel, ln, val)
        for rel, ln, val in _scan_presentation_cjk()
        if _is_card_css_comment(rel, val)
    ]
    assert len(css) == 2, (
        "card_render <style> 模板 CSS 注释块数量偏离预期（2）——模板结构变动，请重审：\n"
        + "\n".join(f"  {rel}:{ln}" for rel, ln, _v in css)
    )
    assert all("zoom" in val for _rel, _ln, val in css), (
        "card_render CSS 注释豁免块未含预期骨架标记 `zoom`——谓词可能吞入非注释措辞，请重审。"
    )
