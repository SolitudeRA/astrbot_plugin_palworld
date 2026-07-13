import re
from pathlib import Path

from palworld_terminal.presentation.command_registry import LOCKABLE_COMMANDS

_SCHEMA = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "schema.ts").read_text(encoding="utf-8")


def test_pal_commands_matches_lockable():
    # 从 schema.ts 的 PAL_COMMANDS 提命令串,断言 == 后端 LOCKABLE_COMMANDS
    m = re.search(r"export const PAL_COMMANDS[^=]*=\s*\[(.*?)\]", _SCHEMA, re.S)
    assert m, "schema.ts 缺 PAL_COMMANDS"
    cmds = set(re.findall(r"cmd:\s*'([^']+)'", m.group(1)))
    assert cmds == set(LOCKABLE_COMMANDS), (
        f"PAL_COMMANDS 与 LOCKABLE_COMMANDS 漂移：仅前端 {cmds - set(LOCKABLE_COMMANDS)}，"
        f"仅后端 {set(LOCKABLE_COMMANDS) - cmds}"
    )
