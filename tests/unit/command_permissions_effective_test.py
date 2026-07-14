from palworld_terminal.application.command_permissions import (
    CommandOverride as CO,
)
from palworld_terminal.application.command_permissions import (
    effective_admin_only as eao,
)
from palworld_terminal.application.command_permissions import (
    effective_enabled as ee,
)


def test_enable_default_and_inheritance():
    assert ee({}, "world today") is True
    assert ee({}, "guild list") is False
    assert ee({"guild": CO(enabled=True)}, "guild list") is True
    ov = {"guild": CO(enabled=True), "guild list": CO(enabled=False)}
    assert ee(ov, "guild list") is False
    assert ee(ov, "guild info") is True

def test_enable_core_ignores_override():
    assert ee({"world status": CO(enabled=False)}, "world status") is True

def test_enable_flat_no_group_layer():
    assert ee({"rank": CO(enabled=True)}, "rank") is True

def test_danger_does_not_inherit_group_enable():
    # server 组键开 → basic 开，danger 仍关（复核 F2）
    ov = {"server": CO(enabled=True)}
    assert ee(ov, "server kick") is True        # basic 随组
    assert ee(ov, "server ban") is False         # danger 不随组
    assert ee({"server ban": CO(enabled=True)}, "server ban") is True   # 叶子显式可开

def test_admin_only_forced_and_fixed_open():
    assert eao({"server kick": CO(admin_only=False)}, "server kick") is True   # 恒真
    assert eao({"link list": CO(admin_only=True)}, "link list") is False        # 恒开放
    assert eao({"help": CO(admin_only=True)}, "help") is False

def test_admin_only_group_and_leaf():
    assert eao({"guild": CO(admin_only=True)}, "guild list") is True
    ov = {"guild": CO(admin_only=True), "guild list": CO(admin_only=False)}
    assert eao(ov, "guild list") is False
