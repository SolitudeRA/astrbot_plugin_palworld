"""admin_only_commands 未知锁条目校验 + 告警（防扁平→分级格式迁移静默失锁）。

命令串后续从扁平（player）变完整路径（player info）。旧配置里的锁条目升级后
若不再匹配 LOCKABLE_COMMANDS，会静默 no-op = fail-open。本测试钉住：未知条目
必须保留在 admin_only_commands（不改现有锁行为）且被收集进 unknown_locks
（供 T9 启动告警），绝不静默吞。
"""
from palworld_terminal.config import parse_config
from palworld_terminal.presentation.command_registry import LOCKABLE_COMMANDS


def _base(**over):
    raw = {"servers": [], "routing": {}, "polling": {}, "world": {}, "bases": {},
           "privacy": {}, "history": {}, "features": {}, "players": {}}
    raw.update(over)
    return parse_config(raw, {})


def test_unknown_lock_kept_and_collected():
    # "totally_not_a_command" 在扁平与完整路径下都不存在 → 未知锁
    cfg = _base(admin_only_commands=["totally_not_a_command", "player"])
    # 未知条目进 unknown_locks
    assert "totally_not_a_command" in cfg.permissions.unknown_locks
    # 未知条目保留在 admin_only_commands（不静默吞、不改现有锁行为）
    assert "totally_not_a_command" in cfg.permissions.admin_only_commands


def test_known_lock_not_flagged_unknown():
    cfg = _base(admin_only_commands=["totally_not_a_command", "player"])
    # 合法锁（此刻扁平 "player" ∈ LOCKABLE_COMMANDS）不进 unknown_locks
    assert "player" in LOCKABLE_COMMANDS  # 前提自证
    assert "player" not in cfg.permissions.unknown_locks
    assert "player" in cfg.permissions.admin_only_commands


def test_unknown_locks_default_empty():
    cfg = _base()
    assert cfg.permissions.unknown_locks == []


def test_non_lockable_not_treated_as_unknown():
    # 不可锁集（server/whoami/help/confirm 等）是既有静默剔除行为，
    # 不应被误报为未知锁——它们既不在 admin_only_commands 也不在 unknown_locks。
    cfg = _base(admin_only_commands=["server", "whoami", "help", "confirm"])
    assert cfg.permissions.admin_only_commands == []
    assert cfg.permissions.unknown_locks == []
