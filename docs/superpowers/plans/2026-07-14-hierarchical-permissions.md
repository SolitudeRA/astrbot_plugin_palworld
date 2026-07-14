# 分级感知权限（统一层级权限模型）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把权限/采集配置从「6 个功能组布尔 + 扁平锁列表」统一为「命令树节点承载 enabled + admin_only（稀疏覆盖 + 三级继承），采集派生自 enable」的单一控制面。

**Architecture:** 新增纯函数模块 `application/command_permissions.py` 作为生效值 + 派生元数据 + 采集派生的唯一真相源（元数据全部从现有 `command_registry` 派生，零手工数据）。config 层新增 `command_overrides` 并承载 legacy→新模型迁移。门控各落点（`_gated`/`_dispatch_read`/`admin_write`/`confirm`/`link`/`_admin_locked`/`admin_denied`/`_action_visible`）改查生效值。删除 `FeaturesConfig`/`feature_groups.py`/`COMMANDS`。前端权限章重做为命令树 UI。

**Tech Stack:** Python 3.10+（AstrBot 插件，dataclass slots）、pytest、ruff、mypy；前端 Vue 3 + TypeScript + Vitest。

## Global Constraints

- 版本四源默认 **v0.9.6**（`metadata.yaml`、`_conf_schema.json` 若含版本、`pyproject.toml`/`package.json` 等——沿用仓库现有版本源位置，与 Phase 1 v0.9.5 同位置）。
- 命令串真相源分家不变：`PAL_REGISTERED`(11 首词，注册锚定) vs `PAL_COMMAND_STRINGS`/`LOCKABLE_COMMANDS`/`_NON_LOCKABLE`（完整路径）。新派生元数据须交叉锚定到 `command_registry`，防漂移测试必须有。
- 门序铁律不变：写命令 `admin_write` 内 admin 硬门**先于** enable 门；写/绑定/confirm 的 admin_only 恒真、结构不可绕；裸组角色隔离复用 `visible_actions` 单一谓词（guest 不泄漏 kick/ban/stop）。
- 可见性语义不回归：锁定读命令仍「可见但执行拒」，不引入「锁读→不可见」。
- 脱敏红线不变：config_view 返回绝不含 password/value 明文；错误只含字段路径。
- 包内**禁绝对自导入前缀**（`no_absolute_self_import` 静态测试）——模块间用相对 import。
- 每个任务结束：全库 `pytest -q`、`ruff check`、`mypy palworld_terminal`、（触前端时）`npm run build` + `npm test` 全绿；`pages/settings` no-drift 不脏。
- 采集地板恒轮询：INFO/METRICS/PLAYERS/SETTINGS 四端点服务 web 状态页，绝不因命令 enable 关闭而停轮询；仅 GAME_DATA 派生。
- 中文文案锚点：改 README/设置页中文用词须先 `grep tests/unit/readme_test.py` 的中文锚点短语，同步更新。

---

## 文件结构

| 文件 | 责任 | 本期动作 |
|---|---|---|
| `palworld_terminal/application/command_permissions.py` | 生效值 API + 派生元数据 + 采集派生（唯一真相源，纯函数） | **新建** |
| `palworld_terminal/application/feature_groups.py` | 旧「端点→功能组」采集派生 | **删除**（被 command_permissions 取代） |
| `palworld_terminal/config.py` | 配置解析：`PermissionsConfig.command_overrides` + 迁移；删 `FeaturesConfig` | 改 |
| `palworld_terminal/presentation/command_registry.py` | 命令树真相源；删 `COMMANDS`/`COMMAND_GROUP` 双源 | 改 |
| `palworld_terminal/presentation/commands.py` | 门控落点改查生效值；`_gated` 按路径 | 改 |
| `palworld_terminal/presentation/formatters.py` | `visible_actions`/`_action_visible` 改吃 overrides | 改 |
| `palworld_terminal/container.py` | `active_endpoints` 接线改吃 overrides | 改 |
| `palworld_terminal/presentation/config_view.py` | `_TOP_KEYS` + `command_permissions` 形状校验 | 改 |
| `palworld_terminal/main.py` | `format_help`/`admin_denied` 调用改传 overrides | 改 |
| `_conf_schema.json` | 删 `features`/`admin_only_commands` 项；加 `command_permissions` | 改 |
| `frontend/src/lib/schema.ts` | `PAL_COMMANDS` 升级为完整命令树描述 | 改 |
| `frontend/src/lib/chapters.ts` | 删 `feature` 章 | 改 |
| `frontend/src/components/SettingsPanel.vue` | 权限章命令树 UI + collectBody | 改 |

**关键接口（贯穿全计划，各任务须一致）：**

```python
# command_permissions.py 对外签名
@dataclass(frozen=True, slots=True)
class CommandOverride:
    enabled: bool | None = None
    admin_only: bool | None = None

COMMAND_META: dict[str, CommandMeta]          # 完整路径/扁平名 -> 元数据
def enable_configurable(path: str) -> bool
def admin_configurable(path: str) -> bool
def admin_forced_true(path: str) -> bool
def default_enabled(path: str) -> bool
def group_of(path: str) -> str | None
def effective_enabled(overrides: Mapping[str, CommandOverride], path: str) -> bool
def effective_admin_only(overrides: Mapping[str, CommandOverride], path: str) -> bool
def active_endpoints(overrides: Mapping[str, CommandOverride]) -> frozenset[EndpointName]

# PermissionsConfig 新形状
@dataclass(slots=True)
class PermissionsConfig:
    admins: list[AdminEntry]
    command_overrides: dict[str, CommandOverride]      # 键=组名 or 完整路径/扁平名
    invalid_command_keys: list[str] = field(default_factory=list)
```

