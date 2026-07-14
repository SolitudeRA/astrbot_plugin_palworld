"""format_help 角色隔离：服务器管控写命令与 confirm 仅管理员可见。

安全模型的一部分：非管理员的 /pal help 绝不泄漏写命令的存在（哪怕组已开）；
写命令行仅在「组已开 且 is_admin」时出现；confirm（core）仅受 is_admin 门。
"""
from __future__ import annotations

from palworld_terminal.presentation.command_registry import HELP_LINE
from palworld_terminal.presentation.formatters import format_help


class _Features:
    def __init__(self, groups: dict[str, bool]) -> None:
        self._groups = groups

    def enabled(self, group: str) -> bool:
        return self._groups.get(group, False)


def _feats(**over) -> _Features:
    base = {
        "server_admin_basic": True, "server_admin_danger": True,
        "guilds_bases": False, "events": False, "report": False, "players": False,
    }
    base.update(over)
    return _Features(base)


def test_help_hides_write_commands_from_non_admin():
    out = format_help(None, is_admin=False, features=_feats())
    assert "/pal kick" not in out
    assert "/pal ban" not in out
    assert "/pal announce" not in out
    assert "/pal confirm" not in out


def test_help_shows_write_commands_to_admin_when_enabled():
    out = format_help(None, is_admin=True, features=_feats())
    for frag in ("/pal announce", "/pal save", "/pal kick", "/pal unban",
                 "/pal ban", "/pal shutdown", "/pal stop", "/pal confirm"):
        assert frag in out


def test_help_hides_write_commands_when_group_disabled_even_for_admin():
    out = format_help(
        None, is_admin=True,
        features=_feats(server_admin_basic=False, server_admin_danger=False),
    )
    assert "/pal kick" not in out       # danger 组关
    assert "/pal announce" not in out   # basic 组关
    # confirm 是 core，仅受 is_admin 门（不受组门），管理员仍可见
    assert "/pal confirm" in out


def test_help_line_confirm_present_no_keyerror():
    # format_help 遍历 COMMANDS 取 HELP_LINE[name]；confirm 缺行会 KeyError。
    assert "confirm" in HELP_LINE
    assert HELP_LINE["confirm"]
