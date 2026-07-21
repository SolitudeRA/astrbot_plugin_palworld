"""StatusDetail 键集跨端静态锚点：前端 interface 与后端形状同源。

任一端改状态卡「详细区」形状（增删键），另一端测试即红——防前后端契约悄悄漂移。
手法同 frontend_pal_commands_test：正则从前端源文件抽键集，再与后端真源交叉断言。
"""
import re
from pathlib import Path

from palworld_terminal.application.query_service import _STATUS_RULE_FIELDS
from palworld_terminal.application.dtos import StatusDetailDTO

_VUE = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "components" / "StatusPanel.vue"
).read_text(encoding="utf-8")

# 键集单一真相（两端都对齐它；改形状须同步改此处 + 两端源，一处不改即红）。
TOP_KEYS = {"version", "description", "uptime_seconds", "frametime_ms", "address", "rules"}
RULES_KEYS = {"difficulty", "pvp", "death_penalty", "exp_rate"}


def _extract_status_detail() -> tuple[set[str], set[str]]:
    """从 StatusPanel.vue 抽 `interface StatusDetail` 的顶层键集与嵌套 rules 键集。

    interface 体的闭合 `}` 独占行首（行内嵌套的 rules `{ ... }` 以空格+`}` 收尾，
    不含换行前的 `}`），故非贪婪 `.*?\\n\\}` 精确停在 interface 闭合处。
    """
    body_m = re.search(r"interface StatusDetail\s*\{(.*?)\n\}", _VUE, re.S)
    assert body_m, "StatusPanel.vue 缺 interface StatusDetail"
    body = body_m.group(1)

    rules_m = re.search(r"rules\?\s*:\s*\{([^}]*)\}", body)
    assert rules_m, "interface StatusDetail 缺嵌套 rules 形状"
    rules_keys = set(re.findall(r"(\w+)\?\s*:", rules_m.group(1)))

    # 顶层：先把 rules 的嵌套块挖掉，避免嵌套键混进顶层集
    top_body = body[: rules_m.start()] + " rules?: _ " + body[rules_m.end() :]
    top_keys = set(re.findall(r"(\w+)\?\s*:", top_body))
    return top_keys, rules_keys


def test_frontend_interface_matches_canonical_keyset():
    top_keys, rules_keys = _extract_status_detail()
    assert top_keys == TOP_KEYS
    assert rules_keys == RULES_KEYS


def test_backend_shape_matches_canonical_keyset():
    # 后端 DTO 字段 = 顶层键真相；status_rows 逐字拷贝这些字段下发（config_view_status_test 守）。
    assert set(StatusDetailDTO.__dataclass_fields__) == TOP_KEYS
    # detail.rules 输出键真相 = query_service._STATUS_RULE_FIELDS（与 /pal world rules 同源）。
    assert {out_key for out_key, _field in _STATUS_RULE_FIELDS} == RULES_KEYS
