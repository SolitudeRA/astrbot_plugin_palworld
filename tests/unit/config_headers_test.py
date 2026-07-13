"""custom_headers 解析：校验/作用域/去重/SkippedHeader（spec §3.2/§3.3/§6）。"""
from palworld_terminal.config import SkippedHeader, parse_config


def _raw(custom_headers=None):
    cfg = {"servers": [
        {"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
         "username": "admin", "password": "pw", "__template_key": "server"},
        {"name": "beta", "enabled": True, "base_url": "http://127.0.0.1:8213",
         "username": "admin", "password": "pw", "__template_key": "server"},
    ]}
    if custom_headers is not None:
        cfg["custom_headers"] = custom_headers
    return cfg


def _hdr(**kw):
    # 模拟 WebUI 保存形状：恒含 __template_key 附加键（解析必须忽略它）
    item = {"name": "", "value": "", "value_env": "", "servers": "",
            "__template_key": "header"}
    item.update(kw)
    return item


def _by_name(cfg):
    return {s.name: s for s in cfg.servers}


def test_no_custom_headers_key_backwards_compatible():
    cfg = parse_config(_raw(), {})
    assert all(s.headers == {} for s in cfg.servers)
    assert cfg.skipped_headers == []


def test_custom_headers_none_value_backwards_compatible():
    raw = _raw()
    raw["custom_headers"] = None
    cfg = parse_config(raw, {})
    assert all(s.headers == {} for s in cfg.servers)
    assert cfg.skipped_headers == []


def test_value_env_wins_over_value():
    cfg = parse_config(
        _raw([_hdr(name="X-Token", value="plain", value_env="MY_TOKEN")]),
        {"MY_TOKEN": "from-env"},
    )
    assert _by_name(cfg)["alpha"].headers == {"X-Token": "from-env"}


def test_value_env_missing_falls_back_to_value():
    cfg = parse_config(
        _raw([_hdr(name="X-Token", value="plain", value_env="ABSENT")]), {},
    )
    assert _by_name(cfg)["alpha"].headers == {"X-Token": "plain"}


def test_both_value_sources_empty_skipped():
    cfg = parse_config(_raw([_hdr(name="X-Token")]), {})
    assert all(s.headers == {} for s in cfg.servers)
    assert cfg.skipped_headers == [SkippedHeader("X-Token", "empty_value")]


def test_value_stripped_before_send():
    cfg = parse_config(_raw([_hdr(name="X-Token", value="  tok  ")]), {})
    assert _by_name(cfg)["alpha"].headers == {"X-Token": "tok"}


def test_scope_empty_applies_to_all_servers():
    cfg = parse_config(_raw([_hdr(name="X-A", value="1")]), {})
    by = _by_name(cfg)
    assert by["alpha"].headers == {"X-A": "1"}
    assert by["beta"].headers == {"X-A": "1"}


def test_scope_limits_to_listed_servers():
    cfg = parse_config(
        _raw([_hdr(name="X-A", value="1", servers="alpha"),
              _hdr(name="X-B", value="2", servers=" alpha , beta ")]), {},
    )
    by = _by_name(cfg)
    assert by["alpha"].headers == {"X-A": "1", "X-B": "2"}
    assert by["beta"].headers == {"X-B": "2"}


def test_scope_all_empty_segments_means_zero_servers():
    # ",," 非空但切分后无有效段：fail-closed，绝不回退到全部（spec §3.2.5）
    cfg = parse_config(_raw([_hdr(name="X-A", value="1", servers=",,")]), {})
    assert all(s.headers == {} for s in cfg.servers)
    assert cfg.skipped_headers == []  # 零作用域不是 skip


def test_scope_all_unknown_names_means_zero_servers():
    cfg = parse_config(_raw([_hdr(name="X-A", value="1", servers="typo")]), {})
    assert all(s.headers == {} for s in cfg.servers)
    assert cfg.skipped_headers == []


def test_scope_is_case_sensitive():
    cfg = parse_config(_raw([_hdr(name="X-A", value="1", servers="Alpha")]), {})
    assert all(s.headers == {} for s in cfg.servers)


def test_reserved_headers_skipped_case_and_whitespace_insensitive():
    reserved = ["authorization", "Host", "CONTENT-LENGTH",
                "Transfer-Encoding", "connection", "Expect",
                " authorization", "AUTHORIZATION"]
    cfg = parse_config(
        _raw([_hdr(name=n, value="v") for n in reserved]), {},
    )
    assert all(s.headers == {} for s in cfg.servers)
    assert [h.reason for h in cfg.skipped_headers] == ["reserved"] * len(reserved)


def test_illegal_names_skipped():
    cfg = parse_config(
        _raw([_hdr(name="X Name", value="v"),
              _hdr(name="X:Name", value="v"),
              _hdr(name="标头", value="v"),
              _hdr(name="   ", value="v")]), {},
    )
    assert all(s.headers == {} for s in cfg.servers)
    assert [h.reason for h in cfg.skipped_headers] == [
        "illegal_name", "illegal_name", "illegal_name", "empty_name"]


def test_illegal_values_skipped_tab_allowed():
    cfg = parse_config(
        _raw([_hdr(name="X-A", value="bad\rv"),
              _hdr(name="X-B", value="bad\nv"),
              _hdr(name="X-C", value="bad\x00v"),
              _hdr(name="X-D", value="bad\x7fv"),
              _hdr(name="X-E", value="ok\tv")]), {},
    )
    assert _by_name(cfg)["alpha"].headers == {"X-E": "ok\tv"}
    assert [h.reason for h in cfg.skipped_headers] == ["illegal_value"] * 4


def test_case_insensitive_dedup_later_wins_and_keeps_later_case():
    cfg = parse_config(
        _raw([_hdr(name="x-token", value="first"),
              _hdr(name="X-TOKEN", value="second")]), {},
    )
    assert _by_name(cfg)["alpha"].headers == {"X-TOKEN": "second"}


def test_skipped_header_never_contains_value():
    cfg = parse_config(_raw([_hdr(name="bad name", value="s3cret")]), {})
    (h,) = cfg.skipped_headers
    assert h.raw_name == "bad name"
    assert "s3cret" not in h.raw_name and "s3cret" not in h.reason
