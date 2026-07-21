"""分级 help + 裸组迷你帮助角色隔离（安全线）+ 单模式省 link + 谓词单一真相源。

安全性质（本任务安全线）：guest 的 /pal server 裸组帮助**绝不含** kick/ban/stop——
_group_help 复用 format_help 同一 `visible_actions` 谓词（不另写一份过滤，杜绝漂移）。
confirm 仅管理员见；功能门关的组不列子动作；单世界模式 help 省略 link 组。
"""
from __future__ import annotations

from types import SimpleNamespace

from palworld_terminal.shared.command_registry import (
    HELP_TEXT,
    PAL_COMMAND_STRINGS,
)
from palworld_terminal.presentation.commands import Commands
from palworld_terminal.presentation.formatters import format_help, visible_actions
from tests.unit._perm import all_on as _all_on
from tests.unit._perm import overrides

# ============================================================================
# visible_actions —— 单一真相源（role filter + feature filter + 单模式省 link）
# ============================================================================

def test_visible_actions_server_hidden_from_guest():
    # 安全线核心：server 全写动作对 guest 恒不可见（gate=admin_write）。
    assert visible_actions("server", False, _all_on(), "multi") == []
    admin = {sub for sub, _spec in visible_actions("server", True, _all_on(), "multi")}
    assert admin == {"announce", "save", "kick", "unban", "ban", "shutdown", "stop"}


def test_visible_actions_link_omitted_in_single_mode():
    assert visible_actions("link", True, _all_on(), "single") == []
    multi = {sub for sub, _spec in visible_actions("link", True, _all_on(), "multi")}
    assert multi == {"list", "add", "remove"}


def test_visible_actions_link_add_remove_admin_only():
    guest = {sub for sub, _spec in visible_actions("link", False, _all_on(), "multi")}
    assert guest == {"list"}  # add/remove(gate=admin) 对 guest 不可见


def test_visible_actions_feature_gate():
    # 功能门示范载体迁 player（可启用组）：关→空、开→全子动作。
    assert visible_actions("player", True, overrides(players=False), "multi") == []
    on = {sub for sub, _spec in visible_actions("player", True, overrides(players=True), "multi")}
    assert on == {"info", "bind", "unbind"}


def test_visible_actions_guild_force_off():
    # guilds_bases 上游不可用：guild 组恒不可见（即便 overrides on）。
    assert visible_actions("guild", True, overrides(guilds_bases=True), "multi") == []
    assert visible_actions("guild", True, _all_on(), "multi") == []


# ============================================================================
# format_help —— 分级视图
# ============================================================================

def test_format_help_admin_hierarchical_full_paths():
    out = format_help(None, is_admin=True, overrides=_all_on(), world_mode="multi")
    for frag in ("/pal world status", "/pal world today", "/pal player bind",
                 "/pal server kick", "/pal server stop", "/pal link add",
                 "/pal rank", "/pal confirm"):
        assert frag in out, frag
    # guilds_bases 上游不可用：guild 组与 world overview 恒不列（即便 _all_on）。
    assert "/pal guild info" not in out
    assert "/pal world overview" not in out


def test_format_help_omits_unavailable_guild_and_overview():
    # §5B⑤：help/裸组恒不含 guild 组与 world overview（force-off，两角色皆然）。
    for admin in (True, False):
        out = format_help(None, is_admin=admin, overrides=_all_on(), world_mode="multi")
        for frag in ("/pal guild list", "/pal guild info", "/pal guild bases",
                     "/pal guild base", "/pal world overview"):
            assert frag not in out, (admin, frag)


def test_format_help_guest_hides_writes_and_confirm():
    out = format_help(None, is_admin=False, overrides=_all_on(), world_mode="multi")
    for frag in ("/pal server kick", "/pal server ban", "/pal server stop",
                 "/pal server announce", "/pal link add", "/pal link remove",
                 "/pal confirm"):
        assert frag not in out, frag
    # 读命令仍在
    assert "/pal world status" in out and "/pal rank" in out and "/pal link list" in out


def test_format_help_omits_guild_when_disabled():
    out = format_help(None, is_admin=True,
                      overrides=overrides(guilds_bases=False), world_mode="multi")
    assert "/pal guild info" not in out and "/pal guild list" not in out
    assert "/pal world status" in out


def test_format_help_single_mode_omits_link_group():
    single = format_help(None, is_admin=True, overrides=_all_on(), world_mode="single")
    assert "/pal link" not in single
    multi = format_help(None, is_admin=True, overrides=_all_on(), world_mode="multi")
    assert "/pal link add" in multi


def test_format_help_confirm_admin_only():
    guest = format_help(None, is_admin=False, overrides=_all_on(), world_mode="multi")
    admin = format_help(None, is_admin=True, overrides=_all_on(), world_mode="multi")
    assert "/pal confirm" not in guest
    assert "/pal confirm" in admin


# ============================================================================
# help-text 覆盖（防漂移：每条完整路径恰有一条描述，双向全等）
# ============================================================================

def test_help_text_covers_all_command_paths_exactly():
    paths = set(PAL_COMMAND_STRINGS)
    keys = set(HELP_TEXT)
    assert keys == paths, f"缺描述: {paths - keys}; 多余描述: {keys - paths}"


# ============================================================================
# 裸组迷你帮助角色隔离（安全线）：_group_help 复用同一 visible_actions 谓词
# ============================================================================

def _cmds(overrides_map=None):
    cfg = SimpleNamespace(
        permissions=SimpleNamespace(
            command_overrides=_all_on() if overrides_map is None else overrides_map),
        server_admin=SimpleNamespace(require_confirmation=False, confirmation_timeout=30),
        servers=[], skipped=[],
    )
    return Commands(None, None, None, cfg, SimpleNamespace(now=lambda: 0))


async def test_bare_server_group_help_hides_writes_from_guest():
    c = _cmds()
    out = await c.server_grp("u", "/pal server", True, "guest", False)
    for frag in ("kick", "ban", "stop", "announce", "save", "unban", "shutdown"):
        assert frag not in out, frag


async def test_bare_server_group_help_shows_writes_to_admin():
    c = _cmds()
    out = await c.server_grp("u", "/pal server", True, "admin", True)
    assert "kick" in out and "stop" in out and "ban" in out


async def test_bare_guild_group_help_empty_when_disabled():
    c = _cmds(overrides(guilds_bases=False))
    out = await c.guild_grp("u", "/pal guild", True, "guest", False)
    for frag in ("list", "info", "bases", "base"):
        assert frag not in out, frag
