from palworld_terminal.application.command_permissions import (
    effective_admin_only as eao,
)
from palworld_terminal.application.command_permissions import (
    effective_enabled as ee,
)
from palworld_terminal.config import parse_config


def _cfg(raw):
    return parse_config(raw, {})


def _row(cmd, enabled="inherit", admin_only="inherit"):
    return {"command": cmd, "enabled": enabled, "admin_only": admin_only}


def test_rows_parsed_to_overrides():
    cfg = _cfg({"command_permissions": [
        _row("guild", enabled="on"),
        _row("world today", enabled="off"),
        _row("guild list", admin_only="on"),
    ]})
    ov = cfg.permissions.command_overrides
    assert ee(ov, "guild info") is True
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