---

## Task 1: 派生元数据模块骨架 + 锚定

**Files:**
- Create: `palworld_terminal/application/command_permissions.py`
- Test: `tests/unit/command_permissions_meta_test.py`

**Interfaces:**
- Consumes: `command_registry.DISPATCH`、`FLAT_ACTIONS`、`_NON_LOCKABLE`、`LOCKABLE_COMMANDS`、`PAL_COMMAND_STRINGS`；`domain.enums.EndpointName`
- Produces: `CommandMeta`、`COMMAND_META`、`FEATURE_DEFAULTS`、`enable_configurable`、`admin_configurable`、`admin_forced_true`、`default_enabled`、`group_of`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/command_permissions_meta_test.py
from palworld_terminal.application import command_permissions as cp
from palworld_terminal.presentation.command_registry import (
    PAL_COMMAND_STRINGS, LOCKABLE_COMMANDS, _NON_LOCKABLE,
)

def test_meta_covers_exactly_all_command_strings():
    assert set(cp.COMMAND_META) == set(PAL_COMMAND_STRINGS)

def test_enable_configurable_is_non_core():
    assert cp.enable_configurable("world today") is True      # report
    assert cp.enable_configurable("guild list") is True       # guilds_bases
    assert cp.enable_configurable("world status") is False     # core
    assert cp.enable_configurable("online") is False           # core
    assert cp.enable_configurable("server ban") is True        # server_admin_danger

def test_admin_configurable_equals_lockable():
    for p in PAL_COMMAND_STRINGS:
        assert cp.admin_configurable(p) is (p in LOCKABLE_COMMANDS)

def test_admin_forced_true_for_writes_and_admin_gate():
    assert cp.admin_forced_true("server kick") is True
    assert cp.admin_forced_true("link add") is True
    assert cp.admin_forced_true("confirm") is True
    assert cp.admin_forced_true("world status") is False

def test_default_enabled_matches_feature_defaults():
    assert cp.default_enabled("world status") is True   # core
    assert cp.default_enabled("world today") is True     # report=True
    assert cp.default_enabled("world events") is True    # events=True
    assert cp.default_enabled("guild list") is False     # guilds_bases=False
    assert cp.default_enabled("player info") is False    # players=False
    assert cp.default_enabled("rank") is False           # players=False
    assert cp.default_enabled("server ban") is False     # danger=False

def test_group_of():
    assert cp.group_of("world today") == "world"
    assert cp.group_of("rank") is None                   # 扁平
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/command_permissions_meta_test.py -q`
Expected: FAIL（`ModuleNotFoundError` / 属性不存在）

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

# feature 默认（承接 config._default_features 语义，按 feat_group）。
FEATURE_DEFAULTS: dict[str, bool] = {
    "core": True,
    "report": True,
    "events": True,
    "guilds_bases": False,
    "players": False,
    "server_admin_basic": False,
    "server_admin_danger": False,
}


@dataclass(frozen=True, slots=True)
class CommandMeta:
    path: str
    group: str | None       # 组名；扁平命令为 None
    feat_group: str
    gate: str               # "read" | "admin_write" | "admin"


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
git commit -m "feat(perm): 命令节点派生元数据模块 + 注册表锚定"
```

---

## Task 2: 生效值（三级继承）+ CommandOverride

**Files:**
- Modify: `palworld_terminal/application/command_permissions.py`
- Test: `tests/unit/command_permissions_effective_test.py`

**Interfaces:**
- Consumes: Task 1 的 `enable_configurable`/`admin_forced_true`/`admin_configurable`/`default_enabled`/`group_of`
- Produces: `CommandOverride`、`effective_enabled(overrides, path)`、`effective_admin_only(overrides, path)`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/command_permissions_effective_test.py
from palworld_terminal.application.command_permissions import (
    CommandOverride as CO, effective_enabled as ee, effective_admin_only as eao,
)

def test_enable_default_when_no_override():
    assert ee({}, "world today") is True      # report 默认开
    assert ee({}, "guild list") is False       # guilds_bases 默认关

def test_enable_group_override():
    assert ee({"guild": CO(enabled=True)}, "guild list") is True

def test_enable_leaf_overrides_group():
    ov = {"guild": CO(enabled=True), "guild list": CO(enabled=False)}
    assert ee(ov, "guild list") is False
    assert ee(ov, "guild info") is True        # 未被叶子覆盖，随组

def test_enable_core_ignores_override():
    # core 不可配：即使写了 enabled=False 也恒开
    assert ee({"world status": CO(enabled=False)}, "world status") is True

def test_enable_flat_no_group_layer():
    assert ee({"rank": CO(enabled=True)}, "rank") is True

def test_admin_only_default_false():
    assert eao({}, "world today") is False

def test_admin_only_forced_true_for_writes():
    assert eao({}, "server kick") is True       # 恒真，不看覆盖
    assert eao({"server kick": CO(admin_only=False)}, "server kick") is True

def test_admin_only_fixed_open_ignores_override():
    # link list / help / whoami 属 _NON_LOCKABLE 且非 forced → 恒开放
    assert eao({"link list": CO(admin_only=True)}, "link list") is False
    assert eao({"help": CO(admin_only=True)}, "help") is False

