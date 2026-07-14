import re
from pathlib import Path

from palworld_terminal.config import _NON_LOCKABLE
from palworld_terminal.presentation.command_registry import (
    LOCKABLE_COMMANDS,
    PAL_COMMAND_STRINGS,
)

_MAIN = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")


def test_pal_command_strings_match_main_registrations():
    # main.py 实际 @pal.command("X") 注册串 == PAL_COMMAND_STRINGS(防漏/防多)
    registered = set(re.findall(r'@pal\.command\("([^"]+)"\)', _MAIN))
    assert registered == set(PAL_COMMAND_STRINGS), (
        f"注册串与 PAL_COMMAND_STRINGS 不一致：仅注册 {registered - set(PAL_COMMAND_STRINGS)}，"
        f"仅表内 {set(PAL_COMMAND_STRINGS) - registered}"
    )


def test_lockable_excludes_non_lockable():
    non_lockable = {
        "server", "whoami", "help", "confirm",
        "announce", "save", "kick", "unban", "ban", "shutdown", "stop",
    }
    assert LOCKABLE_COMMANDS == frozenset(PAL_COMMAND_STRINGS) - non_lockable
    assert "unbind" in LOCKABLE_COMMANDS    # 命令串是 unbind,不是 unbind_self
    assert "server" not in LOCKABLE_COMMANDS and "help" not in LOCKABLE_COMMANDS
    # 服务器管控写命令 + confirm 一律不可锁
    assert not (non_lockable & LOCKABLE_COMMANDS)


def test_non_lockable_matches_registry_complement():
    # config._NON_LOCKABLE(命令门内联)必须与 registry 的不可锁集全等:
    # 任一处改了不可锁集而另一处没跟,此处转红(防漂移)。8 写命令 + confirm 已注册进
    # registry(T8),两侧全集相等——原全等断言恢复(桥接钉子 8→0)。
    registry_non_lockable = frozenset(PAL_COMMAND_STRINGS) - set(LOCKABLE_COMMANDS)
    assert registry_non_lockable == _NON_LOCKABLE
