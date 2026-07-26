"""架构守卫（i18n §3.2 末 / §6「架构守卫」）：application + shared 两层的
**非 docstring、非 _log 参数** 字符串字面量不得含 CJK——防中文措辞回流下层。

分层契约禁止 application/shared 向上取 presentation 的 ``L()``；收编方向一律
「下层产稳定键，中文上提 presentation」（T2-T5 已收编 smoothness / rules 策展标签·
单位词·隐私注记 / report summary / name_resolver 回退词 / HELP_TEXT）。本守卫把
普查逻辑固化为断言：任何新增的下层硬编码中文措辞即红。

普查口径（AST，等价 tokenize 的 STRING 面但可精确分类）：
- 收集全部 ``str`` 常量（含 f-string 字面段），命中 = 含 CJK（``[一-鿿]``）；
- 排除 docstring（Module/Class/Function 体首个 ``Expr`` 字符串）；
- 排除 ``_log.*`` 调用参数（开发者日志不译，spec §4/§8）；
- 剩余命中须全部落在 ``_EXEMPT`` 显式豁免清单，否则红。

豁免（file, value）→ 理由。每条须写明为何该 CJK 字面量正当留在下层。

【T3 enum 豁免说明】RulesDTO 的 enum 渲染值经 ``metadata.setting_display`` 读
``settings.json``（数据文件层，**非源码字面量**），本源码 token 扫描天然不涉，无需在
此列豁免；其**运行时 DTO** 由 ``query_service_rules_test.test_rules_dto_carries_no_curated_chinese``
守卫（该处对 enum 值显式豁免）。两守卫互补：此处守源码字面量，彼处守运行时 DTO。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PKG = _REPO_ROOT / "palworld_terminal"
_LOWER_LAYERS = ("application", "shared")

_CJK = re.compile(r"[一-鿿]")

# _log.debug/info/warning/... 及等价方法名——base 变量名含 "log" 即视为日志器。
_LOG_ATTRS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}


# 显式豁免清单：(相对 palworld_terminal 的 posix 路径, 字面量值) -> 理由。
# 按 (file, value) 而非行号定位，避免上方编辑漂移导致误锁。
_EXEMPT: dict[tuple[str, str], str] = {
    # ~application/guild_service.py:51  names.get(gk) or ("公会-" + gk[:6])
    # 匿名公会兜底名。裁定「数据兜底名不译」，理由（多轴）：
    # ① 落库：该值写入 guilds.latest_name（upsert_guild），属 data-at-rest；spec §4
    #    落盘串政策=存当时 locale、不追溯翻译。
    # ② 合成标识而非策展措辞：值 = 固定前缀 + guild_key 哈希前 6 位，是无名公会的稳定
    #    识别名（等同其身份），非「流畅」「平静的一天」式 UX 措辞。
    # ③ 兼作用户查询键：query_guild.guild(name)/base() 按 latest_name 精确匹配用户输入
    #    （/pal guild 公会-abc123）。渲染层本地化会令展示名与 DB 查询键脱钩→按显示名回查失败。
    # ④ 分层约束：apply() 在 application 摄取路径，不能调 L()；真渲染兜底须在 ~5 处
    #    presentation 读路径重建 gk[:6] 并本地化，且承 ③ 的脱钩风险，代价远超收益。
    # 对比 T4 name_resolver 回退词（据点/公会）：那些只在事件渲染时注入瞬态 EventView.name、
    # 不落库、非查询键——故干净上提 presentation；本例三轴相反，不适用同法。
    ("application/guild_service.py", "公会-"): "匿名公会落库兜底名（data-at-rest + 兼查询键，见上）",
}


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


def _scan_user_visible_cjk() -> list[tuple[str, int, str]]:
    """返回下层全部「用户可见」CJK 字面量：(相对路径, 行号, 值)。

    用户可见 = 含 CJK 的 str 常量，且非 docstring、非 _log 参数。
    """
    hits: list[tuple[str, int, str]] = []
    for layer in _LOWER_LAYERS:
        for py in sorted((_PKG / layer).rglob("*.py")):
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


def test_no_unexpected_cjk_in_application_and_shared():
    """下层无未豁免的用户可见中文措辞——防措辞回流（红→绿守卫）。"""
    hits = _scan_user_visible_cjk()
    unexpected = [
        (rel, ln, val) for rel, ln, val in hits if (rel, val) not in _EXEMPT
    ]
    assert not unexpected, (
        "application/shared 出现未豁免的用户可见中文字面量（须稳定键化上提 "
        "presentation，或在 _EXEMPT 显式豁免并写明理由）：\n"
        + "\n".join(f"  {rel}:{ln}  {val!r}" for rel, ln, val in unexpected)
    )


def test_exemptions_are_all_live():
    """每条豁免须对应真实命中——防豁免清单腐烂（措辞已移除仍留豁免会掩盖回流）。"""
    present = {(rel, val) for rel, _ln, val in _scan_user_visible_cjk()}
    stale = [key for key in _EXEMPT if key not in present]
    assert not stale, (
        "_EXEMPT 存在陈旧条目（对应字面量已不在下层，应删除该豁免）：\n"
        + "\n".join(f"  {rel}  {val!r}" for rel, val in stale)
    )
