from palworld_terminal.shared import command_permissions as cp
from palworld_terminal.shared.command_registry import (
    _NON_LOCKABLE,
    DISPATCH,
    FLAT_ACTIONS,
    PAL_COMMAND_STRINGS,
)


def test_meta_covers_exactly_all_command_strings():
    assert set(cp.COMMAND_META) == set(PAL_COMMAND_STRINGS)


def test_enable_configurable_is_non_core():
    assert cp.enable_configurable("world today") is True
    assert cp.enable_configurable("world status") is False
    assert cp.enable_configurable("online") is False
    assert cp.enable_configurable("server ban") is True


def test_admin_configurable_derived_independently():
    # 独立验证 LOCKABLE ⟺ gate==read ∧ ∉ NON_LOCKABLE（非同义反复）
    for grp, actions in DISPATCH.items():
        for sub, (_m, _f, gate) in actions.items():
            path = f"{grp} {sub}"
            expect = gate == "read" and path not in _NON_LOCKABLE
            assert cp.admin_configurable(path) is expect, path
    for name, (_m, _f, gate) in FLAT_ACTIONS.items():
        expect = gate == "read" and name not in _NON_LOCKABLE
        assert cp.admin_configurable(name) is expect, name


def test_admin_forced_true_for_writes_and_admin_gate():
    assert cp.admin_forced_true("server kick") is True
    assert cp.admin_forced_true("link add") is True
    assert cp.admin_forced_true("confirm") is True
    assert cp.admin_forced_true("world status") is False


def test_default_enabled_matches_feature_defaults():
    assert cp.default_enabled("world status") is True
    assert cp.default_enabled("world today") is True
    assert cp.default_enabled("world events") is True
    assert cp.default_enabled("guild list") is False
    assert cp.default_enabled("rank") is False
    assert cp.default_enabled("server ban") is False


def test_group_of_and_danger():
    assert cp.group_of("world today") == "world"
    assert cp.group_of("rank") is None
    assert cp.DANGER_COMMANDS == frozenset({"server ban", "server shutdown", "server stop"})


def test_all_gated_methods_in_method_path():
    # METHOD_PATH 须覆盖全部 @_gated 方法名，否则运行时 METHOD_PATH[fn.__name__] KeyError。
    from palworld_terminal.shared.command_registry import METHOD_PATH
    gated = {"guilds", "guild", "bases", "base", "events", "today",
             "rank", "player", "bind", "me", "unbind_self"}   # 现 @_gated 方法名
    assert gated <= set(METHOD_PATH)
