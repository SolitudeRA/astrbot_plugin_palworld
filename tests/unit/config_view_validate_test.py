"""config/save 校验与哨仓回填：形状/类型/白名单/体积/语义/哨兵/凭证重定向。"""
from palworld_terminal.presentation.config_view import (
    SENTINEL,
    redact_config,
    validate_and_backfill,
)


def _old():
    return {
        "servers": [
            {"name": "alpha", "base_url": "http://h:8212", "username": "admin",
             "password": "oldpw", "password_env": "", "timeout": 10,
             "enabled": True, "verify_tls": True, "timezone": ""},
        ],
        "custom_headers": [
            {"name": "X-Token", "value": "oldtok", "value_env": "", "servers": ""},
        ],
        "group_bindings": [],
        "routing": {"access_mode": "restricted", "default_server": ""},
        "polling": {"metrics_seconds": 30},
        "world": {"fps_smooth": 50},
        "bases": {}, "privacy": {"mode": "balanced"}, "history": {},
    }


def _body(**over):
    # 模拟页面回传：带 __row_id，敏感字段用哨兵
    b = {
        "servers": [{"__row_id": "srv-0", "name": "alpha",
                     "base_url": "http://h:8212", "username": "admin",
                     "password": SENTINEL, "password_env": "", "timeout": 10,
                     "enabled": True, "verify_tls": True, "timezone": "",
                     "password_set": True}],
        "custom_headers": [{"__row_id": "hdr-0", "name": "X-Token",
                            "value": SENTINEL, "value_env": "", "servers": "",
                            "value_set": True}],
        "group_bindings": [],
        "routing": {"access_mode": "restricted", "default_server": ""},
        "polling": {"metrics_seconds": 30}, "world": {"fps_smooth": 50},
        "bases": {}, "privacy": {"mode": "balanced"}, "history": {},
    }
    b.update(over)
    return b


def test_sentinel_backfills_old_secret_and_strips_meta_keys():
    ok, cand = validate_and_backfill(_body(), _old(), {})
    assert ok is True
    s = cand["servers"][0]
    assert s["password"] == "oldpw"        # 哨兵回填旧值
    assert "__row_id" not in s and "password_set" not in s  # 元键剥离
    assert cand["custom_headers"][0]["value"] == "oldtok"


def test_explicit_new_value_overrides():
    body = _body()
    body["servers"][0]["password"] = "newpw"
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok and cand["servers"][0]["password"] == "newpw"


def test_explicit_empty_clears_secret():
    body = _body()
    body["servers"][0]["password"] = ""
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok and cand["servers"][0]["password"] == ""


def test_new_row_with_sentinel_rejected():
    body = _body()
    body["servers"][0]["__row_id"] = "srv-99"  # 无匹配
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_field"
    assert err["detail"]["path"] == "servers[0].password"


def test_reorder_or_delete_matches_by_row_id_not_index():
    # 页面删掉了原 hdr-0，新增一条排在前面；旧 hdr-0 滑到索引 1 仍按 id 回填
    body = _body()
    body["custom_headers"] = [
        {"__row_id": None, "name": "X-New", "value": "brand", "value_env": "",
         "servers": "", "value_set": False},
        {"__row_id": "hdr-0", "name": "X-Token", "value": SENTINEL,
         "value_env": "", "servers": "", "value_set": True},
    ]
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok
    assert cand["custom_headers"][0]["value"] == "brand"
    assert cand["custom_headers"][1]["value"] == "oldtok"  # 按 id 不错绑


def test_credential_redirect_blocked_on_base_url_host_change():
    body = _body()
    body["servers"][0]["base_url"] = "http://attacker.example:8212"  # host 变
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "credential_redirect"
    assert err["detail"]["path"] == "servers[0].password"


def test_base_url_path_only_change_with_sentinel_ok():
    body = _body()
    body["servers"][0]["base_url"] = "http://h:8212/prefix"  # host 不变
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok and cand["servers"][0]["password"] == "oldpw"


def test_top_level_unknown_key_rejected():
    body = _body(evil="x")
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_shape"


def test_list_item_not_dict_rejected_no_crash():
    body = _body()
    body["servers"] = [123]
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_shape"


def test_enum_invalid_value_rejected_path_only_no_value():
    body = _body()
    body["routing"]["access_mode"] = "wideopen"
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_field"
    assert err["detail"]["path"] == "routing.access_mode"
    assert "wideopen" not in str(err)   # 非法值绝不出现在错误里


def test_int_field_not_convertible_rejected_path_only():
    body = _body()
    body["servers"][0]["timeout"] = "abc"
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_field"
    assert err["detail"]["path"] == "servers[0].timeout"
    assert "abc" not in str(err)


def test_body_too_large_rejected():
    body = _body()
    body["custom_headers"] = [
        {"__row_id": None, "name": f"X-{i}", "value": "v", "value_env": "",
         "servers": "", "value_set": False} for i in range(201)
    ]
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "too_large"


