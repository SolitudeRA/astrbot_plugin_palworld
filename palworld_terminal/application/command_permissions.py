"""统一层级权限模型：命令节点生效值 + 派生元数据 + 采集派生（spec §1/§3/§6）。

纯函数、无 IO；元数据全部从 command_registry 派生（零手工数据），防漂移测试锚定。
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..domain.enums import EndpointName
from ..shared.command_registry import (
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

# 上游不可用 feature 集：/game-data（PalGameDataBridge）对专用服务器未开放
# （2026-07-12 实测定论：404 "GameData API is not enabled"，无任何参数可开启）。
# 集内 feature 的命令恒禁用且不可配置；上游开放后的恢复操作：从本集合删除该
# feature + 同步前端 PAL_TREE（schema.ts 的 unavailable/enableConfigurable/
# defaultEnabled）——跨端锚定测试红→绿即恢复护栏。详见 spec §7。
UPSTREAM_UNAVAILABLE_FEATURES: frozenset[str] = frozenset({"guilds_bases"})


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


def upstream_unavailable(path: str) -> bool:
    m = COMMAND_META.get(path)
    return m is not None and m.feat_group in UPSTREAM_UNAVAILABLE_FEATURES


def upstream_unavailable_group(group: str) -> bool:
    """组名行的上游不可用判定：组内全部叶子的 feat_group ∈ 上游不可用集才成立。

    由常量 + COMMAND_META 派生（禁止硬编码 'guild'）——将来新增 unavailable
    feature 时组级分流自动覆盖，不漏。空成员组返回 False。
    """
    metas = [m for m in COMMAND_META.values() if m.group == group]
    return bool(metas) and all(m.feat_group in UPSTREAM_UNAVAILABLE_FEATURES for m in metas)


def enable_configurable(path: str) -> bool:
    m = COMMAND_META.get(path)
    return (
        m is not None
        and m.feat_group != "core"
        and m.feat_group not in UPSTREAM_UNAVAILABLE_FEATURES
    )


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


@dataclass(frozen=True, slots=True)
class CommandOverride:
    enabled: bool | None = None
    admin_only: bool | None = None


def effective_enabled(overrides: Mapping[str, CommandOverride], path: str) -> bool:
    if upstream_unavailable(path):
        return False  # 上游不可用硬锁：先于一切覆盖（与 enable_configurable 排除构成双保险）
    if not enable_configurable(path):
        return default_enabled(path)
    leaf = overrides.get(path)
    if leaf is not None and leaf.enabled is not None:
        return leaf.enabled
    if path in DANGER_COMMANDS:
        return default_enabled(path)            # danger 不从组键继承（F2）
    grp = group_of(path)
    if grp is not None:
        g = overrides.get(grp)
        if g is not None and g.enabled is not None:
            return g.enabled
    return default_enabled(path)


def effective_admin_only(overrides: Mapping[str, CommandOverride], path: str) -> bool:
    if admin_forced_true(path):
        return True
    if not admin_configurable(path):
        return False
    leaf = overrides.get(path)
    if leaf is not None and leaf.admin_only is not None:
        return leaf.admin_only
    grp = group_of(path)
    if grp is not None:
        g = overrides.get(grp)
        if g is not None and g.admin_only is not None:
            return g.admin_only
    return False


OBSERVATION_FLOOR: frozenset[EndpointName] = frozenset({
    EndpointName.INFO, EndpointName.METRICS, EndpointName.PLAYERS, EndpointName.SETTINGS,
})

_DERIVED_ENDPOINT_FEATURE: dict[EndpointName, str] = {
    EndpointName.GAME_DATA: "guilds_bases",
}


def active_endpoints(overrides: Mapping[str, CommandOverride]) -> frozenset[EndpointName]:
    active = set(OBSERVATION_FLOOR)
    for ep, feat in _DERIVED_ENDPOINT_FEATURE.items():
        if any(
            m.feat_group == feat and effective_enabled(overrides, p)
            for p, m in COMMAND_META.items()
        ):
            active.add(ep)
    return frozenset(active)


# ---- legacy → command_permissions 三态行迁移（装载时一次性；复核 F1/B2）----
# feature 布尔 -> (默认, 命令键列表)。旧值 != 默认才产 enable 行。
# 键既可为组名（guild/player）也可为完整路径（world today/server announce）或扁平
# 命令（rank/me）——parse_config 三态行清洗对三者皆能识别。
_FEATURE_MIGRATION: dict[str, tuple[bool, tuple[str, ...]]] = {
    "report": (True, ("world today",)),
    "events": (True, ("world events",)),
    "guilds_bases": (False, ("guild",)),
    "players": (False, ("player", "rank", "me")),
    "server_admin_basic": (False, ("server announce", "server save",
                                   "server kick", "server unban")),
    "server_admin_danger": (False, ("server ban", "server shutdown", "server stop")),
}


def migrate_legacy_to_rows(raw: Mapping) -> tuple[list[dict[str, str]], list[str]]:
    """旧 features + admin_only_commands → command_permissions 三态行 + 非法锁键。

    - features 布尔 ≠ 默认才产 enable 行（on/off）；键分派到对应命令键。
    - admin_only_commands 各条 ∈ LOCKABLE_COMMANDS → admin_only 行，否则进 invalid。
    - 同一命令的 enable/admin 合并成一行；未涉及的轴填 "inherit"。
    """
    acc: dict[str, dict[str, str]] = {}      # command -> {enabled?, admin_only?}
    invalid: list[str] = []

    f = raw.get("features", {}) or {}
    if isinstance(f, Mapping):
        for feat, (default, keys) in _FEATURE_MIGRATION.items():
            val = bool(f.get(feat, default))
            if val != default:
                for key in keys:
                    acc.setdefault(key, {})["enabled"] = "on" if val else "off"

    raw_cmds = raw.get("admin_only_commands", [])
    if isinstance(raw_cmds, list):
        for c in raw_cmds:
            if not isinstance(c, str):
                continue
            name = c.strip()
            if not name:
                continue
            if name in LOCKABLE_COMMANDS:
                acc.setdefault(name, {})["admin_only"] = "on"
            else:
                invalid.append(name)

    rows: list[dict[str, str]] = [
        {"command": cmd,
         "enabled": v.get("enabled", "inherit"),
         "admin_only": v.get("admin_only", "inherit")}
        for cmd, v in acc.items()
    ]
    return rows, invalid
