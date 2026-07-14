import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_schema():
    return json.loads((REPO_ROOT / "_conf_schema.json").read_text(encoding="utf-8"))


def test_top_level_keys_present_and_types():
    s = load_schema()
    assert s["servers"]["type"] == "template_list"
    assert s["group_bindings"]["type"] == "template_list"
    assert s["custom_headers"]["type"] == "template_list"
    for key in ("routing", "polling", "world", "bases", "privacy", "history"):
        assert s[key]["type"] == "object", f"{key} must be object"


def test_servers_template_items_and_defaults():
    items = load_schema()["servers"]["templates"]["server"]["items"]
    assert set(items) == {
        "name", "enabled", "base_url", "username",
        "password", "password_env", "timeout", "verify_tls", "timezone",
    }
    assert items["base_url"]["default"] == "http://127.0.0.1:8212"
    assert items["enabled"]["default"] is True
    assert items["timeout"]["default"] == 10


def test_group_bindings_is_top_level_not_nested_in_routing():
    s = load_schema()
    assert "group_bindings" not in s["routing"].get("items", {})
    b = s["group_bindings"]["templates"]["binding"]["items"]
    assert set(b) == {"umo", "server", "active"}


def test_routing_defaults():
    items = load_schema()["routing"]["items"]
    assert items["access_mode"]["default"] == "restricted"
    assert items["default_server"]["default"] == ""


def test_polling_defaults():
    items = load_schema()["polling"]["items"]
    assert items["metrics_seconds"]["default"] == 30
    assert items["players_seconds"]["default"] == 30
    assert items["info_seconds"]["default"] == 600
    assert items["settings_seconds"]["default"] == 1800
    assert items["game_data_seconds"]["default"] == 120
    assert items["jitter_ratio"]["default"] == 0.10
    assert items["max_concurrency"]["default"] == 6


def test_world_bases_privacy_history_defaults():
    s = load_schema()
    assert s["world"]["items"]["timezone"]["default"] == "Asia/Tokyo"
    assert s["world"]["items"]["fps_smooth"]["default"] == 50
    assert s["bases"]["items"]["assignment_radius"]["default"] == 5000
    assert s["bases"]["items"]["position_grid_size"]["default"] == 2000
    assert s["privacy"]["items"]["mode"]["default"] == "balanced"
    assert s["privacy"]["items"]["ping_ok_ms"]["default"] == 120
    assert s["history"]["items"]["raw_metrics_days"]["default"] == 7
    assert s["history"]["items"]["observation_days"]["default"] == 180


def test_custom_headers_template_items_and_defaults():
    s = load_schema()
    ch = s["custom_headers"]
    assert ch["default"] == []
    assert ch["templates"]["header"]["display_item"] == "name"
    items = ch["templates"]["header"]["items"]
    assert set(items) == {"name", "value", "value_env", "servers"}
    assert all(items[k]["default"] == "" for k in items)


def test_features_section():
    s = load_schema()
    assert s["features"]["type"] == "object"
    items = s["features"]["items"]
    assert items["report"]["default"] is True
    assert items["events"]["default"] is True
    assert items["guilds_bases"]["default"] is False
    assert items["players"]["default"] is False


def test_permission_schema_present():
    import json
    from pathlib import Path
    schema = json.loads((Path(__file__).resolve().parents[2] / "_conf_schema.json").read_text(encoding="utf-8"))
    assert schema["permission_admins"]["type"] == "template_list"
    assert schema["admin_only_commands"]["type"] == "list"
    assert schema["admin_only_commands"]["default"] == []


def test_admin_only_commands_hint_examples_are_lockable():
    """admin_only_commands 描述里 `反引号` 圈出的可锁示例必须真在 LOCKABLE_COMMANDS 中。

    命令分级后扁平 `player` 已不可锁（只有 `player info`/`player bind`/`player unbind`）；
    描述若再举扁平/不可锁示例，管理员照抄会得到静默 no-op 锁 → 玩家查询对全员开放
    （fail-open）。锚定到 command_registry.LOCKABLE_COMMANDS，示例再漂移即红。
    """
    from palworld_terminal.presentation.command_registry import LOCKABLE_COMMANDS

    desc = load_schema()["admin_only_commands"]["description"]
    tokens = re.findall(r"`([^`]+)`", desc)
    assert tokens, "描述里应至少有一个 `反引号` 圈出的可锁示例"
    for tok in tokens:
        assert tok in LOCKABLE_COMMANDS, (
            f"admin_only_commands 描述示例 `{tok}` 不在 LOCKABLE_COMMANDS 中"
        )


def test_server_admin_schema_present():
    s = load_schema()
    assert s["features"]["items"]["server_admin_basic"]["type"] == "bool"
    assert s["features"]["items"]["server_admin_basic"]["default"] is False
    assert s["features"]["items"]["server_admin_danger"]["type"] == "bool"
    assert s["features"]["items"]["server_admin_danger"]["default"] is False
    assert s["server_admin"]["type"] == "object"
    items = s["server_admin"]["items"]
    assert items["require_confirmation"]["type"] == "bool"
    assert items["require_confirmation"]["default"] is False
    assert items["confirmation_timeout"]["type"] == "int"
    assert items["confirmation_timeout"]["default"] == 30
    assert items["audit_retention_days"]["type"] == "int"
    assert items["audit_retention_days"]["default"] == 180