def test_unmatched_server_name_sentinel_rejected():
    # 改名 alpha→alpha2 且密码哨兵：__row_id 仍匹配旧条目，但用户想保留旧密码
    # 合法（id 匹配）；此用例验证「无 id 匹配才拒」已由 test_new_row 覆盖，
    # 这里验证改名但 id 命中时按 id 正常回填
    body = _body()
    body["servers"][0]["name"] = "alpha2"
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok and cand["servers"][0]["password"] == "oldpw"


def test_unknown_item_key_stripped_not_persisted():
    # F4 红线：列表项内任意未知键（schema 外）落盘前剔除，不持久化
    body = _body()
    body["servers"][0]["pwned"] = "x"
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok is True
    assert "pwned" not in cand["servers"][0]
    # 合法键仍在
    assert cand["servers"][0]["name"] == "alpha"


def test_negative_number_rejected():
    body = _body()
    body["servers"][0]["timeout"] = -5
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_field"
    assert err["detail"]["path"] == "servers[0].timeout"


def test_nan_and_inf_rejected():
    for bad in ("nan", "inf", "-inf"):
        body = _body()
        body["polling"]["jitter_ratio"] = bad
        ok, err = validate_and_backfill(body, _old(), {})
        assert ok is False and err["error"] == "invalid_field", bad
        assert err["detail"]["path"] == "polling.jitter_ratio"


def test_bool_not_accepted_as_number():
    body = _body()
    body["servers"][0]["timeout"] = True
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_field"
    assert err["detail"]["path"] == "servers[0].timeout"


def test_non_string_base_url_no_crash():
    # F9：非字符串 base_url + 哨兵密码不得抛 TypeError 冒泡成 500，须结构化错误
    body = _body()
    body["servers"][0]["base_url"] = 12345
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and isinstance(err, dict) and "error" in err


def test_command_permissions_row_shape_ok():
    body = {"command_permissions": [
        {"command": "guild", "enabled": "on", "admin_only": "inherit"},
        {"command": "guild list", "enabled": "inherit", "admin_only": "on"},
    ]}
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok is True
    assert cand["command_permissions"][0]["command"] == "guild"
    assert cand["command_permissions"][1]["admin_only"] == "on"


def test_command_permissions_row_rejects_bad():
    # 非法三态值
    ok, _ = validate_and_backfill(
        {"command_permissions": [{"command": "guild", "enabled": "yes"}]}, _old(), {})
    assert ok is False
    # 未知命令
    ok, _ = validate_and_backfill(
        {"command_permissions": [{"command": "nope"}]}, _old(), {})
    assert ok is False
    # 非列表形状
    ok, _ = validate_and_backfill(
        {"command_permissions": {"not": "list"}}, _old(), {})
    assert ok is False


def test_command_permissions_row_id_and_meta_stripped():
    red = redact_config({"command_permissions": [
        {"command": "guild", "enabled": "on", "admin_only": "inherit"}]})
    assert red["command_permissions"][0]["__row_id"] == "cmd-0"
    ok, cand = validate_and_backfill(
        {"command_permissions": [red["command_permissions"][0]]}, _old(), {})
    assert ok is True
    row = cand["command_permissions"][0]
    assert "__row_id" not in row
    assert row == {"command": "guild", "enabled": "on", "admin_only": "inherit"}


def test_top_keys_dropped_legacy():
    # features / admin_only_commands 已从白名单删除，作为顶层键一律拒绝
    ok, err = validate_and_backfill({"features": {"report": True}}, _old(), {})
    assert ok is False and err["error"] == "invalid_shape"
    ok, err = validate_and_backfill({"admin_only_commands": ["x"]}, _old(), {})
    assert ok is False and err["error"] == "invalid_shape"


def test_players_section_passthrough_unstripped():
    body = _body()
    body["players"] = {"rank_top_n": 8, "exclude_names": "Alice,Bob"}
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok is True
    assert cand["players"] == {"rank_top_n": 8, "exclude_names": "Alice,Bob"}


def test_players_rank_top_n_rejects_negative():
    body = _body()
    body["players"] = {"rank_top_n": -1, "exclude_names": ""}
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_field"


def test_routing_setup_confirmed_true_preserved_roundtrip():
    # 已确认零回归：setup_confirmed=True 经校验原样保留
    body = _body()
    body["routing"]["setup_confirmed"] = True
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok is True and cand["routing"]["setup_confirmed"] is True


def test_routing_setup_confirmed_default_false_preserved_roundtrip():
    # 默认 False（未确认）同样原样保留
    body = _body()
    body["routing"]["setup_confirmed"] = False
    ok, cand = validate_and_backfill(body, _old(), {})
    assert ok is True and cand["routing"]["setup_confirmed"] is False


def test_routing_setup_confirmed_non_bool_rejected():
    # spec §4.3：非 bool 的 setup_confirmed → invalid_shape（路径响亮拒绝）
    body = _body()
    body["routing"]["setup_confirmed"] = "yes"
    ok, err = validate_and_backfill(body, _old(), {})
    assert ok is False and err["error"] == "invalid_shape"
    assert err["detail"]["path"] == "routing.setup_confirmed"
