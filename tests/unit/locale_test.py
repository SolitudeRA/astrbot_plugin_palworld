import pytest

from palworld_terminal.presentation.locale import MESSAGES, L


def test_no_server_configured_message():
    assert "尚未配置" in L("no_server_configured")


def test_degraded_message_formats_minutes():
    text = L("degraded", minutes=5)
    assert "5" in text
    assert "无法获取" in text


def test_not_authorized_message_includes_server():
    text = L("not_authorized", server="alpha")
    assert "alpha" in text


def test_never_says_server_offline():
    # privacy/honesty red line: degradation must not claim shutdown
    assert "关机" not in MESSAGES["degraded"]


def test_admin_required_message():
    assert L("admin_required") == "该命令需要管理员权限。"


def test_missing_key_raises():
    with pytest.raises(KeyError):
        L("this_key_does_not_exist")
