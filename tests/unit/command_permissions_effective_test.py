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
    # 三级继承示范载体 = player（可配 / 默认关 / 非 unavailable；改动前 guild 的角色）。
    assert ee({}, "world today") is True
    assert ee({}, "player info") is False
    assert ee({"player": CO(enabled=True)}, "player info") is True
    ov = {"player": CO(enabled=True), "player info": CO(enabled=False)}
    assert ee(ov, "player info") is False
    assert ee(ov, "player bind") is True


def test_upstream_unavailable_force_off_all_five_paths():
    # game-data 上游不可用硬锁（§5B①）：5 条命令在 leaf on / 组 on 覆盖下 effective_enabled
    # 恒 False（force-off 首行先于叶子/组覆盖/默认）。
    for path in ("world overview", "guild list", "guild info", "guild bases", "guild base"):
        assert ee({}, path) is False, path
        assert ee({path: CO(enabled=True)}, path) is False, path          # 叶子 on
    for path in ("guild list", "guild info", "guild bases", "guild base"):
        assert ee({"guild": CO(enabled=True)}, path) is False, path        # 组 on

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
