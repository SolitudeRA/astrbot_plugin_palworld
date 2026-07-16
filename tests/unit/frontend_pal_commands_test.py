import json
import re
from pathlib import Path

from palworld_terminal.application.command_permissions import (
    COMMAND_META,
    DANGER_COMMANDS,
    admin_configurable,
    admin_forced_true,
    default_enabled,
    enable_configurable,
    upstream_unavailable,
)

_SCHEMA = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "schema.ts").read_text(encoding="utf-8")


def _load_pal_tree_json() -> list[dict]:
    # PAL_TREE 落成 JSON 可解析（双引号键/值、true/false/null），
    # 抽出数组字面量 → json.loads，避免正则啃嵌套 TS 对象。
    # 数组内对象只用 {}，无嵌套 []，故非贪婪 \[.*?\] 精确停在数组闭合处。
    m = re.search(r"export const PAL_TREE[^=]*=\s*(\[.*?\])", _SCHEMA, re.S)
    assert m, "schema.ts 缺 PAL_TREE"
    return json.loads(m.group(1))


def test_frontend_tree_matches_backend_meta():
    # PAL_TREE 完整命令树描述须与后端派生元数据全等（跨端锚定，任一漂移即红）。
    tree = _load_pal_tree_json()
    assert {n["path"] for n in tree} == set(COMMAND_META)
    for n in tree:
        p = n["path"]
        assert n["enableConfigurable"] == enable_configurable(p), p
        assert n["adminConfigurable"] == admin_configurable(p), p
        assert n["adminForced"] == admin_forced_true(p), p
        assert n["danger"] == (p in DANGER_COMMANDS), p
        assert n["defaultEnabled"] == default_enabled(p), p
        # 上游不可用硬锁跨端锚定：PAL_TREE.unavailable（缺省 false）须与后端
        # upstream_unavailable(path) 全等——任一端漏翻转即红（三向同 commit）。
        assert n.get("unavailable", False) == upstream_unavailable(p), p
