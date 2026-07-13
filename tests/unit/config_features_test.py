"""features 配置解析：默认值、显式覆盖、enabled() 助手（spec §3）。"""
from palworld_terminal.config import FeaturesConfig, parse_config


def _raw(features=None):
    cfg = {"servers": [], "routing": {"access_mode": "open", "default_server": ""},
           "group_bindings": [], "polling": {}, "world": {}, "bases": {},
           "privacy": {"mode": "balanced"}, "history": {}}
    if features is not None:
        cfg["features"] = features
    return cfg


def test_features_default_when_absent():
    f = parse_config(_raw(), {}).features
    assert f.report is True and f.events is True and f.guilds_bases is False


def test_features_explicit_override():
    f = parse_config(_raw({"report": False, "events": False, "guilds_bases": True}), {}).features
    assert f.report is False and f.events is False and f.guilds_bases is True


def test_enabled_helper():
    f = FeaturesConfig(report=True, events=False, guilds_bases=False)
    assert f.enabled("core") is True
    assert f.enabled("report") is True
    assert f.enabled("events") is False
    assert f.enabled("guilds_bases") is False
    assert f.enabled("nope") is False


def test_features_players_default_off():
    f = parse_config(_raw(), {}).features
    assert f.players is False


def test_features_players_enabled_helper():
    f = FeaturesConfig(report=True, events=True, guilds_bases=False, players=True)
    assert f.enabled("players") is True
    assert FeaturesConfig(report=True, events=True, guilds_bases=False).enabled("players") is False


def test_features_players_explicit_on():
    f = parse_config(_raw({"players": True}), {}).features
    assert f.players is True