def test_admin_only_group_and_leaf():
    assert eao({"guild": CO(admin_only=True)}, "guild list") is True
    ov = {"guild": CO(admin_only=True), "guild list": CO(admin_only=False)}
    assert eao(ov, "guild list") is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/command_permissions_effective_test.py -q`
Expected: FAIL（`ImportError: cannot import name 'CommandOverride'`）

- [ ] **Step 3: 实现（追加到 command_permissions.py）**

```python
@dataclass(frozen=True, slots=True)
class CommandOverride:
    enabled: bool | None = None
    admin_only: bool | None = None


def effective_enabled(overrides: Mapping[str, "CommandOverride"], path: str) -> bool:
    if not enable_configurable(path):
        return default_enabled(path)            # core 恒开；未知 path → False
    leaf = overrides.get(path)
    if leaf is not None and leaf.enabled is not None:
        return leaf.enabled
    grp = group_of(path)
    if grp is not None:
        g = overrides.get(grp)
        if g is not None and g.enabled is not None:
            return g.enabled
    return default_enabled(path)


def effective_admin_only(overrides: Mapping[str, "CommandOverride"], path: str) -> bool:
    if admin_forced_true(path):
        return True                             # 写/绑定/confirm 恒真
    if not admin_configurable(path):
        return False                            # link list/help/whoami 恒开放
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
git commit -m "feat(perm): 生效值三级继承（叶子??组??默认）+ 恒定轴"
```

---

## Task 3: 采集派生 `active_endpoints`

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
    # 关光一切可配命令，观测地板四端点仍在（web 仪表盘）
    ov = {g: CO(enabled=False) for g in ("world", "guild", "player", "server")}
    act = active_endpoints(ov)
    assert OBSERVATION_FLOOR <= act
    assert E.GAME_DATA not in act               # 无 guild 命令启用

def test_game_data_derived_from_guild_enable():
    assert E.GAME_DATA not in active_endpoints({})            # guilds_bases 默认关
    assert E.GAME_DATA in active_endpoints({"guild": CO(enabled=True)})

def test_game_data_leaf_enable_also_triggers():
    assert E.GAME_DATA in active_endpoints({"guild bases": CO(enabled=True)})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/command_permissions_endpoints_test.py -q`
Expected: FAIL（`ImportError: OBSERVATION_FLOOR`）

- [ ] **Step 3: 实现（追加到 command_permissions.py）**

```python
# 观测地板：web 状态页 + 核心读共用，恒轮询（spec §6 安全约束）。
OBSERVATION_FLOOR: frozenset[EndpointName] = frozenset({
    EndpointName.INFO,
    EndpointName.METRICS,
    EndpointName.PLAYERS,
    EndpointName.SETTINGS,
})

# 派生端点：非地板端点 -> 触发它的 feat_group。目前仅 GAME_DATA。
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
git commit -m "feat(perm): 采集派生自 enable（观测地板恒轮询 + GAME_DATA 派生）"
```

---

## Task 4: config 解析 + legacy 迁移

**Files:**
- Modify: `palworld_terminal/config.py`（`PermissionsConfig` L156-166、`_parse_permissions` L314-344、`_default_permissions` L165-166）
- Test: `tests/unit/config_command_permissions_test.py`

**Interfaces:**
- Consumes: Task 2 的 `CommandOverride`；`command_registry.LOCKABLE_COMMANDS`、`command_permissions.COMMAND_META`
- Produces: `PermissionsConfig.command_overrides: dict[str, CommandOverride]`、`.invalid_command_keys: list[str]`。**保留** `PermissionsConfig.admins`。**移除** `admin_only_commands`、`unknown_locks` 字段。

> 注：本任务后 `FeaturesConfig` 仍存在（门控尚未切换，Task 6 才切；Task 7 删）。`parse_config` 仍解析 `features`（供门控临时用）；`_parse_permissions` 额外产出 `command_overrides`。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/config_command_permissions_test.py
from palworld_terminal.config import parse_config
from palworld_terminal.application.command_permissions import (
    effective_enabled as ee, effective_admin_only as eao,
)

def _cfg(raw):
    return parse_config(raw, {})

def test_new_model_parsed_when_present():
    cfg = _cfg({"command_permissions": {
        "guild": {"enabled": True},
        "world today": {"enabled": False},
        "guild list": {"admin_only": True},
    }})
    ov = cfg.permissions.command_overrides
    assert ee(ov, "guild info") is True
    assert ee(ov, "world today") is False
    assert eao(ov, "guild list") is True

def test_invalid_keys_and_axes_logged_not_applied():
    cfg = _cfg({"command_permissions": {
        "nonsense path": {"enabled": True},        # 未知键
        "world status": {"enabled": False},         # core 不可配 enable
        "link list": {"admin_only": True},          # 不可配 admin
        "server kick": {"admin_only": False},       # 恒真轴，忽略
    }})
    ov = cfg.permissions.command_overrides
    assert "nonsense path" in cfg.permissions.invalid_command_keys
    assert ee(ov, "world status") is True           # 恒开，覆盖被忽略
    assert eao(ov, "link list") is False            # 恒开放
    assert eao(ov, "server kick") is True           # 恒真

def test_migrate_from_features():
    # 无 command_permissions → 迁移 features（偏离默认才写覆盖）
    cfg = _cfg({"features": {"guilds_bases": True, "players": True, "report": False}})
    ov = cfg.permissions.command_overrides
    assert ee(ov, "guild list") is True             # guilds_bases True
    assert ee(ov, "player info") is True            # players True
    assert ee(ov, "rank") is True and ee(ov, "me") is True
    assert ee(ov, "world today") is False           # report False
    assert ee(ov, "world events") is True           # events 默认 True 未迁

