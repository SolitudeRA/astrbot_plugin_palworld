"""Task 13：help 素节头重做 + 横切拦截文案（spec §3/§4.26/§6#3）。

覆盖：
- help 标题 📖、素节头（废【】）、组头词表统一定字（世界/公会/玩家/服务器管控（管理员）/
  服务器授权/其他）、行式 `· /pal {路径} {描述}`、多模式尾注 vs 单模式省略。
- help 跳过 parse_arg：`/pal help x @a @b` 双 @ 不再裸抛 ArgError（§6#3）。
- admin_required / private_restricted 戴 ⚠️；其余六路由分支保持素文（无图标）。
- feature_disabled 主句戴 ⚠️ + 条件脚注：普通 off 带「设置页开启」引导；upstream_unavailable
  （gamedata 锁定）省略脚注（设置页开不了，假承诺）。
- 角色隔离在重设计后存活（guest 不见 kick/ban/stop/confirm）。
"""
from __future__ import annotations

from types import SimpleNamespace

from palworld_terminal.presentation.commands import Commands, feature_disabled_text
from palworld_terminal.presentation.formatters import format_help
from palworld_terminal.presentation.locale import MESSAGES, L
from tests.unit._perm import all_on as _all_on


def _cmds(world_mode: str = "multi"):
    cfg = SimpleNamespace(
        permissions=SimpleNamespace(command_overrides=_all_on()),
        routing=SimpleNamespace(world_mode=world_mode),
    )
    return Commands(None, None, None, cfg, SimpleNamespace(now=lambda: 0))


# ============================================================================
# help 素节头 + 组头词表 + 行式
# ============================================================================

def test_help_title_icon_no_colon():
    out = format_help(None, is_admin=True, overrides=_all_on(), world_mode="multi")
    assert out.splitlines()[0] == "📖 PalWorldTerminal 命令"
    assert "命令：" not in out  # 旧冒号标题退役


def test_help_group_headers_plain_and_wordlist():
    lines = format_help(None, is_admin=True, overrides=_all_on(), world_mode="multi").splitlines()
    # 组头词表统一定字（素节头，独立成行）。
    assert "世界" in lines
    assert "玩家" in lines
    assert "服务器管控（管理员）" in lines
    assert "服务器授权" in lines          # link 组（废「服务器选择」）
    assert "其他" in lines                # 扁平段
    # 【】节头彻底消失；旧词表退役。
    joined = "\n".join(lines)
    assert "【" not in joined and "】" not in joined
    assert "世界查询" not in joined
    assert "服务器选择" not in joined
    assert "公会与据点" not in joined


def test_help_line_bullet_single_space():
    out = format_help(None, is_admin=True, overrides=_all_on(), world_mode="multi")
    assert "· /pal world status 世界状态" in out
    assert "· /pal world rules 世界规则" in out


def test_help_footer_present_multi():
    out = format_help(None, is_admin=True, overrides=_all_on(), world_mode="multi")
    assert out.splitlines()[-1] == "└ 命令末尾加 @服务器名 可指定服务器"
    assert "提示：" not in out  # 旧尾注退役


def test_help_footer_omitted_single():
    out = format_help(None, is_admin=True, overrides=_all_on(), world_mode="single")
    # 单模式 resolve 忽略 @override，尾注是空承诺 → 省略。
    assert "@服务器名" not in out
    assert "└ 命令末尾" not in out


def test_help_guest_role_isolation_survives():
    guest = format_help(None, is_admin=False, overrides=_all_on(), world_mode="multi")
    for frag in ("/pal server kick", "/pal server ban", "/pal server stop", "/pal confirm"):
        assert frag not in guest, frag
    assert "/pal world status" in guest


# ============================================================================
# help 跳过 parse_arg（§6#3）：双 @ 不再裸抛 ArgError
# ============================================================================

def test_help_double_at_no_argerror():
    c = _cmds()
    # 尾双 @ 会让 parse_arg 抛 ArgError；help 跳过解析 → 正常出帮助、用户有回复。
    out = c.help("/pal help x @a @b", is_admin=True)
    assert out.startswith("📖 PalWorldTerminal 命令")


def test_help_single_mode_omits_footer_via_handler():
    single = _cmds(world_mode="single").help("/pal help", is_admin=True)
    assert "@服务器名" not in single


# ============================================================================
# 横切拦截文案：admin_required / private_restricted ⚠️；六路由分支素文
# ============================================================================

def test_admin_required_warning_icon():
    assert L("admin_required") == "⚠️ 该命令需要管理员权限"


def test_private_restricted_warning_icon():
    assert MESSAGES["private_restricted"].startswith("⚠️ ")
    assert "私聊" in MESSAGES["private_restricted"]  # PR#22 句沿用，仅加前缀


def test_six_routing_branches_stay_plain():
    # private_restricted 已摘出场景类 ⚠️；其余六分支为解析/授权失败，保持素文无图标。
    for key in ("no_server_configured", "single_not_authorized", "server_unknown",
                "not_authorized", "active_server_stale", "no_server_resolved"):
        assert "⚠️" not in MESSAGES[key], key
        assert "❌" not in MESSAGES[key], key
        assert "🔴" not in MESSAGES[key], key


# ============================================================================
# feature_disabled 主句 ⚠️ + 条件脚注（upstream_unavailable 省略）
# ============================================================================

def test_feature_disabled_main_clause_warning():
    assert MESSAGES["feature_disabled"] == "⚠️ 该功能未开启"


def test_feature_disabled_footnote_for_normal_off():
    # 普通 enable off：主句 + 「设置页开启」引导脚注（含解禁后的 guilds_bases）。
    for path in ("world events", "guild list", "world overview"):
        assert feature_disabled_text(path) == "⚠️ 该功能未开启\n└ 管理员可在插件设置页「权限」章开启", path
