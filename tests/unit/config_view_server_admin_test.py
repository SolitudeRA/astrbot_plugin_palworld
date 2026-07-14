"""server_admin 配置段的前后端保存往返闭合校验。

T11 让 collectBody 产出顶层 server_admin 键，但 config_view._TOP_KEYS 未含它 →
携带 server_admin 的保存被 issubset 拒 invalid_shape。本测试锁定端到端闭合：
_TOP_KEYS 白名单接受、object 三字段形状/越界校验、redact 往返保留。
范围与 config.py::_parse_server_admin 一致：timeout[5,600] / retention[1,3650]。
"""
from palworld_terminal.presentation.config_view import (
    redact_config,
    validate_and_backfill,
)


def _ok(body):
    return validate_and_backfill(body, {}, {})


def _sa(**over):
    sa = {"require_confirmation": True, "confirmation_timeout": 30,
          "audit_retention_days": 180}
    sa.update(over)
    return sa


def test_server_admin_in_top_keys_roundtrip_ok():
    # _TOP_KEYS 闭合证据：携带 server_admin 的 body 不再被 issubset 拒 invalid_shape
    ok, cand = _ok({"server_admin": _sa()})
    assert ok is True
    assert cand["server_admin"] == _sa()  # 原样透传，未被剥离/篡改


def test_server_admin_defaults_valid():
    ok, cand = _ok({"server_admin": _sa(require_confirmation=False,
                                        confirmation_timeout=30,
                                        audit_retention_days=180)})
    assert ok is True


def test_server_admin_not_mapping_rejected():
    ok, err = _ok({"server_admin": ["not", "a", "mapping"]})
    assert ok is False and err["error"] == "invalid_shape"


def test_require_confirmation_non_bool_rejected():
    ok, err = _ok({"server_admin": _sa(require_confirmation="yes")})
    assert ok is False and err["error"] == "invalid_shape"
    assert err["detail"]["path"] == "server_admin.require_confirmation"


def test_confirmation_timeout_below_range_rejected():
    ok, err = _ok({"server_admin": _sa(confirmation_timeout=4)})
    assert ok is False and err["error"] == "invalid_shape"
    assert err["detail"]["path"] == "server_admin.confirmation_timeout"


def test_confirmation_timeout_above_range_rejected():
    ok, err = _ok({"server_admin": _sa(confirmation_timeout=601)})
    assert ok is False and err["error"] == "invalid_shape"


def test_confirmation_timeout_bounds_inclusive_ok():
    for v in (5, 600):
        ok, _ = _ok({"server_admin": _sa(confirmation_timeout=v)})
        assert ok is True, v


def test_audit_retention_below_range_rejected():
    ok, err = _ok({"server_admin": _sa(audit_retention_days=0)})
    assert ok is False and err["error"] == "invalid_shape"
    assert err["detail"]["path"] == "server_admin.audit_retention_days"


def test_audit_retention_above_range_rejected():
    ok, err = _ok({"server_admin": _sa(audit_retention_days=3651)})
    assert ok is False and err["error"] == "invalid_shape"


def test_audit_retention_bounds_inclusive_ok():
    for v in (1, 3650):
        ok, _ = _ok({"server_admin": _sa(audit_retention_days=v)})
        assert ok is True, v


def test_int_field_bool_not_accepted_as_number():
    # bool 是 int 子类，True==1 会误当合法 int——须显式拒
    ok, err = _ok({"server_admin": _sa(confirmation_timeout=True)})
    assert ok is False and err["error"] == "invalid_shape"
    assert err["detail"]["path"] == "server_admin.confirmation_timeout"


def test_int_field_string_not_accepted():
    ok, err = _ok({"server_admin": _sa(audit_retention_days="180")})
    assert ok is False and err["error"] == "invalid_shape"


def test_partial_server_admin_fields_ok():
    # 缺字段的 object（仅一字段）仍合法：缺项由 config.py 默认值兜底
    ok, cand = _ok({"server_admin": {"require_confirmation": True}})
    assert ok is True and cand["server_admin"] == {"require_confirmation": True}


def test_redact_config_preserves_server_admin():
    red = redact_config({"server_admin": _sa()})
    assert red["server_admin"] == _sa()