def test_migrate_admin_only_commands():
    cfg = _cfg({"admin_only_commands": ["guild list", "server kick"]})
    ov = cfg.permissions.command_overrides
    assert eao(ov, "guild list") is True            # LOCKABLE → 迁移
    assert "server kick" in cfg.permissions.invalid_command_keys  # 非 LOCKABLE

def test_command_permissions_present_skips_migration():
    # 新键在场（即使空）→ 不迁移 legacy
    cfg = _cfg({"command_permissions": {}, "features": {"guilds_bases": True}})
    ov = cfg.permissions.command_overrides
    assert ee(ov, "guild list") is False            # 未迁移，用默认
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/config_command_permissions_test.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

改 `PermissionsConfig`（config.py L156-166）：

```python
@dataclass(slots=True)
class PermissionsConfig:
    admins: list[AdminEntry]
    command_overrides: dict[str, "CommandOverride"]
    invalid_command_keys: list[str] = field(default_factory=list)


def _default_permissions() -> PermissionsConfig:
    return PermissionsConfig(admins=[], command_overrides={})
```

在 config.py 顶部（`from .domain.enums import AccessMode` 附近）新增：

```python
from .application.command_permissions import CommandOverride
```

> ⚠️ 循环 import 风险：`command_permissions` import `command_registry`（presentation），`config` import `command_permissions`。现状 `config` 已在 `_parse_permissions` **函数体内**相对 import `command_registry`（L331）避免顶层环。若顶层 import `command_permissions` 触发环，改为函数体内 import（与既有模式一致）。实现时先试顶层，`pytest` 或 `ruff` 报环则下沉到函数体内。

替换 `_parse_permissions`（L314-344）为解析新模型 + 迁移：

```python
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
        group_of,
    )
    from .presentation.command_registry import DISPATCH

    valid_group_keys = set(DISPATCH.keys())
    overrides: dict[str, dict] = {}     # 先可变 dict 累积，末尾冻结为 CommandOverride
    invalid: list[str] = []

    def _set(key: str, field_name: str, value: bool) -> None:
        overrides.setdefault(key, {})[field_name] = value

    if "command_permissions" in raw:
        # 新模型在场：解析它，不迁移 legacy。
        cp_raw = raw.get("command_permissions") or {}
        if isinstance(cp_raw, Mapping):
            for key, body in cp_raw.items():
                key = str(key)
                is_group = key in valid_group_keys
                is_path = key in COMMAND_META
                if not is_group and not is_path:
                    invalid.append(key)
                    continue
                if not isinstance(body, Mapping):
                    continue
                if "enabled" in body and isinstance(body["enabled"], bool):
                    # 组键：只要组内有可配命令即接受；叶子：该叶子须可配
                    if is_group or enable_configurable(key):
                        _set(key, "enabled", body["enabled"])
                if "admin_only" in body and isinstance(body["admin_only"], bool):
                    if is_group:
                        _set(key, "admin_only", body["admin_only"])
                    elif admin_configurable(key) and not admin_forced_true(key):
                        _set(key, "admin_only", body["admin_only"])
    else:
        # 迁移 legacy：features(6 bool) + admin_only_commands(平铺路径)。
        _migrate_legacy(raw, _set, invalid)

    from .application.command_permissions import CommandOverride
    frozen = {
        k: CommandOverride(enabled=v.get("enabled"), admin_only=v.get("admin_only"))
        for k, v in overrides.items()
    }
    return PermissionsConfig(admins=admins, command_overrides=frozen, invalid_command_keys=invalid)
```

新增迁移辅助（config.py，`_parse_permissions` 上方）：

```python
# feature 布尔 -> (默认值, 其覆盖的命令键列表)。仅当旧值 != 默认才写覆盖。
_FEATURE_MIGRATION: dict[str, tuple[bool, list[str]]] = {
    "report": (True, ["world today"]),
    "events": (True, ["world events"]),
    "guilds_bases": (False, ["guild"]),               # 组键
    "players": (False, ["player", "rank", "me"]),
    "server_admin_basic": (False, ["server announce", "server save",
                                   "server kick", "server unban"]),
    "server_admin_danger": (False, ["server ban", "server shutdown", "server stop"]),
}


def _migrate_legacy(raw: Mapping, _set, invalid: list[str]) -> None:
    f = raw.get("features", {}) or {}
    if isinstance(f, Mapping):
        for feat, (default, keys) in _FEATURE_MIGRATION.items():
            val = bool(f.get(feat, default))
            if val != default:
                for key in keys:
                    _set(key, "enabled", val)
    from .presentation.command_registry import LOCKABLE_COMMANDS
    raw_cmds = raw.get("admin_only_commands", [])
    if isinstance(raw_cmds, list):
        for c in raw_cmds:
            if not isinstance(c, str):
                continue
            name = c.strip()
            if not name:
                continue
            if name in LOCKABLE_COMMANDS:
                _set(name, "admin_only", True)
            else:
                invalid.append(name)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/unit/config_command_permissions_test.py -q`
Expected: PASS

- [ ] **Step 5: 全库回归（此刻门控仍读 features，应仍绿）**

