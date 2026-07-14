from palworld_terminal.presentation.config_view import (
    redact_config,
    validate_and_backfill,
)


def _ok(body):
    return validate_and_backfill(body, {}, {})


def test_permission_admins_roundtrip_and_row_id():
    red = redact_config({"permission_admins": [{"id": "aiocqhttp:1", "note": "群主"}]})
    assert red["permission_admins"][0]["__row_id"] == "adm-0"


def test_command_permissions_valid():
    ok, res = _ok({"command_permissions": [
        {"command": "player info", "enabled": "inherit", "admin_only": "on"}]})
    assert ok
    assert res["command_permissions"][0]["admin_only"] == "on"


def test_command_permissions_non_list_rejected():
    ok, err = _ok({"command_permissions": {"evil": 1}})
    assert not ok and err["error"] == "invalid_shape"


def test_command_permissions_unknown_command_rejected():
    ok, err = _ok({"command_permissions": [{"command": "bogus"}]})
    assert not ok and err["error"] == "invalid_field"


def test_command_permissions_strips_meta():
    ok, res = _ok({"command_permissions": [
        {"command": "guild", "enabled": "on", "admin_only": "inherit",
         "__row_id": "cmd-0", "junk": 1}]})
    assert ok
    assert res["command_permissions"][0] == {
        "command": "guild", "enabled": "on", "admin_only": "inherit"}


def test_permission_admins_strips_meta():
    ok, res = _ok({"permission_admins": [{"id": "aiocqhttp:1", "note": "x", "__row_id": "adm-0", "junk": 1}]})
    assert ok
    assert res["permission_admins"][0] == {"id": "aiocqhttp:1", "note": "x"}


def test_single_allowed_groups_roundtrip_row_id():
    cfg = {"single_allowed_groups": [{"umo": "aiocqhttp:GroupMessage:1", "note": "x"}]}
    out = redact_config(cfg)
    assert out["single_allowed_groups"][0]["__row_id"] == "sag-0"
    assert out["single_allowed_groups"][0]["umo"] == "aiocqhttp:GroupMessage:1"


def test_single_allowed_groups_strips_meta():
    ok, res = _ok({"single_allowed_groups": [
        {"__row_id": "sag-0", "umo": "u", "note": "n", "junk": "x"}]})
    assert ok
    assert set(res["single_allowed_groups"][0]) == {"umo", "note"}
