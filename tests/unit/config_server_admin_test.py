from palworld_terminal.config import parse_config


def _base(**over):
    raw = {"servers": [], "routing": {}, "polling": {}, "world": {}, "bases": {},
           "privacy": {}, "history": {}, "features": {}, "players": {}}
    raw.update(over)
    return parse_config(raw, {})


def test_server_admin_defaults():
    sa = _base().server_admin
    assert sa.require_confirmation is False
    assert sa.confirmation_timeout == 30
    assert sa.audit_retention_days == 180


def test_server_admin_range_clamp():
    sa = _base(server_admin={"confirmation_timeout": 99999, "audit_retention_days": -5}).server_admin
    assert sa.confirmation_timeout == 600   # 上界 clamp [5,600]
    assert sa.audit_retention_days == 1     # 越界 clamp 到下界 [1,3650]


def test_server_admin_non_int_falls_back_default():
    sa = _base(server_admin={"confirmation_timeout": "oops"}).server_admin
    assert sa.confirmation_timeout == 30    # 非 int 回默认


def test_non_lockable_full_paths():
    from palworld_terminal.config import _NON_LOCKABLE
    assert _NON_LOCKABLE == frozenset({
        "server announce", "server save", "server kick", "server unban",
        "server ban", "server shutdown", "server stop",
        "link list", "link add", "link remove",
        "help", "whoami", "whereami", "confirm",
    })
