"""StatusDetail 跨端契约：前端 interface 与后端输出形状一致。"""
import re
from pathlib import Path

from palworld_terminal.application.dtos import StatusDetailDTO
from palworld_terminal.application.query_service import _STATUS_RULE_FIELDS

_VUE = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "components" / "StatusPanel.vue"
).read_text(encoding="utf-8")

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


def test_frontend_interface_matches_backend_contract():
    top_keys, rules_keys = _extract_status_detail()
    assert top_keys == set(StatusDetailDTO.__dataclass_fields__)
    assert rules_keys == {out_key for out_key, _field in _STATUS_RULE_FIELDS}
