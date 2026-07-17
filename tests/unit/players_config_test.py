"""players 配置节解析：rank_top_n 默认、exclude_names 逗号分隔（spec §7）。"""
from palworld_terminal.config import PlayersConfig, parse_config


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


# ---- list_fold_limit（spec §2.7 / §5#10：clamp ≥1，默认 7）----

def test_list_fold_limit_default_when_absent():
    assert parse_config(_raw(), {}).players.list_fold_limit == 7


def test_list_fold_limit_override():
    assert parse_config(_raw({"list_fold_limit": 15}), {}).players.list_fold_limit == 15


def test_list_fold_limit_zero_clamps_to_one():
    assert parse_config(_raw({"list_fold_limit": 0}), {}).players.list_fold_limit == 1


def test_list_fold_limit_negative_clamps_to_one():
    assert parse_config(_raw({"list_fold_limit": -3}), {}).players.list_fold_limit == 1


def test_list_fold_limit_malformed_falls_back_to_default():
    assert parse_config(_raw({"list_fold_limit": "abc"}), {}).players.list_fold_limit == 7


# ---- rank_top_n clamp（spec §2.7 / §5#10：1–50，0/负回默认 5）----

def test_rank_top_n_zero_returns_default():
    assert parse_config(_raw({"rank_top_n": 0}), {}).players.rank_top_n == 5


def test_rank_top_n_negative_returns_default():
    assert parse_config(_raw({"rank_top_n": -3}), {}).players.rank_top_n == 5


def test_rank_top_n_over_max_clamps_to_50():
    assert parse_config(_raw({"rank_top_n": 200}), {}).players.rank_top_n == 50


def test_rank_top_n_at_bounds_pass_through():
    assert parse_config(_raw({"rank_top_n": 1}), {}).players.rank_top_n == 1
    assert parse_config(_raw({"rank_top_n": 50}), {}).players.rank_top_n == 50


def test_rank_top_n_malformed_returns_default():
    assert parse_config(_raw({"rank_top_n": "xyz"}), {}).players.rank_top_n == 5
