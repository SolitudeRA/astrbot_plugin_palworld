# 分级感知权限（统一层级权限模型）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把权限/采集配置从「6 个功能组布尔 + 扁平锁列表」统一为「命令树节点承载 enabled + admin_only（稀疏覆盖 + 三级继承），采集派生自 enable」的单一控制面。

**Architecture:** 新增纯函数模块 `application/command_permissions.py`（生效值 + 派生元数据 + 采集派生，元数据全从 `command_registry` 派生，零手工数据）。配置存储用 AstrBot 原生 `template_list` 三态行 `{command, enabled, admin_only}`（复核 M1）；**装载时迁移旧键并落库**（复核 F1/B2）。门控各落点改查生效值。删除 `FeaturesConfig`/`feature_groups.py`/`COMMANDS`。前端权限章重做为命令树 UI。

**Tech Stack:** Python 3.10+（AstrBot 插件，dataclass slots）、pytest、ruff、mypy；前端 Vue 3 + TypeScript + Vitest。

## Global Constraints

- 版本**两源**（实测只有 `metadata.yaml` 的 `version:` + `main.py` L83 `@register(...,"v0.9.x")`；`pyproject.toml`/`package.json` **无**版本字段，勿去改）→ 本期 **v0.9.6**。
- 命令串真相源分家不变：`PAL_REGISTERED`(11 首词，注册锚定) vs `PAL_COMMAND_STRINGS`/`LOCKABLE_COMMANDS`/`_NON_LOCKABLE`（完整路径）。新派生元数据须交叉锚定 `command_registry`。
- 门序铁律不变：`admin_write` 内 admin 硬门**先于** enable 门；写/绑定/confirm 的 admin_only 恒真、结构不可绕；裸组角色隔离复用 `visible_actions` 单一谓词（guest 不泄漏 kick/ban/stop）。
- 可见性语义不回归：锁定读命令仍「可见但执行拒」，不引入「锁读→不可见」。
- **danger 命令（ban/shutdown/stop）不从 `server` 组键继承 enable**——须逐叶子显式 enable（复核 F2）。
- 脱敏红线不变：config_view 返回绝不含 password/value 明文；错误只含字段路径。
- 包内**禁绝对自导入前缀**（`no_absolute_self_import` 静态测试）——模块间用相对 import。config.py 顶层 `from .application.command_permissions import CommandOverride` **无循环**（`command_registry` 零 import、`presentation/__init__.py` 空），可直接顶层 import。
- 存储形状：`command_permissions` = `template_list` 行 `{command:str, enabled:str, admin_only:str}`，enabled/admin_only ∈ {"inherit","on","off"}。**不用**动态键 dict。
- 每任务结束：全库 `pytest -q`、`ruff check palworld_terminal`、`mypy palworld_terminal`、（触前端时）`cd frontend && npm run build && npm test` 全绿；`pages/settings` no-drift 不脏。
- 中文文案锚点：改 README/设置页中文用词须先 `grep tests/unit/readme_test.py` 中文锚点短语同步。

---

## 文件结构

| 文件 | 责任 | 动作 |
|---|---|---|
| `palworld_terminal/application/command_permissions.py` | 生效值 API + 派生元数据 + 采集派生（纯函数） | **新建** |
| `palworld_terminal/application/feature_groups.py` | 旧采集派生 | **删除** |
| `palworld_terminal/config.py` | 解析 command_permissions 行 → command_overrides；删 FeaturesConfig | 改 |
| `palworld_terminal/main.py` | 装载迁移落库；门控调用改传 overrides；`_log_startup_warnings` 重指 | 改 |
| `palworld_terminal/presentation/command_registry.py` | 命令树真相源；`METHOD_PATH`；删 COMMANDS/COMMAND_GROUP | 改 |
| `palworld_terminal/presentation/commands.py` | 门控落点改查生效值 | 改 |
| `palworld_terminal/presentation/formatters.py` | visible_actions/_action_visible/format_help 改吃 overrides | 改 |
| `palworld_terminal/container.py` | active_endpoints 接线 + L117-121 服务门 | 改 |
| `palworld_terminal/presentation/config_view.py` | command_permissions 列表节 + 校验 + 清死码 | 改 |
| `_conf_schema.json` | 删 features/admin_only_commands；加 command_permissions template_list | 改 |
| `frontend/src/lib/schema.ts` | `PAL_TREE`（JSON 可解析命令树） | 改 |
| `frontend/src/lib/chapters.ts` | 删 feature 章 | 改 |
| `frontend/src/components/SettingsPanel.vue` | 权限章命令树 UI + collectBody 行回写 | 改 |

**关键接口（贯穿全计划）：**

```python
@dataclass(frozen=True, slots=True)
class CommandOverride:
    enabled: bool | None = None
    admin_only: bool | None = None

COMMAND_META: dict[str, CommandMeta]
DANGER_COMMANDS: frozenset[str]        # {"server ban","server shutdown","server stop"}
def enable_configurable(path) -> bool
def admin_configurable(path) -> bool
def admin_forced_true(path) -> bool
def default_enabled(path) -> bool
def group_of(path) -> str | None
def effective_enabled(overrides, path) -> bool
def effective_admin_only(overrides, path) -> bool
def active_endpoints(overrides) -> frozenset[EndpointName]
def migrate_legacy_to_rows(raw: Mapping) -> tuple[list[dict], list[str]]   # (rows, invalid_keys)

@dataclass(slots=True)
class PermissionsConfig:
    admins: list[AdminEntry]
    command_overrides: dict[str, CommandOverride]
    invalid_command_keys: list[str] = field(default_factory=list)
    # 旧字段 admin_only_commands/unknown_locks 保留到 Task 8 才删（消费点全切换后）
```

---

## Task 1: 派生元数据模块 + 独立锚定

**Files:**
- Create: `palworld_terminal/application/command_permissions.py`
- Test: `tests/unit/command_permissions_meta_test.py`

