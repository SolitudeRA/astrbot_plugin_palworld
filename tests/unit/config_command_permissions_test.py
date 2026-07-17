from palworld_terminal.application.command_permissions import (
    effective_admin_only as eao,
)
from palworld_terminal.application.command_permissions import (
    effective_enabled as ee,
)
from palworld_terminal.application.command_permissions import (
    upstream_unavailable_group,
)
from palworld_terminal.config import parse_config


def _cfg(raw):
    return parse_config(raw, {})


def _row(cmd, enabled="inherit", admin_only="inherit"):
    return {"command": cmd, "enabled": enabled, "admin_only": admin_only}


def test_rows_parsed_to_overrides():
    # enable 传导示范载体迁 player（可配组）；guild list admin_only 轴不受 force-off 影响，
    # 仍属 LOCKABLE，保留其锁传导断言。
    cfg = _cfg({"command_permissions": [
        _row("player", enabled="on"),
        _row("world today", enabled="off"),
        _row("guild list", admin_only="on"),
    ]})
    ov = cfg.permissions.command_overrides
    assert ee(ov, "player info") is True
    assert ee(ov, "world today") is False
    assert eao(ov, "guild list") is True


def test_tristate_inherit_is_none():
    cfg = _cfg({"command_permissions": [_row("guild", enabled="inherit", admin_only="inherit")]})
    # 两轴 inherit → 无有效覆盖（可为空或该键两字段皆 None）
    ov = cfg.permissions.command_overrides
    assert ee(ov, "guild list") is False        # 走默认


def test_invalid_command_and_axis_logged():
    cfg = _cfg({"command_permissions": [
        _row("nonsense", enabled="on"),           # 未知命令
        _row("world status", enabled="off"),       # core 不可配 enable
        _row("link list", admin_only="on"),        # 不可配 admin
        _row("server kick", admin_only="off"),     # 恒真轴
    ]})
    ov = cfg.permissions.command_overrides
    inv = cfg.permissions.invalid_command_keys
    assert "nonsense" in inv
    assert any("world status" in x for x in inv)   # 轴违规也登记（F3）
    assert any("link list" in x for x in inv)
    assert ee(ov, "world status") is True
    assert eao(ov, "link list") is False
    assert eao(ov, "server kick") is True


def test_upstream_unavailable_group_derived_from_constant():
    # 组内全部叶子的 feat_group ∈ UPSTREAM_UNAVAILABLE_FEATURES 才算组级不可用；
    # 由常量 + COMMAND_META 派生，不硬编码组名 'guild'。
    assert upstream_unavailable_group("guild") is True
    assert upstream_unavailable_group("world") is False   # world 含 core/report/events 叶子
    assert upstream_unavailable_group("player") is False
    assert upstream_unavailable_group("nope") is False     # 无成员组不算不可用


def test_upstream_on_diverted_from_axis_invalid():
    # 叶子行与组名行 enabled=on：均入 upstream_ineffective_keys、均不进 invalid_command_keys；
    # 生效值仍 False（effective_enabled force-off），raw 行照常落盘回读。
    cfg = _cfg({"command_permissions": [
        _row("guild list", enabled="on"),   # 叶子完整路径（enable_configurable 已翻 False）
        _row("guild", enabled="on"),        # 组名行（is_group 短路，旧路径漏收集）
    ]})
    ineff = cfg.permissions.upstream_ineffective_keys
    inv = cfg.permissions.invalid_command_keys
    assert "guild list:enabled" in ineff
    assert "guild:enabled" in ineff
    assert "guild list:enabled" not in inv     # 不落轴违规路径（§2 非目标）
    assert "guild:enabled" not in inv
    ov = cfg.permissions.command_overrides
    assert ee(ov, "guild list") is False       # 配置的 on 不生效


def test_upstream_off_inherit_not_collected():
    # enabled ∈ {off, inherit}：用户预期即关闭，不告警、不入 invalid。
    cfg = _cfg({"command_permissions": [
        _row("guild list", enabled="off"),
        _row("guild", enabled="inherit"),
    ]})
    assert cfg.permissions.upstream_ineffective_keys == ()
    assert cfg.permissions.invalid_command_keys == []


def test_upstream_admin_only_axis_untouched():
    # admin_only 轴零改动：guild list 仍 LOCKABLE，走原逻辑，不进 upstream_ineffective。
    cfg = _cfg({"command_permissions": [_row("guild list", admin_only="on")]})
    assert cfg.permissions.upstream_ineffective_keys == ()
    ov = cfg.permissions.command_overrides
    assert eao(ov, "guild list") is True
