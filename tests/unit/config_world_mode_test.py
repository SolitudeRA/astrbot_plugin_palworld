from palworld_terminal.config import parse_config


def _base(**routing):
    raw = {"servers": [], "routing": routing, "polling": {}, "world": {}, "bases": {},
           "privacy": {}, "history": {}, "features": {}, "players": {}}
    return parse_config(raw, {})


def test_world_mode_default_single():
    assert _base().routing.world_mode == "single"


def test_world_mode_single():
    assert _base(world_mode="single").routing.world_mode == "single"


def test_world_mode_invalid_falls_back_single():
    assert _base(world_mode="oops").routing.world_mode == "single"


def test_conf_schema_world_mode_enum():
    import json
    from pathlib import Path
    s = json.loads((Path(__file__).resolve().parents[2] / "_conf_schema.json").read_text(encoding="utf-8"))
    wm = s["routing"]["items"]["world_mode"]
    assert wm["type"] == "string" and set(wm["options"]) == {"multi", "single"} and wm["default"] == "single"


def test_config_view_enums_has_world_mode():
    from palworld_terminal.presentation.config_view import _ENUMS
    assert "routing.world_mode" in _ENUMS
