from palworld_terminal.config import AppConfig, parse_config
from palworld_terminal.domain.enums import AccessMode


def _server(**kw):
    base = {
        "name": "s1", "enabled": True, "base_url": "http://127.0.0.1:8212",
        "username": "admin", "password": "pw", "password_env": "",
        "timeout": 10, "verify_tls": True, "timezone": "",
    }
    base.update(kw)
    return base


def test_parse_normal_server():
    cfg = parse_config({"servers": [_server()]}, env={})
    assert isinstance(cfg, AppConfig)
    assert len(cfg.servers) == 1
    s = cfg.servers[0]
    assert s.server_id == "s1"
    assert s.ready is True
    assert cfg.skipped == []


def test_empty_name_skipped():
    cfg = parse_config({"servers": [_server(name="   ")]}, env={})
    assert cfg.servers == []
    assert [(x.reason) for x in cfg.skipped] == ["empty"]


def test_duplicate_name_skipped():
    cfg = parse_config({"servers": [_server(name="dup"), _server(name="dup")]}, env={})
    assert len(cfg.servers) == 1
    assert cfg.servers[0].server_id == "dup"
    assert [x.reason for x in cfg.skipped] == ["duplicate"]


def test_illegal_char_names_skipped():
    for bad in ("a:b", "a@b", "a b"):
        cfg = parse_config({"servers": [_server(name=bad)]}, env={})
        assert cfg.servers == [], bad
        assert cfg.skipped[0].reason == "illegal_char", bad


def test_password_env_takes_precedence():
    cfg = parse_config(
        {"servers": [_server(password="plain", password_env="PAL_PW")]},
        env={"PAL_PW": "fromenv"},
    )
    assert cfg.servers[0].password == "fromenv"
    assert cfg.servers[0].ready is True


def test_plaintext_password_fallback_when_env_missing():
    cfg = parse_config(
        {"servers": [_server(password="plain", password_env="")]},
        env={},
    )
    assert cfg.servers[0].password == "plain"


def test_no_credential_marks_not_ready_and_diagnoses():
    cfg = parse_config(
        {"servers": [_server(password="", password_env="")]},
        env={},
    )
    assert len(cfg.servers) == 1
    assert cfg.servers[0].ready is False
    assert any(x.reason == "no_credential" for x in cfg.skipped)


def test_routing_and_polling_defaults():
    cfg = parse_config({"servers": []}, env={})
    assert cfg.routing.access_mode is AccessMode.RESTRICTED
    assert cfg.routing.default_server == ""
    assert cfg.polling.metrics_seconds == 30
    assert cfg.polling.info_seconds == 600
    assert cfg.polling.jitter_ratio == 0.10
    assert cfg.polling.max_concurrency == 6
    assert cfg.world.timezone == "Asia/Tokyo"
    assert cfg.bases.assignment_radius == 5000
    assert cfg.privacy.mode == "balanced"
    assert cfg.history.observation_days == 180


def test_bindings_parsed_from_top_level():
    cfg = parse_config(
        {"servers": [_server()], "group_bindings": [{"umo": "u1", "server": "s1", "active": True}]},
        env={},
    )
    assert len(cfg.group_bindings) == 1
    assert cfg.group_bindings[0].umo == "u1"
    assert cfg.group_bindings[0].server == "s1"
    assert cfg.group_bindings[0].active is True


def test_presentation_me_card_theme_default_and_enum():
    # 缺省 → light
    cfg = parse_config({"servers": []}, env={})
    assert cfg.presentation.me_card_theme == "light"
    # 合法枚举原样保留
    for theme in ("light", "dark", "auto"):
        cfg = parse_config({"presentation": {"me_card_theme": theme}}, env={})
        assert cfg.presentation.me_card_theme == theme
    # 非法 → 回落 light
    cfg = parse_config({"presentation": {"me_card_theme": "rainbow"}}, env={})
    assert cfg.presentation.me_card_theme == "light"


def test_malformed_numeric_values_degrade_to_defaults():
    # 手改配置文件留下畸形数值:降级为默认,不炸插件启动
    raw = {
        "servers": [{"name": "a", "base_url": "http://x", "username": "u",
                     "password": "pw", "timeout": "abc"}],
        "polling": {"metrics_seconds": "oops", "jitter_ratio": None},
        "privacy": {"ping_good_ms": []},
    }
    cfg = parse_config(raw, {})
    assert cfg.servers[0].timeout == 10
    assert cfg.polling.metrics_seconds == 30
    assert cfg.polling.jitter_ratio == 0.10
    assert cfg.privacy.ping_good_ms == 60
