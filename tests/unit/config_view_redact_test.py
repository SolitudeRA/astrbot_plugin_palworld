"""config/get 脱敏读：明文绝不出站、稳定 row_id、env 名可回显值不读。"""
from palworld_terminal.presentation.config_view import redact_config


def _raw():
    return {
        "servers": [
            {"name": "alpha", "base_url": "http://h:8212", "username": "admin",
             "password": "topsecret", "password_env": ""},
            {"name": "beta", "base_url": "http://h:8213", "username": "admin",
             "password": "", "password_env": "BETA_PW"},
        ],
        "custom_headers": [
            {"name": "X-Token", "value": "hdrsecret", "value_env": "", "servers": ""},
            {"name": "X-Env", "value": "", "value_env": "TOK_ENV", "servers": "alpha"},
        ],
        "group_bindings": [{"umo": "u1", "server": "alpha", "active": True}],
        "routing": {"access_mode": "restricted", "default_server": ""},
    }


def test_password_plaintext_never_in_output():
    out = redact_config(_raw())
    import json
    blob = json.dumps(out)
    assert "topsecret" not in blob
    assert "hdrsecret" not in blob
    assert out["servers"][0]["password"] == ""
    assert out["custom_headers"][0]["value"] == ""


def test_password_set_flag_true_for_plaintext_and_env():
    out = redact_config(_raw())
    assert out["servers"][0]["password_set"] is True   # 明文
    assert out["servers"][1]["password_set"] is True   # env-only
    assert out["custom_headers"][0]["value_set"] is True
    assert out["custom_headers"][1]["value_set"] is True


def test_password_set_false_when_both_empty():
    raw = _raw()
    raw["servers"][0]["password"] = ""
    raw["servers"][0]["password_env"] = ""
    out = redact_config(raw)
    assert out["servers"][0]["password_set"] is False


def test_env_name_kept_value_not_read(monkeypatch):
    monkeypatch.setenv("BETA_PW", "env-plaintext")
    out = redact_config(_raw())
    import json
    assert "env-plaintext" not in json.dumps(out)
    assert out["servers"][1]["password_env"] == "BETA_PW"


def test_row_ids_injected_and_unique():
    out = redact_config(_raw())
    assert [s["__row_id"] for s in out["servers"]] == ["srv-0", "srv-1"]
    assert [h["__row_id"] for h in out["custom_headers"]] == ["hdr-0", "hdr-1"]
    assert out["group_bindings"][0]["__row_id"] == "bind-0"


def test_does_not_mutate_input():
    raw = _raw()
    redact_config(raw)
    assert raw["servers"][0]["password"] == "topsecret"  # 原对象不被改
    assert "__row_id" not in raw["servers"][0]


def test_non_list_sections_passthrough():
    out = redact_config(_raw())
    assert out["routing"] == {"access_mode": "restricted", "default_server": ""}
