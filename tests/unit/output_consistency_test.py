"""跨任务一致性护栏（命令输出重设计 Task 15 收口）。

两条防漂移断言，守 spec §10.2「横切规则全落地」的两个单一真相源：

1. 八类事件措辞（spec §4.4）唯一源 = presentation/event_wording.py；events / today /
   guild info 近期动态三处消费者只 delegate、绝不 re-inline（否则「改词即漂移」复现）。
2. 时长 / 日期 / 折叠格式化唯一源 = presentation/textkit.py；formatters.py delegate 而非
   自造（无 strftime / divmod 手算旁路，helper 名齐全）。
"""
from __future__ import annotations

import ast
import inspect

from palworld_terminal.application import query_service, report_service
from palworld_terminal.presentation import event_wording as event_wording_module
from palworld_terminal.presentation import formatters as formatters_module


def _code_string_literals(source: str) -> str:
    """`source` 中所有「真实代码」字符串字面量文本（换行拼接返回）。

    排除 模块/类/函数 docstring 与注释（注释本就不入 AST）——re-inline 一定是代码里的
    字符串 / f-string 字面量；注释或 docstring 里出现措辞是「描述」而非「产出」，不算漂移。
    f-string 的字面段是 JoinedStr 内的 ast.Constant，ast.walk 会独立遍历到。
    """
    tree = ast.parse(source)
    docstring_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False) is not None and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr):
                    docstring_ids.add(id(first.value))
    parts: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstring_ids:
            parts.append(node.value)
    return "\n".join(parts)


# 八类事件措辞（spec §4.4）各取一段 event_wording 独有的 f-string 字面段作指纹。
_WORDING_FRAGMENTS = [
    "升级 Lv",        # PLAYER_LEVEL_UP
    "加入世界",        # NEW_PLAYER
    "」出现",          # NEW_GUILD
    "」确认",          # NEW_BASE
    "疑似消失",        # BASE_VANISHED
    "工作帕鲁",        # WORKER_DELTA
    "世界迎来第",      # WORLD_DAY_MILESTONE
    "在线人数新纪录",  # ONLINE_RECORD
]


def test_eight_wordings_single_source_no_reinline():
    # 唯一渲染源（render_event）持有全八类措辞指纹。
    canonical = _code_string_literals(inspect.getsource(event_wording_module))
    for frag in _WORDING_FRAGMENTS:
        assert frag in canonical, f"event_wording.py 缺措辞指纹 {frag!r}"
    # 措辞渲染下沉 presentation.render_event（消除 application→presentation 反向依赖）：
    # query/report 不再产措辞、不 import 已废弃的 event_wording，只经 event_view 单一构造
    # 入口产 EventView；代码内绝不 re-inline 任一措辞。
    for mod in (query_service, report_service):
        src = inspect.getsource(mod)
        assert "event_wording" not in src, f"{mod.__name__} 仍引用已废弃的 event_wording"
        assert "event_view(" in src, f"{mod.__name__} 未经 event_view 单一构造入口"
        code_strings = _code_string_literals(src)
        for frag in _WORDING_FRAGMENTS:
            assert frag not in code_strings, (
                f"{mod.__name__} 代码内 re-inline 措辞 {frag!r}——八类措辞应唯一源自 "
                f"presentation.render_event（改词即漂移）"
            )
    # render_event 是 formatters 唯一措辞源（消费者只 delegate，不 re-inline）。
    assert "render_event(" in inspect.getsource(formatters_module)


def test_formatters_delegate_textkit_no_hand_rolled_duration_or_date():
    src = inspect.getsource(formatters_module)
    # 时长 / 日期 / 折叠 helper 全部自 textkit 引入并使用（非本地重造）。
    assert "from ..presentation.textkit import" in src
    for helper in ("fmt_duration", "rel_date", "rel_datetime", "time_of_day", "abs_date", "fold"):
        assert helper in src, f"formatters.py 未引用 textkit.{helper}（疑似自造旁路）"
    # 无自造时长 / 日期格式化旁路：日期一律走 textkit（strftime 唯在 textkit），时长一律走
    # fmt_duration（divmod 手算唯在 textkit）；亦无本地 _fmt_duration 影子实现。
    assert "strftime" not in src, "formatters.py 直接 strftime——日期须走 textkit rel_date/abs_date/time_of_day"
    assert "divmod" not in src, "formatters.py 直接 divmod——时长须走 textkit.fmt_duration"
    assert "def _fmt_duration" not in src, "formatters.py 存在本地 _fmt_duration 影子实现（应删，走 textkit）"