Run: `pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: PASS（旧 `config_permissions_test.py`/`config_admin_only_warn_test.py` 若断言已删字段会红——改这些测试为断言新 `command_overrides`/`invalid_command_keys`，作为本任务一部分）

- [ ] **Step 6: 提交**

```bash
git add palworld_terminal/config.py tests/unit/config_command_permissions_test.py tests/unit/config_permissions_test.py tests/unit/config_admin_only_warn_test.py
git commit -m "feat(perm): PermissionsConfig.command_overrides + legacy 迁移（features/admin_only_commands）"
```

---

## Task 5: 采集接线切换到 overrides

**Files:**
- Modify: `palworld_terminal/container.py`（L17 import、L154 `active_endpoints(self._cfg.features)`）
- Test: `tests/integration/feature_groups_off_test.py`（改名/改断言）、`tests/unit/container_features_test.py`

**Interfaces:**
- Consumes: Task 3 `command_permissions.active_endpoints`；`PermissionsConfig.command_overrides`
- Produces: container 用 overrides 驱动轮询端点集

- [ ] **Step 1: 改测试（先失败）**

把 `tests/integration/feature_groups_off_test.py`、`tests/unit/container_features_test.py` 中构造 `features=...` 驱动 `active_endpoints` 的断言，改为构造 `permissions.command_overrides` 驱动：

```python
# container_features_test.py（示意断言）
from palworld_terminal.application.command_permissions import CommandOverride as CO
# guild 组默认关 → 不含 GAME_DATA
cfg = make_cfg(command_overrides={})
assert EndpointName.GAME_DATA not in container_active_endpoints(cfg)
# guild 组开 → 含 GAME_DATA
cfg2 = make_cfg(command_overrides={"guild": CO(enabled=True)})
assert EndpointName.GAME_DATA in container_active_endpoints(cfg2)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/integration/feature_groups_off_test.py tests/unit/container_features_test.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

container.py L17 改 import：

```python
from .application.command_permissions import active_endpoints
```

container.py L154：

```python
            endpoints=active_endpoints(self._cfg.permissions.command_overrides),
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/integration/feature_groups_off_test.py tests/unit/container_features_test.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/container.py tests/integration/feature_groups_off_test.py tests/unit/container_features_test.py
git commit -m "feat(perm): 采集端点集改由 command_overrides 派生"
```

---

## Task 6: 门控落点切换到生效值

**Files:**
- Modify: `palworld_terminal/presentation/command_registry.py`（新增 `METHOD_PATH`）
- Modify: `palworld_terminal/presentation/commands.py`（`_gated` L68-78、`_dispatch_read` L337/340、`admin_write` L453、`confirm` L571、`link` L389、`_admin_locked` L294-296、`admin_denied` L623-626、`_group_help` L306）
- Modify: `palworld_terminal/presentation/formatters.py`（`_action_visible` L141-152、`visible_actions` L155-170、`format_help` L178）
- Modify: `palworld_terminal/main.py`（`format_help`/`admin_denied` 调用传参）
- Test: `tests/unit/commands_gating_test.py`、`commands_dispatch_test.py`、`commands_admin_write_test.py`、`formatters_test.py`、`formatters_hierarchy_test.py`、`formatters_admin_help_test.py`、`main_permission_gate_test.py`

**Interfaces:**
- Consumes: `command_permissions.effective_enabled/effective_admin_only`；`command_overrides`
- Produces: 所有门控读生效值；`command_registry.METHOD_PATH: dict[str, str]`（读方法名→完整路径，供 `_gated`）

> 单任务体量偏大但**高内聚且必须原子**（半切会留双语义）。所有落点共享同一替换规则：`self._cfg.features.enabled(组)` → `effective_enabled(self._cfg.permissions.command_overrides, 完整路径)`；`... in self._cfg.permissions.admin_only_commands` → `effective_admin_only(self._cfg.permissions.command_overrides, path)`。

- [ ] **Step 1: 写/改失败测试**

补一条继承感知门控测试，验证「组级 enable=False 关掉叶子」「叶子锁 admin_only 拒 guest」：

```python
# tests/unit/commands_gating_test.py 追加
import pytest
from palworld_terminal.application.command_permissions import CommandOverride as CO

@pytest.mark.asyncio
async def test_group_disable_blocks_leaf(make_commands):
    cmds = make_commands(command_overrides={"guild": CO(enabled=False)})
    out = await cmds.guild_grp("umo", "list", True, "u1", False)
    assert "未启用" in out or "feature_disabled" in out  # 视 L() 文案

@pytest.mark.asyncio
async def test_leaf_admin_lock_denies_guest(make_commands):
    cmds = make_commands(command_overrides={"guild": CO(enabled=True), "guild list": CO(admin_only=True)})
    out = await cmds.guild_grp("umo", "list", True, "guest", False)
    assert "管理员" in out
```

（`make_commands` fixture：把现有测试构造 `features=` 的替身改为构造 `permissions.command_overrides=`；同步更新 `commands_dispatch_test`/`commands_admin_write_test` 的替身。）

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/commands_gating_test.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`command_registry.py` 新增（`FLAT_ACTIONS` 之后）：

```python
# 读方法名 → 完整路径（供 commands._gated 按路径判定 enable）。
# server 写走 admin_write、link 走 link handler，均不经 _gated，故仅收 read 方法。
METHOD_PATH: dict[str, str] = {
    method: (f"{grp} {sub}" if grp else sub)
    for grp, actions in [(g, a) for g, a in DISPATCH.items()]
    for sub, (method, _feat, gate) in actions.items()
    if gate == "read"
}
METHOD_PATH.update({
    name: name for name, (_m, _f, gate) in FLAT_ACTIONS.items() if gate == "read"
})
```

`commands.py` 顶部 import：

