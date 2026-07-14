import json
import re
from pathlib import Path

from palworld_terminal.application.command_permissions import (
    COMMAND_META,
    DANGER_COMMANDS,
    admin_configurable,
    admin_forced_true,
    enable_configurable,
)
from palworld_terminal.presentation.command_registry import LOCKABLE_COMMANDS

_SCHEMA = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "schema.ts").read_text(encoding="utf-8")


def _load_pal_tree_json() -> list[dict]:
    # PAL_TREE 落成 JSON 可解析（双引号键/值、true/false/null），
    # 抽出数组字面量 → json.loads，避免正则啃嵌套 TS 对象。
    # 数组内对象只用 {}，无嵌套 []，故非贪婪 \[.*?\] 精确停在数组闭合处。
    m = re.search(r"export const PAL_TREE[^=]*=\s*(\[.*?\])", _SCHEMA, re.S)
    assert m, "schema.ts 缺 PAL_TREE"
    return json.loads(m.group(1))


def test_pal_commands_matches_lockable():
    # 保留：PAL_COMMANDS（供 SettingsPanel 现构建）命令串 == 后端 LOCKABLE_COMMANDS。
    m = re.search(r"export const PAL_COMMANDS[^=]*=\s*\[(.*?)\]", _SCHEMA, re.S)
    assert m, "schema.ts 缺 PAL_COMMANDS"
    cmds = set(re.findall(r"cmd:\s*'([^']+)'", m.group(1)))
    assert cmds == set(LOCKABLE_COMMANDS), (
        f"PAL_COMMANDS 与 LOCKABLE_COMMANDS 漂移：仅前端 {cmds - set(LOCKABLE_COMMANDS)}，"
        f"仅后端 {set(LOCKABLE_COMMANDS) - cmds}"
    )


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