**Interfaces:**
- Consumes: `command_registry.DISPATCH`/`FLAT_ACTIONS`/`_NON_LOCKABLE`/`LOCKABLE_COMMANDS`/`PAL_COMMAND_STRINGS`；`domain.enums.EndpointName`
- Produces: `CommandMeta`、`COMMAND_META`、`FEATURE_DEFAULTS`、`DANGER_COMMANDS`、`enable_configurable`、`admin_configurable`、`admin_forced_true`、`default_enabled`、`group_of`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/command_permissions_meta_test.py
from palworld_terminal.application import command_permissions as cp
from palworld_terminal.presentation.command_registry import (
    PAL_COMMAND_STRINGS, LOCKABLE_COMMANDS, _NON_LOCKABLE, DISPATCH, FLAT_ACTIONS,
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/command_permissions_meta_test.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# palworld_terminal/application/command_permissions.py
"""统一层级权限模型：命令节点生效值 + 派生元数据 + 采集派生（spec §1/§3/§6）。

纯函数、无 IO；元数据全部从 command_registry 派生（零手工数据），防漂移测试锚定。
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..domain.enums import EndpointName
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/command_permissions_meta_test.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/application/command_permissions.py tests/unit/command_permissions_meta_test.py
git commit -m "feat(perm): 命令节点派生元数据模块 + 独立锚定 + danger 分类"
```

---

## Task 2: 生效值三级继承 + danger 不继承组键

**Files:**
- Modify: `palworld_terminal/application/command_permissions.py`
- Test: `tests/unit/command_permissions_effective_test.py`

**Interfaces:**
- Consumes: Task 1
- Produces: `CommandOverride`、`effective_enabled(overrides, path)`、`effective_admin_only(overrides, path)`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/command_permissions_effective_test.py
from palworld_terminal.application.command_permissions import (
    CommandOverride as CO, effective_enabled as ee, effective_admin_only as eao,
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/command_permissions_effective_test.py -q`
Expected: FAIL（ImportError CommandOverride）

- [ ] **Step 3: 实现（追加）**

```python
@dataclass(frozen=True, slots=True)
class CommandOverride:
    enabled: bool | None = None
    admin_only: bool | None = None


def effective_enabled(overrides: Mapping[str, "CommandOverride"], path: str) -> bool:
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


def effective_admin_only(overrides: Mapping[str, "CommandOverride"], path: str) -> bool:
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/command_permissions_effective_test.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/application/command_permissions.py tests/unit/command_permissions_effective_test.py
git commit -m "feat(perm): 生效值三级继承 + danger 不继承组键 enable"
```

---

## Task 3: 采集派生 active_endpoints

**Files:**
- Modify: `palworld_terminal/application/command_permissions.py`
- Test: `tests/unit/command_permissions_endpoints_test.py`

**Interfaces:**
- Consumes: Task 1/2；`domain.enums.EndpointName`
- Produces: `OBSERVATION_FLOOR`、`active_endpoints(overrides)`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/command_permissions_endpoints_test.py
from palworld_terminal.application.command_permissions import (
    CommandOverride as CO, active_endpoints, OBSERVATION_FLOOR,
)
from palworld_terminal.domain.enums import EndpointName as E

def test_floor_always_present_even_when_all_disabled():
    ov = {g: CO(enabled=False) for g in ("world", "guild", "player", "server")}
    act = active_endpoints(ov)
    assert OBSERVATION_FLOOR <= act
    assert E.GAME_DATA not in act

def test_game_data_derived_from_guild_enable():
    assert E.GAME_DATA not in active_endpoints({})
    assert E.GAME_DATA in active_endpoints({"guild": CO(enabled=True)})
    assert E.GAME_DATA in active_endpoints({"guild bases": CO(enabled=True)})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/command_permissions_endpoints_test.py -q`
Expected: FAIL

- [ ] **Step 3: 实现（追加）**

```python
OBSERVATION_FLOOR: frozenset[EndpointName] = frozenset({
    EndpointName.INFO, EndpointName.METRICS, EndpointName.PLAYERS, EndpointName.SETTINGS,
})

_DERIVED_ENDPOINT_FEATURE: dict[EndpointName, str] = {
    EndpointName.GAME_DATA: "guilds_bases",
}


def active_endpoints(overrides: Mapping[str, "CommandOverride"]) -> frozenset[EndpointName]:
    active = set(OBSERVATION_FLOOR)
    for ep, feat in _DERIVED_ENDPOINT_FEATURE.items():
        if any(
            m.feat_group == feat and effective_enabled(overrides, p)
            for p, m in COMMAND_META.items()
        ):
            active.add(ep)
    return frozenset(active)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/command_permissions_endpoints_test.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/application/command_permissions.py tests/unit/command_permissions_endpoints_test.py
git commit -m "feat(perm): 采集派生（观测地板恒轮询 + GAME_DATA 派生）"
```

---

## Task 4: config 解析 command_permissions 行（保留 legacy 字段）

**Files:**
- Modify: `palworld_terminal/config.py`（`PermissionsConfig` L156-166、`_parse_permissions` L314-344、`_default_permissions`、顶部 import）
- Test: `tests/unit/config_command_permissions_test.py`

**Interfaces:**
- Consumes: `command_permissions.CommandOverride`/`COMMAND_META`/`enable_configurable`/`admin_configurable`/`admin_forced_true`；`command_registry.DISPATCH`
- Produces: `PermissionsConfig.command_overrides`、`.invalid_command_keys`。**保留** `admins`、`admin_only_commands`、`unknown_locks`（Task 8 才删——消费点 `_admin_locked`/`admin_denied`/`main.py:_log_startup_warnings` 尚未切换）。

> 本任务只解析新 `command_permissions` 行 → command_overrides；**不含 legacy 迁移**（迁移在 Task 5 装载期做）。此处若 raw 无 `command_permissions`，command_overrides 为空（合法，Task 5 装载迁移会先把 legacy 转成行写回，故运行时 parse 恒见新键）。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/config_command_permissions_test.py
from palworld_terminal.config import parse_config
from palworld_terminal.application.command_permissions import (
    effective_enabled as ee, effective_admin_only as eao,
)

def _cfg(raw):
    return parse_config(raw, {})

def _row(cmd, enabled="inherit", admin_only="inherit"):
    return {"command": cmd, "enabled": enabled, "admin_only": admin_only}

def test_rows_parsed_to_overrides():
    cfg = _cfg({"command_permissions": [
        _row("guild", enabled="on"),
        _row("world today", enabled="off"),
        _row("guild list", admin_only="on"),
    ]})
    ov = cfg.permissions.command_overrides
    assert ee(ov, "guild info") is True
    assert ee(ov, "world today") is False
    assert eao(ov, "guild list") is True

def test_tristate_inherit_is_none():
    cfg = _cfg({"command_permissions": [_row("guild", enabled="inherit", admin_only="inherit")]})
    # 两轴 inherit → 无有效覆盖（可为空或该键两字段皆 None）
    ov = cfg.permissions.command_overrides
    assert ee(ov, "guild list") is False        # 走默认

def test_invalid_command_and_axis_logged():
    cfg = _cfg({"command_permissions": [
        _row("nonsense", enabled="on"),           # 未知命令
        _row("world status", enabled="off"),       # core 不可配 enable
        _row("link list", admin_only="on"),        # 不可配 admin
        _row("server kick", admin_only="off"),     # 恒真轴
    ]})
    ov = cfg.permissions.command_overrides
    inv = cfg.permissions.invalid_command_keys
    assert "nonsense" in inv
    assert any("world status" in x for x in inv)   # 轴违规也登记（F3）
    assert any("link list" in x for x in inv)
    assert ee(ov, "world status") is True
    assert eao(ov, "link list") is False
    assert eao(ov, "server kick") is True

def test_legacy_fields_still_present():
    # Task 8 前保留旧字段供未切换消费点
    cfg = _cfg({"admin_only_commands": ["guild list"]})
    assert cfg.permissions.admin_only_commands == ["guild list"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/config_command_permissions_test.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

config.py 顶部（`from .domain.enums import AccessMode` 附近）新增：

```python
from .application.command_permissions import CommandOverride
```

`PermissionsConfig`（L156-166）改为（**保留旧字段**）：

```python
@dataclass(slots=True)
class PermissionsConfig:
    admins: list[AdminEntry]
    command_overrides: dict[str, CommandOverride]
    invalid_command_keys: list[str] = field(default_factory=list)
    admin_only_commands: list[str] = field(default_factory=list)   # legacy，Task 8 删
    unknown_locks: list[str] = field(default_factory=list)          # legacy，Task 8 删


def _default_permissions() -> PermissionsConfig:
    return PermissionsConfig(admins=[], command_overrides={})
```

`_parse_permissions`（L314-344）改为（解析 admins + 新行 + 保留旧字段解析）：

```python
_TRISTATE = {"inherit": None, "on": True, "off": False}


def _parse_permissions(raw: Mapping) -> PermissionsConfig:
    admins: list[AdminEntry] = []
    seen: set[str] = set()
    for item in raw.get("permission_admins", []) or []:
        if not isinstance(item, Mapping):
            continue
        pid = str(item.get("id", "") or "").strip()
        if not pid or pid.endswith(":") or pid in seen:
            continue
        seen.add(pid)
        admins.append(AdminEntry(id=pid, note=str(item.get("note", "") or "").strip()))

    from .application.command_permissions import (
        COMMAND_META, admin_configurable, admin_forced_true, enable_configurable,
    )
    from .presentation.command_registry import DISPATCH, LOCKABLE_COMMANDS

    valid_group_keys = set(DISPATCH.keys())
    overrides: dict[str, dict] = {}
    invalid: list[str] = []

    for row in raw.get("command_permissions", []) or []:
        if not isinstance(row, Mapping):
            continue
        cmd = str(row.get("command", "") or "").strip()
        if not cmd:
            continue
        is_group = cmd in valid_group_keys
        is_path = cmd in COMMAND_META
        if not is_group and not is_path:
            invalid.append(cmd)
            continue
        en = _TRISTATE.get(str(row.get("enabled", "inherit")), None)
        ao = _TRISTATE.get(str(row.get("admin_only", "inherit")), None)
        rec = overrides.setdefault(cmd, {})
        if en is not None:
            if is_group or enable_configurable(cmd):
                rec["enabled"] = en
            else:
                invalid.append(f"{cmd}:enabled")     # 轴违规登记（F3）
        if ao is not None:
            if is_group or (admin_configurable(cmd) and not admin_forced_true(cmd)):
                rec["admin_only"] = ao
            else:
                invalid.append(f"{cmd}:admin_only")   # 轴违规登记（F3）

    frozen = {
        k: CommandOverride(enabled=v.get("enabled"), admin_only=v.get("admin_only"))
        for k, v in overrides.items() if v
    }

    # legacy 字段照旧解析（Task 8 前消费点仍读）——沿用现逻辑。
    raw_cmds = raw.get("admin_only_commands", [])
    legacy_cmds: list[str] = []
    legacy_unknown: list[str] = []
    if isinstance(raw_cmds, list):
        from .presentation.command_registry import _NON_LOCKABLE
        cseen: set[str] = set()
        for c in raw_cmds:
            if not isinstance(c, str):
                continue
            name = c.strip()
            if not name or name in _NON_LOCKABLE or name in cseen:
                continue
            cseen.add(name)
            legacy_cmds.append(name)
            if name not in LOCKABLE_COMMANDS:
                legacy_unknown.append(name)

    return PermissionsConfig(
        admins=admins, command_overrides=frozen, invalid_command_keys=invalid,
        admin_only_commands=legacy_cmds, unknown_locks=legacy_unknown,
    )
```

- [ ] **Step 4: 跑测试通过 + 全库回归（门控仍读 features/admin_only_commands，应仍绿）**

Run: `pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: PASS（若 `config_permissions_test`/`config_admin_only_warn_test` 断言旧字段仍在——它们**仍在**，应绿；如引用 `command_overrides` 需补则补）

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/config.py tests/unit/config_command_permissions_test.py
git commit -m "feat(perm): 解析 command_permissions 三态行 → command_overrides（保留 legacy 字段）"
```

---

## Task 5: 装载时迁移 legacy → 行并落库（复核 F1/B2 根治）

**Files:**
- Modify: `palworld_terminal/application/command_permissions.py`（`migrate_legacy_to_rows`）
- Modify: `palworld_terminal/main.py`（插件装载 early，parse/container 之前，调用迁移 + `astrbot_config.save()`）
- Test: `tests/unit/command_permissions_migrate_test.py`、`tests/unit/main_migration_test.py`

**Interfaces:**
- Consumes: `command_registry.LOCKABLE_COMMANDS`
- Produces: `migrate_legacy_to_rows(raw) -> tuple[list[dict], list[str]]`（行列表 + 非法锁键）；main.py 装载迁移使 storage 含 command_permissions、旧键清除

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/command_permissions_migrate_test.py
from palworld_terminal.application.command_permissions import migrate_legacy_to_rows

def _rows_map(rows):
    return {r["command"]: r for r in rows}

def test_migrate_features():
    rows, inv = migrate_legacy_to_rows({"features": {
        "guilds_bases": True, "players": True, "report": False}})
    m = _rows_map(rows)
    assert m["guild"]["enabled"] == "on"
    assert m["player"]["enabled"] == "on"
    assert m["rank"]["enabled"] == "on" and m["me"]["enabled"] == "on"
    assert m["world today"]["enabled"] == "off"
    assert "world events" not in m          # 默认未变不产行

def test_migrate_server_admin_leaves():
    rows, _ = migrate_legacy_to_rows({"features": {
        "server_admin_basic": True, "server_admin_danger": True}})
    m = _rows_map(rows)
    for p in ("server announce", "server save", "server kick", "server unban",
              "server ban", "server shutdown", "server stop"):
        assert m[p]["enabled"] == "on"

def test_migrate_admin_only_commands():
    rows, inv = migrate_legacy_to_rows({"admin_only_commands": ["guild list", "server kick"]})
    m = _rows_map(rows)
    assert m["guild list"]["admin_only"] == "on"
    assert "server kick" in inv             # 非 LOCKABLE

def test_merge_enable_and_admin_same_command():
    rows, _ = migrate_legacy_to_rows({
        "features": {"players": True}, "admin_only_commands": ["rank"]})
    m = _rows_map(rows)
    assert m["rank"]["enabled"] == "on" and m["rank"]["admin_only"] == "on"
```

```python
# tests/unit/main_migration_test.py —— 装载迁移落库 + 往返不丢锁（F1/B2 关键）
def test_load_migration_persists_and_no_lock_loss(fake_astrbot_config):
    cfg = fake_astrbot_config({"admin_only_commands": ["guild list"], "features": {"guilds_bases": True}})
    _run_plugin_load(cfg)                    # 触发装载迁移
    assert "command_permissions" in cfg.data
    assert "admin_only_commands" not in cfg.data and "features" not in cfg.data
    assert cfg.saved is True
    # GET 读路径（redact_config(cfg.data)）现含 command_permissions → 保存不丢锁
    from palworld_terminal.config import parse_config
    from palworld_terminal.application.command_permissions import effective_admin_only
    ov = parse_config(cfg.data, {}).permissions.command_overrides
    assert effective_admin_only(ov, "guild list") is True

def test_load_migration_idempotent(fake_astrbot_config):
    cfg = fake_astrbot_config({"command_permissions": []})   # 新键在场 → 跳过
    _run_plugin_load(cfg)
    assert cfg.saved is False
```

（`fake_astrbot_config`/`_run_plugin_load`：最小替身，`cfg.data` 是 dict、`cfg.save()` 置 `cfg.saved=True`；`_run_plugin_load` 调用 main.py 抽出的迁移入口函数。）

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/command_permissions_migrate_test.py tests/unit/main_migration_test.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`command_permissions.py` 追加：

```python
# feature 布尔 -> (默认, 命令键列表)。旧值 != 默认才产 enable 行。
_FEATURE_MIGRATION: dict[str, tuple[bool, tuple[str, ...]]] = {
    "report": (True, ("world today",)),
    "events": (True, ("world events",)),
    "guilds_bases": (False, ("guild",)),
    "players": (False, ("player", "rank", "me")),
    "server_admin_basic": (False, ("server announce", "server save",
                                   "server kick", "server unban")),
    "server_admin_danger": (False, ("server ban", "server shutdown", "server stop")),
}


def migrate_legacy_to_rows(raw: Mapping) -> tuple[list[dict], list[str]]:
    """旧 features + admin_only_commands → command_permissions 三态行 + 非法锁键。"""
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

    rows = [
        {"command": cmd,
         "enabled": v.get("enabled", "inherit"),
         "admin_only": v.get("admin_only", "inherit")}
        for cmd, v in acc.items()
    ]
    return rows, invalid
```

`main.py`：抽出装载迁移入口（在读取 config、build container 之前调用一次）：

```python
def _migrate_permissions_config(config) -> None:
    """装载时一次性迁移 legacy 权限配置并落库（复核 F1/B2）。幂等。"""
    from .application.command_permissions import migrate_legacy_to_rows
    data = config  # AstrBotConfig 是 dict-like
    if "command_permissions" in data:
        return
    if "features" not in data and "admin_only_commands" not in data:
        return
    rows, _invalid = migrate_legacy_to_rows(data)
    data["command_permissions"] = rows
    data.pop("features", None)
    data.pop("admin_only_commands", None)
    config.save()
```

在插件 `__init__`/装载序列中，`parse_config` 与 container 构建**之前**调用
`self._migrate_permissions_config(self.config)`（具体钩子按 main.py 现有装载点接入；
若装载点已 await 配置，放在首次 `_apply` 前）。

- [ ] **Step 4: 跑测试通过 + 全库**

Run: `pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/application/command_permissions.py palworld_terminal/main.py tests/unit/command_permissions_migrate_test.py tests/unit/main_migration_test.py
git commit -m "feat(perm): 装载时迁移 legacy 权限配置并落库（根治读路径失锁 F1/B2）"
```

---

## Task 6: container 采集接线 + 服务装配门迁移（复核 B1/B3）

**Files:**
- Modify: `palworld_terminal/container.py`（L17 import、L117-121 服务门、L154 active_endpoints）
- Test: `tests/integration/feature_groups_off_test.py`、`tests/unit/container_features_test.py`

**Interfaces:**
- Consumes: `command_permissions.active_endpoints`/`effective_enabled`；`domain.enums.EndpointName`；`PermissionsConfig.command_overrides`
- Produces: container 端点集 + EventService/GuildService/BaseService 实例化均由 overrides 驱动

- [ ] **Step 1: 改测试（先失败）**

把两个测试构造 `features=` 的替身改为构造 `permissions.command_overrides=`，断言：
- `command_overrides={}` → active_endpoints 不含 GAME_DATA；EventService=None（events 默认关？注意 events 默认**开**，故 `{}` 下 EventService 应**非 None**）、GuildService/BaseService=None。
- `command_overrides={"guild": CO(enabled=True)}` → 含 GAME_DATA、GuildService/BaseService 非 None。
- `command_overrides={"world events": CO(enabled=False)}` → EventService=None。

```python
from palworld_terminal.application.command_permissions import CommandOverride as CO
# events 默认开 → EventService 默认在
c0 = build_container(command_overrides={})
assert c0.events_service is not None
assert c0.guild_service is None and c0.base_service is None
c1 = build_container(command_overrides={"guild": CO(enabled=True), "world events": CO(enabled=False)})
assert c1.events_service is None
assert c1.guild_service is not None and c1.base_service is not None
```

（按 container 实际结构取服务引用；若服务未暴露，测 active_endpoints + 断构造分支覆盖。）

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/integration/feature_groups_off_test.py tests/unit/container_features_test.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

container.py L17：

```python
from .application.command_permissions import active_endpoints, effective_enabled
from .domain.enums import EndpointName        # 若未 import
```

L117-121 服务门（`self._cfg.features.X` → 生效值；语义等价保留「门关注 None」）：

```python
        ov = self._cfg.permissions.command_overrides
        events = EventService(...) if effective_enabled(ov, "world events") else None
        _game_data_on = EndpointName.GAME_DATA in active_endpoints(ov)
        guilds = GuildService(...) if _game_data_on else None
        bases  = BaseService(...)  if _game_data_on else None
```

L154：

```python
            endpoints=active_endpoints(self._cfg.permissions.command_overrides),
```

> 实现注意：核对 `events`/`guilds`/`bases` 作为依赖被注入下游（如 players/guilds 服务）的耦合——现状 `features` 关时即注 None，改后语义一致（生效值关 → None），下游容忍不变。若 `ov` 局部变量与既有命名冲突，另取名。

- [ ] **Step 4: 跑测试通过 + 全库**

Run: `pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/container.py tests/integration/feature_groups_off_test.py tests/unit/container_features_test.py
git commit -m "feat(perm): container 采集端点 + 服务装配门改由生效值驱动（B1/B3）"
```

---

## Task 7: 门控落点全切换生效值（原子）

**Files:**
- Modify: `command_registry.py`（`METHOD_PATH`）
- Modify: `commands.py`（`_gated` L68-78、`_dispatch_read` L337/340、`admin_write` L453、`confirm` L571、`link` L389、`_admin_locked` L294-296、`admin_denied` L623-626、`_group_help` L306、`help` L435、import 行去 `COMMAND_GROUP`）
- Modify: `formatters.py`（`_action_visible` L141-152、`visible_actions` L155-170、`format_help` L178 + 扁平循环 L186-187）
- Modify: `main.py`（`_log_startup_warnings` L117 `unknown_locks` → `invalid_command_keys`）
- Test: `commands_gating_test.py`、`commands_dispatch_test.py`、`commands_admin_write_test.py`、`formatters_test.py`、`formatters_hierarchy_test.py`、`formatters_admin_help_test.py`、`main_permission_gate_test.py`、新增 `test_gated_methods_in_method_path`

**Interfaces:**
- Consumes: `command_permissions.effective_enabled`/`effective_admin_only`；`command_registry.METHOD_PATH`
- Produces: 所有门控读生效值；`METHOD_PATH: dict[str,str]`（read 方法名→完整路径）

> 高内聚**必须原子**（半切留双语义）。统一规则：`features.enabled(组)` → `effective_enabled(cfg.permissions.command_overrides, 完整路径)`；`... in admin_only_commands` → `effective_admin_only(...)`。

- [ ] **Step 1: 写/改测试（先失败）**

```python
# tests/unit/commands_gating_test.py 追加
import pytest
from palworld_terminal.application.command_permissions import CommandOverride as CO

@pytest.mark.asyncio
async def test_group_disable_blocks_leaf(make_commands):
    cmds = make_commands(command_overrides={"guild": CO(enabled=False)})
    out = await cmds.guild_grp("umo", "list", True, "u1", False)
    assert out == "..."   # L("feature_disabled") 实际文案

@pytest.mark.asyncio
async def test_leaf_admin_lock_denies_guest(make_commands):
    cmds = make_commands(command_overrides={"guild": CO(enabled=True), "guild list": CO(admin_only=True)})
    out = await cmds.guild_grp("umo", "list", True, "guest", False)
    assert "管理员" in out

# tests/unit/command_permissions_meta_test.py 追加（METHOD_PATH 覆盖，防 KeyError）
def test_all_gated_methods_in_method_path():
    from palworld_terminal.presentation.command_registry import METHOD_PATH
    gated = {"guilds", "guild", "bases", "base", "events", "today",
             "rank", "player", "bind", "me", "unbind_self"}   # 现 @_gated 方法名
    assert gated <= set(METHOD_PATH)
```

（`make_commands` fixture 由构造 `features=` 改为构造 `permissions.command_overrides=`；同步 `commands_dispatch_test`/`commands_admin_write_test` 替身。）

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/commands_gating_test.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`command_registry.py` 追加（`FLAT_ACTIONS` 之后）：

```python
# 读方法名 → 完整路径（供 commands._gated）。仅收 gate==read 方法（写走 admin_write）。
METHOD_PATH: dict[str, str] = {
    method: f"{grp} {sub}"
    for grp, actions in DISPATCH.items()
    for sub, (method, _feat, gate) in actions.items()
    if gate == "read"
}
METHOD_PATH.update({
    name: name for name, (_m, _f, gate) in FLAT_ACTIONS.items() if gate == "read"
})
```

`commands.py` 顶部 import：`from ..application.command_permissions import effective_admin_only, effective_enabled` + `from .command_registry import METHOD_PATH`；**去掉** 现 import 里的 `COMMAND_GROUP`（避免 ruff F401）。

`_gated`（L68-78）：

```python
def _gated(fn):
    @functools.wraps(fn)
    async def wrapper(self, *args, **kwargs):
        path = METHOD_PATH[fn.__name__]
        if not effective_enabled(self._cfg.permissions.command_overrides, path):
            return L("feature_disabled")
        return await fn(self, *args, **kwargs)
    return wrapper
```

`_dispatch_read` L337：`if not effective_enabled(self._cfg.permissions.command_overrides, f"{group} {p.sub}"):`

`_admin_locked`（L294-296）：

```python
    def _admin_locked(self, path: str, sender_id: str, is_admin: bool) -> bool:
        return effective_admin_only(self._cfg.permissions.command_overrides, path) and not is_admin
```

`admin_write` L453：`if not effective_enabled(self._cfg.permissions.command_overrides, f"server {command_str}"):`

`confirm` L571：`if not effective_enabled(self._cfg.permissions.command_overrides, f"server {p.command_str}"):`

`link` L389：`if not effective_enabled(self._cfg.permissions.command_overrides, f"link {p.sub}"):`

`admin_denied`（L623-626）：

```python
    def admin_denied(self, command_str: str, sender_id: str) -> str | None:
        if effective_admin_only(self._cfg.permissions.command_overrides, command_str) \
                and not self.is_plugin_admin(sender_id):
            return L("admin_required")
        return None
```

`_group_help` L306：`visible_actions(group, is_admin, self._cfg.permissions.command_overrides, self._world_mode())`

`help` L435（**复核 M1 落点**）：把 `format_help(topic, is_admin, self._cfg.features, self._world_mode())` 改为 `format_help(topic, is_admin, self._cfg.permissions.command_overrides, self._world_mode())`。

`formatters.py`：

```python
def _action_visible(path: str, spec: ActionSpec, is_admin: bool, overrides) -> bool:
    from ..application.command_permissions import effective_enabled
    _method, _feat_group, gate = spec
    if not effective_enabled(overrides, path):
        return False
    if gate in ("admin_write", "admin"):
        return is_admin
    return True


def visible_actions(group, is_admin, overrides, world_mode="multi"):
    if group == "link" and world_mode == "single":
        return []
    return [
        (sub, spec)
        for sub, spec in DISPATCH.get(group, {}).items()
        if _action_visible(f"{group} {sub}", spec, is_admin, overrides)
    ]
```

`format_help`（L178）签名 `features` → `overrides`；其**扁平动作循环**（L186-187）调用改为
`_action_visible(name, spec, is_admin, overrides)`（传 name + overrides，参数个数变）。

`main.py` `_log_startup_warnings` L117：`c.config.permissions.unknown_locks` → `c.config.permissions.invalid_command_keys`（文案「未知锁条目」→「非法命令权限配置项」）。

`grep -rn "self._cfg.features\|\.features\b\|admin_only_commands" palworld_terminal/presentation palworld_terminal/main.py` 确认门控读零残留（`config.py`/legacy 字段定义除外）。

- [ ] **Step 4: 跑测试通过 + 全库回归**

Run: `pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: PASS（formatters/commands/main 测试替身改 `command_overrides=` 作为本任务一部分修）

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/presentation/command_registry.py palworld_terminal/presentation/commands.py palworld_terminal/presentation/formatters.py palworld_terminal/main.py tests/
git commit -m "feat(perm): 门控/可见性全落点改查命令生效值（含 help 落点 + 启动告警重指）"
```

---

## Task 8: 删除 FeaturesConfig / feature_groups / COMMANDS / legacy 字段

**Files:**
- Delete: `palworld_terminal/application/feature_groups.py`
- Modify: `config.py`（删 `FeaturesConfig`/`_default_features`/`AppConfig.features`/`parse_config` 内 features 构造；删 `PermissionsConfig.admin_only_commands`/`unknown_locks` 字段 + `_parse_permissions` 的 legacy 解析块）
- Modify: `command_registry.py`（删 `COMMANDS` L5-19、`COMMAND_GROUP` L20）
- Test: 删/改 `config_features_test.py`、`config_server_admin_test.py`（features.enabled 断言）、`config_admin_only_warn_test.py`（unknown_locks）

**Interfaces:**
- Consumes: 无（清理）
- Produces: `AppConfig` 无 `features`；`PermissionsConfig` 无 legacy 字段；`command_registry` 无 COMMANDS/COMMAND_GROUP

- [ ] **Step 1: 零引用门禁 grep**

Run: `grep -rn "FeaturesConfig\|\.features\b\|COMMAND_GROUP\|feature_groups\|admin_only_commands\|unknown_locks" palworld_terminal/`
Expected: 仅剩本任务将删的**定义处**（config.py 的 FeaturesConfig/legacy 字段、command_registry COMMANDS/COMMAND_GROUP、feature_groups.py），**无消费点**（Task 6/7 已切光 container/commands/formatters/main）

- [ ] **Step 2: 删除 + 改测试（先红后绿）**

删除上列定义 + legacy 解析块；删/改引用它们的测试。

- [ ] **Step 3: 全库回归**

Run: `pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "refactor(perm): 删除 FeaturesConfig/feature_groups/COMMANDS/legacy 权限字段"
```

---

## Task 9: _conf_schema + config_view 往返（template_list + 清死码）

**Files:**
- Modify: `_conf_schema.json`（删 features/admin_only_commands；加 command_permissions template_list）
- Modify: `config_view.py`（`_LIST_SECTIONS`/`_SECTION_KEYS`/`_ROW_ID_PREFIX`/`_TOP_KEYS`；command_permissions 行校验；删 features 死循环 + admin_only_commands 死校验块）
- Test: `config_view_validate_test.py`、`conf_schema_test.py`

**Interfaces:**
- Consumes: `command_permissions.COMMAND_META`；`command_registry.DISPATCH`
- Produces: config_view 接受/校验 command_permissions 行；往返闭合

- [ ] **Step 1: 写失败测试**

```python
# config_view_validate_test.py 追加
def test_command_permissions_row_shape_ok():
    body = {"command_permissions": [
        {"command": "guild", "enabled": "on", "admin_only": "inherit"},
        {"command": "guild list", "enabled": "inherit", "admin_only": "on"},
    ]}
    assert validate_body(body) is None

def test_command_permissions_row_rejects_bad():
    assert validate_body({"command_permissions": [{"command": "guild", "enabled": "yes"}]}) is not None
    assert validate_body({"command_permissions": [{"command": "nope"}]}) is not None
    assert validate_body({"command_permissions": {"not": "list"}}) is not None

def test_top_keys_dropped_legacy():
    assert validate_body({"features": {"report": True}}) is not None
    assert validate_body({"admin_only_commands": ["x"]}) is not None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/config_view_validate_test.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

config_view.py：
- `_LIST_SECTIONS` 加 `"command_permissions"`；`_ROW_ID_PREFIX` 加 `"command_permissions": "cmd"`；`_SECTION_KEYS` 加 `"command_permissions": {"command", "enabled", "admin_only"}`。
- `_TOP_KEYS`：删 `"features"`、`"admin_only_commands"`，加 `"command_permissions"`。
- 新增 command_permissions 行校验（在列表节校验流程中，或独立块）：每行 `command` ∈ `set(COMMAND_META)∪set(DISPATCH)`，`enabled`/`admin_only` ∈ {"inherit","on","off"}；否则 `_err`。
- **删死码**：object 形状循环（L155-158）里的 `"features"`；独立 `admin_only_commands` 校验块（L174-181）。

`_conf_schema.json`：删 features（6 bool）+ admin_only_commands 项；加 command_permissions（template_list，行模板 command:string / enabled:string / admin_only:string，描述含三态取值 + 指向插件设置页）。

同步 `conf_schema_test.py`：`test_features_section`（删）、`test_permission_schema_present`（改断 command_permissions）、`test_server_admin_schema_present`（**改：不再经 `features.items.server_admin_basic` 读**，直接断顶层 server_admin 项）、`test_admin_only_commands_hint_examples_are_lockable`（删或改为 command_permissions 描述锚定）。

- [ ] **Step 4: 全库**

Run: `pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add _conf_schema.json palworld_terminal/presentation/config_view.py tests/unit/config_view_validate_test.py tests/unit/conf_schema_test.py
git commit -m "feat(perm): _conf_schema + config_view 往返承载 command_permissions（template_list）"
```

---

## Task 10: 前端命令树描述 PAL_TREE + 跨端锚定

**Files:**
- Modify: `frontend/src/lib/schema.ts`（`PAL_COMMANDS` L98-107 → `PAL_TREE`，JSON 可解析）
- Test: `tests/unit/frontend_pal_commands_test.py`

**Interfaces:**
- Consumes: 后端 `command_permissions` 派生元数据（锚定源）
- Produces: `PAL_TREE`（完整命令树 + configurable 标志）

- [ ] **Step 1: 写失败锚定测试**

```python
# tests/unit/frontend_pal_commands_test.py 升级
# PAL_TREE 落成 JSON 可解析（如 `export const PAL_TREE = [...] as const`，值为纯 JSON），
# 测试用 json.loads 提取（避免正则啃嵌套 TS 对象）。
def test_frontend_tree_matches_backend_meta():
    tree = _load_pal_tree_json()   # 从 schema.ts 抽出 PAL_TREE 数组并 json.loads
    from palworld_terminal.application.command_permissions import (
        COMMAND_META, enable_configurable, admin_configurable, admin_forced_true, DANGER_COMMANDS,
    )
    assert {n["path"] for n in tree} == set(COMMAND_META)
    for n in tree:
        p = n["path"]
        assert n["enableConfigurable"] == enable_configurable(p)
        assert n["adminConfigurable"] == admin_configurable(p)
        assert n["adminForced"] == admin_forced_true(p)
        assert n["danger"] == (p in DANGER_COMMANDS)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/frontend_pal_commands_test.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`schema.ts`：`PAL_TREE` 取代 `PAL_COMMANDS`，每项 `{group, path, label, enableConfigurable, adminConfigurable, adminForced, danger}`，落成 JSON 数组字面量（便于 Python `json.loads`）。按组 + 扁平「其他」组织。内容与后端派生全等（锚定守）。

- [ ] **Step 4: 测试通过 + 前端构建**

Run: `pytest tests/unit/frontend_pal_commands_test.py -q`（**本任务不跑 `npm run build`**，避免重生成 pages/settings 产生未提交脏态；bundle 统一在 Task 11 构建+提交）
Expected: PASS

- [ ] **Step 5: 提交（仅源码，不含 bundle）**

```bash
git add frontend/src/lib/schema.ts tests/unit/frontend_pal_commands_test.py
git commit -m "feat(perm/fe): PAL_TREE 命令树描述（JSON 可解析）跨端锚定后端派生"
```

---

## Task 11: 前端权限章命令树 UI + collectBody

**Files:**
- Modify: `frontend/src/lib/chapters.ts`（删 feature 章）
- Modify: `frontend/src/components/SettingsPanel.vue`（权限章命令树 + collectBody 行回写）
- Build: `frontend`（`npm run build` 生成 `pages/settings` bundle，本任务统一提交）
- Test: `frontend/src/**/*.spec.ts`

**Interfaces:**
- Consumes: Task 10 `PAL_TREE`
- Produces: 权限章命令树 UI；`collectBody` 输出 `command_permissions` 三态行

- [ ] **Step 1: 写失败前端测试**

```ts
it('collectBody emits sparse command_permissions rows', () => {
  const state = makeTreeState({ 'guild': { enabled: 'on' }, 'world today': { enabled: 'off' } })
  expect(collectBody(state).command_permissions).toEqual([
    { command: 'guild', enabled: 'on', admin_only: 'inherit' },
    { command: 'world today', enabled: 'off', admin_only: 'inherit' },
  ])
})
it('group enable toggle excludes danger leaves', () => {
  // server 组头「整组启用」不写 ban/shutdown/stop（复核 F2）
})
it('non-configurable cells locked', () => {
  // world status enable 单元格 disabled；server kick admin_only 恒 on 锁定
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm test`
Expected: FAIL

- [ ] **Step 3: 实现**

- `chapters.ts` 删 `feature` 章。
- `SettingsPanel.vue` 权限章：AdminCard（permission_admins，不变）+ 命令树表：按组折叠、组头「整组启用/整组仅管理员」批量开关（**整组启用排除 danger 叶子**，F2）、叶子行两列三态开关、不可配格锁定置灰显恒定值、danger 行标记、继承 vs 覆盖视觉区分。
- `collectBody`：命令树 state → 稀疏 `command_permissions` 三态行（两轴 inherit 的行省略）。
- 树 UI 视觉可用 artifact-design 协作定稿（沿用 Phase 1 观测台视觉系统）。

- [ ] **Step 4: 测试 + 构建 + no-drift**

Run: `cd frontend && npm test && npm run build`；回根 `git status --porcelain pages/settings`
Expected: PASS；bundle LF 无幻影（`npm run build` 内置 normalize-eol）

- [ ] **Step 5: 提交（源码 + bundle）**

```bash
git add frontend/ pages/settings/
git commit -m "feat(perm/fe): 权限章命令树 UI + collectBody 三态行回写"
```

---

## Task 12: 文档 + 版本 + 迁移对照

**Files:**
- Modify: `README.md`（权限/功能表述→命令树；旧→新迁移对照表）
- Modify: `metadata.yaml`（version→v0.9.6）、`main.py` L83 `@register(...,"v0.9.6")`
- Modify: `tests/unit/readme_test.py`（点名断言同步）

**Interfaces:**
- Consumes: 全部前序行为
- Produces: 文档 + 版本两源一致

- [ ] **Step 1: 改版本两源 + README + 点名锚点测试**

- `metadata.yaml` version + `main.py` L83 register → v0.9.6（**仅这两处**）。
- README 更新权限章（命令树控制面）+ 加旧→新配置迁移对照表（features 布尔 / admin_only_commands → command_permissions 三态行）。
- **点名同步会断的 readme_test.py 断言**（决定「对照表保留旧词」或「改锚点」）：
  - `test_readme_documents_feature_groups`（功能开关/features/guilds_bases/默认关/game-data）
  - `test_readme_command_table_and_matrix`（core/report/events/guilds_bases/未开放/help 隐藏）
  - `test_readme_documents_permission_management`（admin_only_commands 须在迁移对照表出现）
  推荐：迁移对照表**保留旧词**（features/guilds_bases/admin_only_commands 作为「旧→新」左列），使锚点自然满足，同时新增命令树说明。README 资源引用保持绝对 URL。

- [ ] **Step 2: 全绿**

Run: `pytest -q && ruff check palworld_terminal && mypy palworld_terminal && (cd frontend && npm run build && npm test)`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "docs(perm): 命令树权限文档 + 迁移对照 + v0.9.6"
```

---

## Self-Review 结论

- **Spec 覆盖**：§1 模型→T1-2；§2 template_list 形状→T4/T9；§3 API→T1-3；§4 门控→T7；§5 装载迁移落库→T5；§6 采集派生 + container 服务门→T3/T6；§7 树 UI→T10-11；§8 schema/config_view→T9；§9 测试（含装载往返、container 门、danger、METHOD_PATH、独立 LOCKABLE 锚定）→散布；§10 版本两源 + 点名 readme 锚点→T12。全覆盖。
- **复核 Blocker 闭环**：B-读路径失锁→T5 装载迁移落库 + 往返测试；B-container 服务门→T6 L117-121 迁移 + grep 门禁修正（T8）；B-字段生命周期→legacy 字段存活到 T8、`_log_startup_warnings` 重指入 T7。
- **复核 Major 闭环**：M1 动态键→template_list（T4/T9）；M2 readme 锚点→T12 点名；M-help 落点→T7 显式含 `help` L435。
- **复核 Minor 闭环**：F2 danger 不继承（T2 + T11 组头排除）；F3 轴违规登记（T4）；循环 import 去兜底（Global Constraints 顶层安全）；版本两源（Global + T12）；conf_schema_test 四断言 + 死码（T9）；METHOD_PATH 覆盖测试（T7）；PAL_TREE JSON 可解析（T10）；T10 不构建避免脏态、bundle 统一 T11 提交。
- **类型一致**：`CommandOverride`、`command_overrides: dict[str,CommandOverride]`、`effective_*(overrides,path)`、`active_endpoints(overrides)`、`METHOD_PATH`、三态 {inherit,on,off} 贯穿一致。
- **原子性**：T7 门控切换一次完成 + 全库回归；legacy 字段 T4 保留、T8 删，窗口全绿。
