"""players 配置节解析：rank_top_n 默认、exclude_names 逗号分隔（spec §7）。"""
from palchronicle.config import PlayersConfig, parse_config


def _raw(players=None):
    cfg = {"servers": [], "routing": {"access_mode": "open", "default_server": ""},
           "group_bindings": [], "polling": {}, "world": {}, "bases": {},
           "privacy": {"mode": "balanced"}, "history": {}}
    if players is not None:
        cfg["players"] = players
    return cfg


def test_players_defaults_when_absent():
    p = parse_config(_raw(), {}).players
    assert p.rank_top_n == 5
    assert p.exclude_names == []


def test_players_rank_top_n_override():
    assert parse_config(_raw({"rank_top_n": 10}), {}).players.rank_top_n == 10


def test_exclude_names_comma_split_and_trim():
    p = parse_config(_raw({"exclude_names": " Alice , Bob ,,Carol "}), {}).players
    assert p.exclude_names == ["Alice", "Bob", "Carol"]


def test_players_config_is_dataclass():
    p = PlayersConfig(rank_top_n=3, exclude_names=["x"])
    assert p.rank_top_n == 3 and p.exclude_names == ["x"]
