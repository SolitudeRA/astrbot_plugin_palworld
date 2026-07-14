"""分级命令真相源锚定（spec §3 命令树 / §8 锚定）。

本任务 additive：只锚新增的分发表 + 完整路径常量（新名 DISPATCH / PAL_REGISTERED
/ PAL_COMMAND_PATHS / _NON_LOCKABLE_PATHS / LOCKABLE_PATHS），旧 26 扁平锚定
（command_names_test）保持不动、仍绿；getattr introspection 锚定留 T7。
"""
from palworld_terminal.presentation.command_registry import (
    _NON_LOCKABLE_PATHS,
    DISPATCH,
    LOCKABLE_PATHS,
    PAL_COMMAND_PATHS,
    PAL_REGISTERED,
)


def test_pal_registered_is_eleven_first_words():
    # 注册身份 = 11 首词（5 组 + 6 扁平）；AstrBot 只认首词，子动作 Commands 自解析。
    assert set(PAL_REGISTERED) == {
        "world", "guild", "player", "server", "link",
        "rank", "online", "me", "help", "whoami", "confirm",
    }
    assert len(PAL_REGISTERED) == 11


def test_dispatch_groups_have_all_subactions():
    assert set(DISPATCH["world"]) == {"status", "overview", "rules", "events", "today"}
    assert set(DISPATCH["guild"]) == {"list", "info", "bases", "base"}
    assert set(DISPATCH["player"]) == {"info", "bind", "unbind"}
    assert set(DISPATCH["server"]) == {
        "announce", "save", "kick", "unban", "ban", "shutdown", "stop"}
    assert set(DISPATCH["link"]) == {"list", "add", "remove"}


def test_command_paths_full_hierarchy():
    # 完整路径 = f"{组} {动作}" 各组 + 扁平命令名
    assert "world status" in PAL_COMMAND_PATHS
    assert "server kick" in PAL_COMMAND_PATHS
    assert "guild info" in PAL_COMMAND_PATHS
    assert "player unbind" in PAL_COMMAND_PATHS
    assert "rank" in PAL_COMMAND_PATHS  # 扁平命令直接入路径集


def test_non_lockable_paths_cover_writes_link_and_meta():
    # server 各动作 + link 各动作 + 元命令（help/whoami/confirm）绝不可锁
    assert "server kick" in _NON_LOCKABLE_PATHS
    assert "server stop" in _NON_LOCKABLE_PATHS
    assert "link add" in _NON_LOCKABLE_PATHS
    assert "link remove" in _NON_LOCKABLE_PATHS
    assert "help" in _NON_LOCKABLE_PATHS
    assert "whoami" in _NON_LOCKABLE_PATHS
    assert "confirm" in _NON_LOCKABLE_PATHS


def test_lockable_paths_is_complement():
    assert LOCKABLE_PATHS == frozenset(PAL_COMMAND_PATHS) - _NON_LOCKABLE_PATHS
    assert "world status" in LOCKABLE_PATHS
    assert "rank" in LOCKABLE_PATHS  # rank 可锁
    assert "server kick" not in LOCKABLE_PATHS
    assert "help" not in LOCKABLE_PATHS
    # 不可锁集与可锁集无交集
    assert not (_NON_LOCKABLE_PATHS & LOCKABLE_PATHS)


def test_write_actions_route_admin_write_with_correct_group():
    # 写子动作逐一：gate=admin_write 且映射正确功能组（防漏门=无鉴权关服）。
    basic = {"announce", "save", "kick", "unban"}
    danger = {"ban", "shutdown", "stop"}
    for sub, (_method, group, gate) in DISPATCH["server"].items():
        assert gate == "admin_write", sub
        if sub in basic:
            assert group == "server_admin_basic", sub
        elif sub in danger:
            assert group == "server_admin_danger", sub


def test_action_spec_shape():
    # ActionSpec = (方法名, 功能门组, gate)；gate ∈ {read, admin_write, admin}。
    for _group, actions in DISPATCH.items():
        for _sub, spec in actions.items():
            assert isinstance(spec, tuple) and len(spec) == 3
            method, feat, gate = spec
            assert isinstance(method, str) and method
            assert isinstance(feat, str) and feat
            assert gate in ("read", "admin_write", "admin")