```python
from ..application.command_permissions import effective_admin_only, effective_enabled
from .command_registry import METHOD_PATH
```

`_gated`（L68-78）改为按路径查生效 enable：

```python
def _gated(fn):
    """命令 gating：按方法名映射完整路径，查生效 enable，未启用回 feature_disabled。"""
    @functools.wraps(fn)
    async def wrapper(self, *args, **kwargs):
        path = METHOD_PATH[fn.__name__]
        if not effective_enabled(self._cfg.permissions.command_overrides, path):
            return L("feature_disabled")
        return await fn(self, *args, **kwargs)
    return wrapper
```

`_dispatch_read` L337：

```python
        if not effective_enabled(self._cfg.permissions.command_overrides, f"{group} {p.sub}"):
            return L("feature_disabled")
```

`_admin_locked`（L294-296）：

```python
    def _admin_locked(self, path: str, sender_id: str, is_admin: bool) -> bool:
        """admin_only 锁（下沉）：按完整路径查生效 admin_only，锁定且非管理员 → True。"""
        return effective_admin_only(self._cfg.permissions.command_overrides, path) and not is_admin
```

`admin_write` L453（门 2 feature 门）：

```python
        if not effective_enabled(self._cfg.permissions.command_overrides, f"server {command_str}"):
            return L("feature_disabled")
```

`confirm` L571（stale 复检——按完整路径 `server {command_str}`）：

```python
        if not effective_enabled(self._cfg.permissions.command_overrides, f"server {p.command_str}"):
            return L("admin_confirm_stale")
```

`link` L389（feat_group=core 恒开 → 直接判 enable=True 恒成立；保留判定形式一致）：

```python
        if not effective_enabled(self._cfg.permissions.command_overrides, f"link {p.sub}"):
            return L("feature_disabled")
```

`admin_denied`（L623-626）：

```python
    def admin_denied(self, command_str: str, sender_id: str) -> str | None:
        if effective_admin_only(self._cfg.permissions.command_overrides, command_str) \
                and not self.is_plugin_admin(sender_id):
            return L("admin_required")
        return None
```

`formatters.py` `_action_visible`（L141-152）改吃 overrides + 按路径查 enable：

```python
def _action_visible(path: str, spec: ActionSpec, is_admin: bool, overrides) -> bool:
    from ..application.command_permissions import effective_enabled
    _method, _feat_group, gate = spec
    if not effective_enabled(overrides, path):
        return False
    if gate in ("admin_write", "admin"):
        return is_admin
    return True
```

`visible_actions`（L155-170）签名 `features` → `overrides`，构造 path：

```python
def visible_actions(group, is_admin, overrides, world_mode="multi"):
    if group == "link" and world_mode == "single":
        return []
    return [
        (sub, spec)
        for sub, spec in DISPATCH.get(group, {}).items()
        if _action_visible(f"{group} {sub}", spec, is_admin, overrides)
    ]
```

`format_help`（L178）签名 `features` → `overrides`，内部传递不变。

`commands.py` `_group_help` L306：`visible_actions(group, is_admin, self._cfg.permissions.command_overrides, self._world_mode())`。

`main.py`：所有 `format_help(..., self._cfg.features, ...)` / `visible_actions(..., features, ...)` 调用改传 `cfg.permissions.command_overrides`；`admin_denied` 调用不变（签名未改）。用 `grep -rn "self._cfg.features\|\.features," palworld_terminal/` 确保零残留 `features` 门控读。

- [ ] **Step 4: 跑测试确认通过 + 全库回归**

Run: `pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: PASS（`formatters_test`/`formatters_hierarchy_test`/`formatters_admin_help_test`/`commands_*`/`main_permission_gate_test` 中构造 `features=` 的替身改为 `command_overrides=`，作为本任务一部分修复）

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/presentation/command_registry.py palworld_terminal/presentation/commands.py palworld_terminal/presentation/formatters.py palworld_terminal/main.py tests/
git commit -m "feat(perm): 门控/可见性全落点改查命令生效值（enable + admin_only）"
```

---

## Task 7: 删除 FeaturesConfig / feature_groups / COMMANDS 双源

**Files:**
- Delete: `palworld_terminal/application/feature_groups.py`
- Modify: `palworld_terminal/config.py`（删 `FeaturesConfig` L117-137、`_default_features` L136-137、`AppConfig.features` L225、`parse_config` 内 `features=` 构造 L415-424/473）
- Modify: `palworld_terminal/presentation/command_registry.py`（删 `COMMANDS` L5-19、`COMMAND_GROUP` L20）
- Test: 删 `tests/unit/config_features_test.py`、`tests/unit/config_server_admin_test.py` 中 `features.enabled` 断言；确认无残留 import

**Interfaces:**
- Consumes: 无新增（清理任务）
- Produces: `AppConfig` 不再有 `features` 字段；`command_registry` 无 `COMMANDS`/`COMMAND_GROUP`

> 前置确认：Task 6 后**再无**任何生产代码读 `cfg.features` / `COMMAND_GROUP` / `feature_groups`。本任务先 grep 验证零引用再删。

- [ ] **Step 1: 验证零引用**

Run: `grep -rn "FeaturesConfig\|cfg.features\|_cfg.features\|COMMAND_GROUP\|feature_groups\|\.features\b" palworld_terminal/`
Expected: 仅剩本任务将删的定义处（config.py 定义、command_registry 定义），无消费点

- [ ] **Step 2: 删除 + 改测试（先红）**

