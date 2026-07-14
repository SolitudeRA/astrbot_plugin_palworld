from palworld_terminal.presentation.config_view import (
    redact_config,
    validate_and_backfill,
)


def _ok(body):
    return validate_and_backfill(body, {}, {})


def test_permission_admins_roundtrip_and_row_id():
    red = redact_config({"permission_admins": [{"id": "aiocqhttp:1", "note": "群主"}]})
    assert red["permission_admins"][0]["__row_id"] == "adm-0"


def test_admin_only_commands_valid():
    ok, res = _ok({"admin_only_commands": ["player", "rank"]})
    assert ok and res["admin_only_commands"] == ["player", "rank"]


def test_admin_only_commands_non_list_rejected():
    ok, err = _ok({"admin_only_commands": {"evil": 1}})
    assert not ok and err["error"] == "invalid_shape"


def test_admin_only_commands_non_str_element_rejected():
    ok, err = _ok({"admin_only_commands": ["player", 123]})
    assert not ok and err["error"] == "invalid_shape"


def test_permission_admins_strips_meta():
    ok, res = _ok({"permission_admins": [{"id": "aiocqhttp:1", "note": "x", "__row_id": "adm-0", "junk": 1}]})
    assert ok
    assert res["permission_admins"][0] == {"id": "aiocqhttp:1", "note": "x"}
