from palworld_terminal.shared.command_permissions import migrate_legacy_to_rows


def _rows_map(rows):
    return {r["command"]: r for r in rows}


def test_migrate_features():
    rows, inv = migrate_legacy_to_rows({"features": {
        "guilds_bases": True, "players": True, "report": False}})
    m = _rows_map(rows)
    assert m["guild"]["enabled"] == "on"
    assert m["player"]["enabled"] == "on"
    assert m["rank"]["enabled"] == "on" and m["me"]["enabled"] == "on"
    assert m["world today"]["enabled"] == "off"
    assert "world events" not in m          # 默认未变不产行


def test_migrate_server_admin_leaves():
    rows, _ = migrate_legacy_to_rows({"features": {
        "server_admin_basic": True, "server_admin_danger": True}})
    m = _rows_map(rows)
    for p in ("server announce", "server save", "server kick", "server unban",
              "server ban", "server shutdown", "server stop"):
        assert m[p]["enabled"] == "on"


def test_migrate_admin_only_commands():
    rows, inv = migrate_legacy_to_rows({"admin_only_commands": ["guild list", "server kick"]})
    m = _rows_map(rows)
    assert m["guild list"]["admin_only"] == "on"
    assert "server kick" in inv             # 非 LOCKABLE


def test_merge_enable_and_admin_same_command():
    rows, _ = migrate_legacy_to_rows({
        "features": {"players": True}, "admin_only_commands": ["rank"]})
    m = _rows_map(rows)
    assert m["rank"]["enabled"] == "on" and m["rank"]["admin_only"] == "on"
