import json
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
