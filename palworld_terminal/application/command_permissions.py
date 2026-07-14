"""统一层级权限模型：命令节点生效值 + 派生元数据 + 采集派生（spec §1/§3/§6）。

纯函数、无 IO；元数据全部从 command_registry 派生（零手工数据），防漂移测试锚定。
"""
from __future__ import annotations

from dataclasses import dataclass

from ..presentation.command_registry import (
    DISPATCH,
    FLAT_ACTIONS,
    LOCKABLE_COMMANDS,
)

FEATURE_DEFAULTS: dict[str, bool] = {
    "core": True, "report": True, "events": True,
    "guilds_bases": False, "players": False,
    "server_admin_basic": False, "server_admin_danger": False,
}

DANGER_COMMANDS: frozenset[str] = frozenset({
    "server ban", "server shutdown", "server stop",
})


@dataclass(frozen=True, slots=True)
class CommandMeta:
    path: str
    group: str | None
    feat_group: str
    gate: str


def _build_meta() -> dict[str, CommandMeta]:
    out: dict[str, CommandMeta] = {}
    for grp, actions in DISPATCH.items():
        for sub, (_method, feat, gate) in actions.items():
            path = f"{grp} {sub}"
            out[path] = CommandMeta(path=path, group=grp, feat_group=feat, gate=gate)
    for name, (_method, feat, gate) in FLAT_ACTIONS.items():
        out[name] = CommandMeta(path=name, group=None, feat_group=feat, gate=gate)
    return out


COMMAND_META: dict[str, CommandMeta] = _build_meta()


def enable_configurable(path: str) -> bool:
    m = COMMAND_META.get(path)
    return m is not None and m.feat_group != "core"


def admin_forced_true(path: str) -> bool:
    m = COMMAND_META.get(path)
    return m is not None and m.gate in ("admin_write", "admin")


def admin_configurable(path: str) -> bool:
    return path in LOCKABLE_COMMANDS


def default_enabled(path: str) -> bool:
    m = COMMAND_META.get(path)
    if m is None:
        return False
    return FEATURE_DEFAULTS.get(m.feat_group, False)


def group_of(path: str) -> str | None:
    m = COMMAND_META.get(path)
    return m.group if m is not None else None