删 `feature_groups.py`；删 config.py 的 `FeaturesConfig`/`_default_features`/`AppConfig.features` 字段/`parse_config` 内 `features` 构造与传参；删 command_registry `COMMANDS`/`COMMAND_GROUP`。删/改引用它们的测试文件。

- [ ] **Step 3: 全库回归**

Run: `pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "refactor(perm): 删除 FeaturesConfig/feature_groups/COMMANDS 双真相源"
```

---

## Task 8: `_conf_schema` + config_view 往返闭合

**Files:**
- Modify: `_conf_schema.json`（删 `features`/`admin_only_commands` 项；加 `command_permissions`）
- Modify: `palworld_terminal/presentation/config_view.py`（`_TOP_KEYS` L30-34、新增 `command_permissions` 形状校验）
- Test: `tests/unit/config_view_validate_test.py`、`tests/unit/conf_schema_test.py`

**Interfaces:**
- Consumes: `command_permissions.COMMAND_META`、`enable_configurable`、`admin_configurable`、`admin_forced_true`、`command_registry.DISPATCH`
- Produces: config_view 接受/校验 `command_permissions`；拒绝形状非法项

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/config_view_validate_test.py 追加
def test_command_permissions_accepts_valid_shape():
    body = {"command_permissions": {"guild": {"enabled": True}, "guild list": {"admin_only": True}}}
    err = validate_body(body)              # 用该模块现有校验入口
    assert err is None

def test_command_permissions_rejects_bad_shape():
    body = {"command_permissions": {"guild": {"enabled": "yes"}}}   # 非 bool
    assert validate_body(body) is not None
    body2 = {"command_permissions": ["not", "a", "map"]}
    assert validate_body(body2) is not None

def test_top_keys_dropped_features():
    assert validate_body({"features": {"report": True}}) is not None   # 已非白名单
    assert validate_body({"admin_only_commands": ["x"]}) is not None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/config_view_validate_test.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

config_view.py `_TOP_KEYS`（L30-34）——删 `features`、`admin_only_commands`，加 `command_permissions`：

```python
_TOP_KEYS = {
    "servers", "routing", "group_bindings", "custom_headers",
    "polling", "world", "bases", "privacy", "history", "players",
    "permission_admins", "command_permissions", "server_admin",
}
```

新增 `command_permissions` 形状校验（照现 `admin_only_commands` 独立校验位置，L174 附近）：

```python
    # command_permissions：dict[str, {enabled?:bool, admin_only?:bool}]。
    if "command_permissions" in body:
        cp = body["command_permissions"]
        if not isinstance(cp, dict):
            return _err("invalid_shape", "command_permissions")
        from ..application.command_permissions import COMMAND_META
        from .command_registry import DISPATCH
        valid_keys = set(COMMAND_META) | set(DISPATCH.keys())
        for key, ov in cp.items():
            if key not in valid_keys:
                return _err("unknown_key", f"command_permissions.{key}")
            if not isinstance(ov, dict):
                return _err("invalid_shape", f"command_permissions.{key}")
            for fld in ("enabled", "admin_only"):
                if fld in ov and not isinstance(ov[fld], bool):
                    return _err("invalid_shape", f"command_permissions.{key}.{fld}")
```

`_conf_schema.json`：删 `features`（6 bool 项）与 `admin_only_commands` 项；新增 `command_permissions`（object 型，描述指向插件设置页为主编辑面）。exact JSON 依仓库 schema 风格（object 型条目），描述含：「命令权限（启用/仅管理员）。推荐用插件设置页「权限」章可视化编辑；此处为高级 JSON 覆盖。键=组名或完整命令路径，值={enabled, admin_only}」。

- [ ] **Step 4: 跑测试确认通过 + 全库**

Run: `pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: PASS（`conf_schema_test` 若锚定 features 键需同步改）

- [ ] **Step 5: 提交**

```bash
git add _conf_schema.json palworld_terminal/presentation/config_view.py tests/unit/config_view_validate_test.py tests/unit/conf_schema_test.py
git commit -m "feat(perm): _conf_schema + config_view 往返承载 command_permissions"
```

---

## Task 9: 前端命令树描述 + 跨端锚定

**Files:**
- Modify: `frontend/src/lib/schema.ts`（`PAL_COMMANDS` L98-107 升级为完整命令树描述）
- Test: `tests/unit/frontend_pal_commands_test.py`

**Interfaces:**
- Consumes: 后端 `command_permissions.COMMAND_META` + configurable 谓词（跨端锚定源）
- Produces: 前端 `PAL_TREE`（完整命令树 + 每命令 configurable 标志），供 SettingsPanel 渲染

- [ ] **Step 1: 写失败锚定测试**

```python
# tests/unit/frontend_pal_commands_test.py 升级
# 断言 schema.ts 的 PAL_TREE 覆盖全部命令路径且 configurable 标志与后端派生一致。
def test_frontend_tree_matches_backend_meta():
    tree = _parse_pal_tree_from_schema_ts()      # 解析 TS 常量
    from palworld_terminal.application.command_permissions import (
        COMMAND_META, enable_configurable, admin_configurable, admin_forced_true,
    )
    assert {n["path"] for n in tree} == set(COMMAND_META)
    for n in tree:
        p = n["path"]
        assert n["enableConfigurable"] == enable_configurable(p)
        assert n["adminConfigurable"] == admin_configurable(p)
        assert n["adminForced"] == admin_forced_true(p)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/unit/frontend_pal_commands_test.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`schema.ts` 用 `PAL_TREE`（含 group、path、label、enableConfigurable、adminConfigurable、adminForced、danger 标志）取代 15 项 `PAL_COMMANDS`。内容须与后端派生全等（锚定测试守）。按组 + 扁平「其他」段组织。

