"""format_help 角色隔离：服务器管控写命令与 confirm 仅管理员可见（分级完整路径）。

安全模型的一部分：非管理员的 /pal help 绝不泄漏写命令的存在（哪怕组已开）；
写命令行（/pal server kick …）仅在「组已开 且 is_admin」时出现；confirm 仅受 is_admin 门。
命令串随分级架构由扁平（/pal kick）迁移为完整路径（/pal server kick）——安全性质不变。
"""
from __future__ import annotations

from palworld_terminal.presentation.command_registry import HELP_TEXT
from palworld_terminal.presentation.formatters import format_help


class _Features:
    def __init__(self, groups: dict[str, bool]) -> None:
        self._groups = groups

    def enabled(self, group: str) -> bool:
        return self._groups.get(group, False)


def _feats(**over) -> _Features:
    # core 恒开（真实 FeaturesConfig.enabled("core") 恒 True）——confirm/link 等 core 动作
    # 的可见性由角色门决定，功能门恒通过。
    base = {
        "core": True, "server_admin_basic": True, "server_admin_danger": True,
        "guilds_bases": False, "events": False, "report": False, "players": False,
    }
    base.update(over)
    return _Features(base)


def test_help_hides_write_commands_from_non_admin():
    out = format_help(None, is_admin=False, features=_feats())
    assert "/pal server kick" not in out
    assert "/pal server ban" not in out
    assert "/pal server announce" not in out
    assert "/pal confirm" not in out


def test_help_shows_write_commands_to_admin_when_enabled():
    out = format_help(None, is_admin=True, features=_feats())
    for frag in ("/pal server announce", "/pal server save", "/pal server kick",
                 "/pal server unban", "/pal server ban", "/pal server shutdown",
                 "/pal server stop", "/pal confirm"):
        assert frag in out


def test_help_hides_write_commands_when_group_disabled_even_for_admin():
    out = format_help(
        None, is_admin=True,
        features=_feats(server_admin_basic=False, server_admin_danger=False),
    )
    assert "/pal server kick" not in out       # danger 组关
    assert "/pal server announce" not in out   # basic 组关
    # confirm 是 core，仅受 is_admin 门（不受组门），管理员仍可见
    assert "/pal confirm" in out


def test_help_text_confirm_present_no_keyerror():
    # format_help 取 HELP_TEXT["confirm"]；confirm 缺描述会渲染无描述行。
    assert "confirm" in HELP_TEXT
    assert HELP_TEXT["confirm"]
