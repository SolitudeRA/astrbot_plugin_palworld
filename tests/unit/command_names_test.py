import re
from pathlib import Path

from palworld_terminal.config import _NON_LOCKABLE
from palworld_terminal.presentation.command_registry import (
    DISPATCH,
    FLAT_ACTIONS,
    LOCKABLE_COMMANDS,
    PAL_COMMAND_STRINGS,
    PAL_REGISTERED,
)
from palworld_terminal.presentation.commands import Commands

_MAIN = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")

# 完整路径不可锁集（与 config._NON_LOCKABLE / registry._NON_LOCKABLE 同集）。
_NON_LOCKABLE_PATHS = frozenset({
    "server announce", "server save", "server kick", "server unban",
    "server ban", "server shutdown", "server stop",
    "link list", "link add", "link remove",
    "help", "whoami", "confirm",
})


def test_registrations_match_pal_registered():
    # main.py 实际 @pal.command("X") 注册串 == PAL_REGISTERED(11 首词:5 组 + 6 扁平)。
    # AstrBot 只认首词;子动作(world status …)由 Commands 层自解析,不在注册面。
    registered = set(re.findall(r'@pal\.command\("([^"]+)"\)', _MAIN))
    assert registered == set(PAL_REGISTERED), (
        f"注册串与 PAL_REGISTERED 不一致：仅注册 {registered - set(PAL_REGISTERED)}，"
        f"仅表内 {set(PAL_REGISTERED) - registered}"
    )
    assert len(registered) == 11


def test_lockable_excludes_non_lockable():
    assert LOCKABLE_COMMANDS == frozenset(PAL_COMMAND_STRINGS) - _NON_LOCKABLE_PATHS
    assert "world status" in LOCKABLE_COMMANDS
    assert "player unbind" in LOCKABLE_COMMANDS   # 完整路径,不是方法名 unbind_self
    assert "rank" in LOCKABLE_COMMANDS            # 扁平命令可锁
    # server 写命令 + link + 元命令一律不可锁
    assert "server kick" not in LOCKABLE_COMMANDS and "help" not in LOCKABLE_COMMANDS
    assert not (_NON_LOCKABLE_PATHS & LOCKABLE_COMMANDS)


def test_non_lockable_matches_registry_complement():
    # config._NON_LOCKABLE(命令门内联)必须与 registry 的不可锁集全等(完整路径):
    # 任一处改了不可锁集而另一处没跟,此处转红(防漂移)。
    registry_non_lockable = frozenset(PAL_COMMAND_STRINGS) - set(LOCKABLE_COMMANDS)
    assert registry_non_lockable == _NON_LOCKABLE


def test_dispatch_methods_resolve_on_commands():
    # DISPATCH read/admin 方法名 + FLAT_ACTIONS 方法名须解析到 Commands 可调用绑定
    # (抓 typo,如 player unbind → unbind_self 映射错位 → 运行时 AttributeError)。
    for group, actions in DISPATCH.items():
        for sub, (method, _feat, gate) in actions.items():
            if gate == "admin_write":
                continue  # 写动作方法名是 admin_write 的 command_str token,非 Commands 方法
            assert callable(getattr(Commands, method)), f"{group} {sub} → {method}"
    for name, (method, _feat, _gate) in FLAT_ACTIONS.items():
        assert callable(getattr(Commands, method)), f"{name} → {method}"