- [ ] **Step 4: 跑测试确认通过 + 前端构建**

Run: `pytest tests/unit/frontend_pal_commands_test.py -q && (cd frontend && npm run build && npm test)`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/lib/schema.ts tests/unit/frontend_pal_commands_test.py
git commit -m "feat(perm/fe): 命令树描述 PAL_TREE 跨端锚定后端派生元数据"
```

---

## Task 10: 前端权限章命令树 UI + collectBody

**Files:**
- Modify: `frontend/src/lib/chapters.ts`（删 `feature` 章 L16）
- Modify: `frontend/src/components/SettingsPanel.vue`（权限章：AdminCard + 命令树表；collectBody 回写 `command_permissions`）
- Test: `frontend/src/**/*.spec.ts`（新增命令树组件测试 + collectBody 测试）

**Interfaces:**
- Consumes: Task 9 `PAL_TREE`；后端 `command_permissions` 形状
- Produces: 权限章命令树 UI；`collectBody` 输出稀疏 `command_permissions` dict

- [ ] **Step 1: 写失败前端测试**

```ts
// 命令树：组级开关写组键；叶子覆盖写叶子键；不可配格禁用；collectBody 稀疏输出
it('collectBody emits sparse command_permissions', () => {
  const state = makeState({ 'guild': { enabled: true }, 'world today': { enabled: false } })
  expect(collectBody(state).command_permissions).toEqual({
    guild: { enabled: true }, 'world today': { enabled: false },
  })
})
it('non-configurable cells are locked', () => {
  // world status 的 enable 单元格 disabled；server kick 的 admin_only 单元格锁定为 on
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm test`
Expected: FAIL

- [ ] **Step 3: 实现**

- `chapters.ts` 删 `feature` 章（内容并入 `permissions` 章）。
- `SettingsPanel.vue` 权限章：保留 AdminCard（`permission_admins`）；新增命令树表——按组分组可折叠，组头行有「整组启用/整组仅管理员」批量开关（写组键覆盖），叶子行两列开关（enable/admin_only），不可配格置灰锁定并显恒定生效值，danger 命令行加标记，继承 vs 覆盖视觉区分。
- `collectBody`：从命令树 state 收敛为稀疏 `command_permissions`（只输出偏离继承默认的覆盖）。
- 若树 UI 视觉复杂，实现期可用 artifact-design 协作定稿（视觉基调沿用 Phase 1 观测台系统）。

- [ ] **Step 4: 跑测试通过 + 构建 + no-drift**

Run: `cd frontend && npm run build && npm test`；回仓库根 `git status --porcelain pages/settings`（应无意外脏；构建产物按 `npm run build` 内置 normalize-eol 保持 LF）
Expected: PASS，产物 LF 无幻影

- [ ] **Step 5: 提交**

```bash
git add frontend/ pages/settings/
git commit -m "feat(perm/fe): 设置页权限章命令树 UI + collectBody 稀疏回写"
```

---

## Task 11: 文档 + 版本 + 迁移对照

**Files:**
- Modify: `README.md`（权限/功能表述→命令树控制面；旧→新配置对照表）
- Modify: `metadata.yaml` / `pyproject.toml` / `package.json` / 版本源四处 → v0.9.6
- Modify: `tests/unit/readme_test.py`（中文锚点短语随文案更新）

**Interfaces:**
- Consumes: 全部前序任务的最终行为
- Produces: 与实现一致的文档 + 版本四源全等

- [ ] **Step 1: 改版本四源 + README + 锚点测试**

grep 现有版本源位置（Phase 1 v0.9.5 落点）逐一改 v0.9.6；README 更新权限章说明 + 加旧→新配置迁移对照表（features 布尔/admin_only_commands → command_permissions 键）；`readme_test.py` 中文锚点短语同步。

- [ ] **Step 2: 全绿**

Run: `pytest -q && ruff check palworld_terminal && mypy palworld_terminal && (cd frontend && npm run build && npm test)`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "docs(perm): 命令树权限文档 + 迁移对照 + v0.9.6"
```

---

## Self-Review 结论（写计划后自查）

- **Spec 覆盖**：§1 核心模型→T1-2；§2 配置形状→T4；§3 生效值 API→T1-3；§4 门控改造→T6；§5 迁移→T4；§6 采集派生→T3/T5；§7 设置页树 UI→T9-10；§8 _conf_schema/config_view→T8；§9 锚定与测试→散布各任务 + T1/T9 防漂移；§10 版本文档→T11。全覆盖。
- **类型一致**：`CommandOverride(enabled, admin_only)`、`command_overrides: dict[str, CommandOverride]`、`effective_enabled/effective_admin_only(overrides, path)`、`active_endpoints(overrides)`、`METHOD_PATH` 贯穿一致。
- **占位符**：无 TBD；`_conf_schema.json` 的 command_permissions 精确 JSON 与前端 PAL_TREE/树组件的完整代码在实现期按仓库风格落地（T8/T9/T10 描述了确切形状与锚定约束）——这些是需读现有 schema/组件风格的落地项，已给出形状、键名、校验规则与测试断言。
- **风险点**：T4 循环 import（已给下沉 import 兜底）；T6 原子性（半切留双语义，须一次完成 + 全库回归）；T7 删除前 grep 零引用门禁。
