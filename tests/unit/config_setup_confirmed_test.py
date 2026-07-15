from palworld_terminal.config import parse_config


def test_setup_confirmed_default_false():
    cfg = parse_config({}, {})
    assert cfg.routing.setup_confirmed is False


def test_setup_confirmed_parsed_true():
    cfg = parse_config({"routing": {"setup_confirmed": True}}, {})
    assert cfg.routing.setup_confirmed is True


def test_setup_confirmed_strict_bool_rejects_string():
    # 严格 is True：字符串一律未确认（避免 bool("false")==True 脚枪）
    assert parse_config({"routing": {"setup_confirmed": "true"}}, {}).routing.setup_confirmed is False
    assert parse_config({"routing": {"setup_confirmed": "false"}}, {}).routing.setup_confirmed is False
    assert parse_config({"routing": {"setup_confirmed": 1}}, {}).routing.setup_confirmed is False
