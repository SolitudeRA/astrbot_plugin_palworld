# 分级命令架构 + 模式基础 + 变体 实施计划（v0.9.5 Phase 1）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 26 个扁平 `/pal <X>` 命令重构为分级 `/pal <组> <动作>`（5 组 + 6 扁平），为单/多世界模式打地基（`world_mode` + 模式感知 resolve），并引入命令变体机制（`rank today|total|level`）。

**Architecture:** 扁平自解析（非 AstrBot 原生嵌套组）：每组一个 `@pal.command("<组>")` handler，Commands 层自解析子动作首词、查分发表路由。门控**下沉进分发**（功能门 per-子动作、`admin_denied` 按完整路径、写走 `admin_write`）。先加地基（解析/模式/rank/锁校验）与新机器（分发表/组方法，additive 保绿），再原子切换 main.py 注册 + 迁移测试，最后 help/前端/文档。

**Tech Stack:** Python 3.11+、AstrBot 插件框架、aiosqlite；前端 Vue3 + reka-ui + Vite；pytest / vitest。

## Global Constraints

- **依据 spec**：`docs/superpowers/specs/2026-07-14-command-hierarchy-design.md`（已过三视角对抗复核）。
- **git 提交不得出现任何 Claude / AI / 🤖 署名**。
- **包内 import 一律相对**，函数体内绝不绝对自导入（`no_absolute_self_import_test` 红线）。
- **Windows 上 `python` 被拦截**，一律用 `./.venv/Scripts/python.exe` 跑 pytest / ruff / mypy。
- **门控落点（铁律，spec §4.1）**：`admin_denied` 下沉 Commands 分发按**完整路径**（`world status`）；功能门改**分发循环内 per-子动作**（不用方法级 `_gated`——一个 world handler 跨 core/events/report 三门）；busy/inflight 门闩保留；写命令走 `admin_write`（门序 admin 先于 feature 不变，server 组不套 `_gated`）。**任一写动作漏门 = 无鉴权关服**。
- **两种粒度分家（spec §8）**：`PAL_REGISTERED`(11 首词)供注册锚定；`PAL_COMMAND_STRINGS`/`LOCKABLE_COMMANDS`/`admin_only_commands`/`_NON_LOCKABLE` 走**完整路径**。`_NON_LOCKABLE` 两副本（config.py + command_registry.py）须全等。
- **锁迁移防失锁（spec §7 B2）**：`admin_only_commands` 旧扁平值升级后不匹配新路径=静默失锁；`_parse_permissions` 校验每条属 LOCKABLE、未知条目保留并告警。
- **`world_mode` 嵌 `routing`（spec §5 M1）**：不做裸顶层标量（会被 `_TOP_KEYS` 拒 + 无渲染件）。
- **单模式安全（spec §5 M1）**：single 分支置 resolve 顶端；`_authorized` 放宽读、**写仍 admin 硬门**；single+restricted 产生显式访问告警；`/pal link` 单模式 handler 顶部拒（先于 DB 写）。
- **rank total（spec §6）**：留存期内累计（非全时段）；新无窗聚合方法；**复用 load_excluded_keys + 名字级收敛剔除**；strict **双砍 today/total**；mode 串 `time→today` 破坏性重命名。
- **裸 group 迷你帮助复用 `format_help` 同一角色谓词**（guest 不见写命令）。
- **解析防御式 strip-if-present**（不假定组词位置），保留 @override/ArgError/空白折叠。
- **版本 `v0.9.0` → `v0.9.5`**（四源）；Phase 2 同为 v0.9.5 不再抬版。
- **前端改后 build + verify-bundle + no-drift**。
- **子代理 model 一律 opus**。

## 文件结构总览

| 文件 | 职责 | Task |
|---|---|---|
| `presentation/server_arg.py` | 分级解析（组词 strip + 子动作 + 参数 + @override） | T1 |
| `config.py` + `_conf_schema.json` + `config_view.py` | `routing.world_mode` + `_ENUMS` | T2 |
| `application/routing_service.py` | resolve 模式感知 + 单模式告警 | T3 |
| `application/query_service.py` + `adapters/sqlite_repository.py` | rank mode + total 无窗聚合 + 名字级收敛 + strict 双砍 | T4 |
| `config.py`（permissions） | admin_only_commands 未知锁校验+告警 | T5 |
| `presentation/command_registry.py` | 分发表 + PAL_REGISTERED + 完整路径常量 + _NON_LOCKABLE 分级 | T6 |
| `presentation/commands.py` | 组分发方法 + 门控下沉（additive） | T7 |
| `main.py` + 测试迁移 | 11 handler 切换 + 删旧 + 锚定翻新 | T8 |
| `presentation/formatters.py` + link handler | 分级 help + 裸组迷你帮助 + 单模式 link 守卫 | T9 |
| `frontend/src/**` + `pages/settings/` | world_mode enum + PAL_COMMANDS 完整路径 + 产物 | T10 |
| `docs/*` + `README.md` + 版本四源 | 分级文档 + 锁迁移映射表 + v0.9.5 | T11 |

---

## Task 1: server_arg —— 分级解析

**Files:**
- Modify: `palworld_terminal/presentation/server_arg.py`
- Test: `tests/unit/server_arg_hierarchy_test.py`（新建）

**Interfaces:**
- Produces: `parse_group(message_str, group) -> ParsedGroup(sub: str, rest: str, server_override: str | None)`——剥 `/pal <group>` 前缀（strip-if-present）、取子动作首词 `sub`、剩余整串 `rest`、尾 @override。T7 消费。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/server_arg_hierarchy_test.py`：

```python
import pytest
from palworld_terminal.presentation.server_arg import parse_group, ArgError


def test_basic_sub_and_rest():
    p = parse_group("/pal guild info 战狼帮", "guild")
    assert p.sub == "info" and p.rest == "战狼帮" and p.server_override is None


def test_three_segment_with_override():
    p = parse_group("/pal guild info 战狼帮 @alpha", "guild")
    assert p.sub == "info" and p.rest == "战狼帮" and p.server_override == "alpha"


def test_group_word_absent_still_parses():
    # AstrBot 某些版本会剥掉组词，只留子动作
    p = parse_group("info 战狼帮", "guild")
    assert p.sub == "info" and p.rest == "战狼帮"


def test_bare_group_empty_sub():
    p = parse_group("/pal server", "server")
    assert p.sub == "" and p.rest == ""


def test_reason_keeps_spaces_collapsed():
    p = parse_group("/pal server kick Alice 刷屏 挂机", "server")
    assert p.sub == "kick" and p.rest == "Alice 刷屏 挂机"


def test_double_override_raises():
    with pytest.raises(ArgError):
        parse_group("/pal server kick Alice @a @b", "server")
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/server_arg_hierarchy_test.py -v`
Expected: FAIL —— `ImportError: cannot import name 'parse_group'`

- [ ] **Step 3: 实现 parse_group**

`server_arg.py` 加（复用现有 `_strip_prefix` 的逐一 strip 思路 + `parse_arg` 的尾 @override 逻辑）：

```python
@dataclass(slots=True)
class ParsedGroup:
    sub: str
    rest: str
    server_override: str | None


def parse_group(message_str: str, group: str) -> ParsedGroup:
    body = _strip_prefix(message_str, group)  # 剥 `/`、`pal`(若在)、group(若在)
    if not body:
        return ParsedGroup(sub="", rest="", server_override=None)
    tokens = body.split()
    override: str | None = None
    if tokens[-1].startswith("@") and len(tokens[-1]) > 1:
        if len(tokens) >= 2 and tokens[-2].startswith("@") and len(tokens[-2]) > 1:
            raise ArgError("multiple server overrides")
        override = tokens[-1][1:]
        tokens = tokens[:-1]
    if not tokens:
        return ParsedGroup(sub="", rest="", server_override=override)
    sub = tokens[0]
    rest = " ".join(tokens[1:]).strip()
    return ParsedGroup(sub=sub, rest=rest, server_override=override)
```

注：`_strip_prefix(message_str, group)` 现签名即「剥 `/`+`pal`(若在)+第二参(若在)」——组词当 subcommand 传入即 strip-if-present，无需假定位置。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/server_arg_hierarchy_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/presentation/server_arg.py tests/unit/server_arg_hierarchy_test.py
git commit -m "feat(parse): parse_group 分级解析（组词 strip-if-present + 子动作 + @override）"
```

---

## Task 2: config —— routing.world_mode + _ENUMS

**Files:**
- Modify: `palworld_terminal/config.py`、`_conf_schema.json`、`palworld_terminal/presentation/config_view.py`
- Test: `tests/unit/config_world_mode_test.py`（新建）

**Interfaces:**
- Produces: `RoutingConfig.world_mode: str`（"single"|"multi"，默认 "multi"）；`config_view._ENUMS` 含 `"routing.world_mode"`。T3/T10 消费。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/config_world_mode_test.py`：

```python
from palworld_terminal.config import parse_config


def _base(**routing):
    raw = {"servers": [], "routing": routing, "polling": {}, "world": {}, "bases": {},
           "privacy": {}, "history": {}, "features": {}, "players": {}}
    return parse_config(raw, {})


def test_world_mode_default_multi():
    assert _base().routing.world_mode == "multi"


def test_world_mode_single():
    assert _base(world_mode="single").routing.world_mode == "single"


def test_world_mode_invalid_falls_back_multi():
    assert _base(world_mode="oops").routing.world_mode == "multi"


def test_conf_schema_world_mode_enum():
    import json
    from pathlib import Path
    s = json.loads((Path(__file__).resolve().parents[2] / "_conf_schema.json").read_text(encoding="utf-8"))
    wm = s["routing"]["items"]["world_mode"]
    assert wm["type"] == "string" and set(wm["options"]) == {"multi", "single"} and wm["default"] == "multi"


def test_config_view_enums_has_world_mode():
    from palworld_terminal.presentation.config_view import _ENUMS
    assert "routing.world_mode" in _ENUMS
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_world_mode_test.py -v`
Expected: FAIL

- [ ] **Step 3: RoutingConfig 加字段**

`config.py`：先读 `RoutingConfig` 现结构（`access_mode`/`default_server` 附近）。加 `world_mode: str`（默认 "multi"）；`parse_config` 的 routing 解析处加 `world_mode=_one_of(r.get("world_mode"), {"single","multi"}, "multi")`（若无 `_one_of` 辅助则内联 `v if v in {...} else "multi"`）。

- [ ] **Step 4: _conf_schema.json + config_view._ENUMS**

`_conf_schema.json` 的 `routing.items` 加：
```json
"world_mode": { "type": "string", "options": ["multi", "single"], "default": "multi",
  "description": "运行模式：multi 多世界（按群绑定/切换服务器）；single 单世界（所有操作对应唯一服务器）。⚠️ single + restricted 并存时访问控制不生效，读命令对所有上下文开放。" }
```
`config_view.py` 的 `_ENUMS`（约 :47-51）加 `"routing.world_mode": {"multi", "single"}`（照现有 `routing.access_mode` 等条目形态）。

- [ ] **Step 5: 运行确认通过 + 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_world_mode_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add palworld_terminal/config.py _conf_schema.json palworld_terminal/presentation/config_view.py tests/unit/config_world_mode_test.py
git commit -m "feat(config): routing.world_mode(single/multi) + _ENUMS + schema"
```

---

## Task 3: routing_service —— 模式感知 resolve + 单模式告警

**Files:**
- Modify: `palworld_terminal/application/routing_service.py`
- Test: `tests/unit/routing_world_mode_test.py`（新建）

**Interfaces:**
- Consumes: `RoutingConfig.world_mode`（T2）。
- Produces: `resolve` 单模式恒解析唯一服务器 + `_authorized` 放宽；`RoutingService.single_restricted_warning() -> str | None`（供 T9/main 启动告警）。T7 消费。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/routing_world_mode_test.py`——先读 `routing_service.py` 现 `resolve`/`Resolution`/`_authorized`/构造对齐真实接口，测：
- multi 现状回归（1 条既有场景不变）。
- single：私聊也解析到唯一服务器（绕过 restricted 私聊早退）、忽略 @override 与群绑定。
- single + 0 台 → error「未配置服务器」。
- single + >1 台 → 首台 + 告警。
- `single_restricted_warning()`：single+restricted → 非 None；multi 或 single+open → None。

（构造 `RoutingService` 用现有 fake repo/config 范式；断言 `resolution.server` 与 `resolution.error`。）

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/routing_world_mode_test.py -v`
Expected: FAIL

- [ ] **Step 3: resolve 单模式分支置顶 + 告警**

`resolve` **最顶端**（早于现私聊 restricted 早退）加：
```python
if self._cfg.routing.world_mode == "single":
    ready = [s for s in self._cfg.servers if s.ready]
    if not ready:
        return Resolution(server=None, error=L("server_none"))
    # >1 台：首台 + 告警（记 warning 一次，具体日志方式照现有）
    return Resolution(server=ready[0], error=None)
```
（`_authorized` 在单模式不再被调用——单模式直接返回，天然放宽。）加 `single_restricted_warning`：
```python
def single_restricted_warning(self) -> str | None:
    if self._cfg.routing.world_mode == "single" and self._cfg.routing.access_mode == "restricted":
        return L("single_restricted_warning")
    return None
```
locale 加 `single_restricted_warning` 文案。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/routing_world_mode_test.py tests/unit/routing_service_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS（multi 既有 routing 测试不破）

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/application/routing_service.py palworld_terminal/presentation/locale.py tests/unit/routing_world_mode_test.py
git commit -m "feat(routing): resolve 模式感知（single 恒唯一服务器 + restricted 架空告警）"
```

---

## Task 4: rank 变体 —— today/total/level + total 无窗聚合 + 隐私

**Files:**
- Modify: `palworld_terminal/adapters/sqlite_repository.py`、`palworld_terminal/application/query_service.py`、`palworld_terminal/presentation/commands.py`、`presentation/command_registry.py`(HELP_LINE rank)、`presentation/locale.py`
- Test: `tests/unit/rank_total_test.py`（新建）、`tests/unit/commands_rank_test.py`（改 time→today）

**Interfaces:**
- Produces: `Repository.total_durations(world_id) -> dict[player_key, int]`（无日窗 Σobserved_seconds）；`QueryService.rank(world, mode)` mode∈{today,total,level}；`commands.rank` mode 串 today/total/level。T7 消费。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/rank_total_test.py`：total 聚合正确（跨多日会话累加）；**隐藏一个有历史时长的玩家 → 其整组名字从 total 榜消失**（复用名字级收敛，非只按 key）；strict → total 回 notice。改 `commands_rank_test.py`：`time`→`today` 断言；strict 下 today 与 total 都回 notice。先读 `query_service.rank`(today/level 现实现) + `load_excluded_keys`/`banned_names` 收敛 + `format_rank` `not strict` 守卫对齐。

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/rank_total_test.py -v`
Expected: FAIL

- [ ] **Step 3: repo 无窗聚合 + query rank mode + strict 双砍**

`sqlite_repository.py` 加 `total_durations(world_id)`——`SELECT player_key, SUM(observed_seconds) FROM player_observations WHERE world_id=? GROUP BY player_key`（**注**：total 直接 Σobserved_seconds，无墙钟 overlap——与 today 窗口逻辑不同；确认列名/表以真实为准）。`query_service.rank(world, mode)`：mode=="total" 走 `total_durations` + **复用 `load_excluded_keys` + 名字级收敛剔除**（照 today 的 `banned_names` 整组剔除，不得只按 key）；mode=="today"/"level" 现状。`commands.rank`：mode 串 `today/total/level`（缺省 today），`if mode in ("today","total") and strict: return notice`（原只 `time`）；`format_rank` `not strict` 守卫覆盖 total。HELP_LINE rank 改 `[today|total|level]`；locale 键 `rank_time_strict`→`rank_duration_strict`（或保留但覆盖 total）。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/rank_total_test.py tests/unit/commands_rank_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/adapters/sqlite_repository.py palworld_terminal/application/query_service.py palworld_terminal/presentation/commands.py palworld_terminal/presentation/command_registry.py palworld_terminal/presentation/locale.py tests/unit/rank_total_test.py tests/unit/commands_rank_test.py
git commit -m "feat(rank): today/total/level 变体 + total 留存期聚合（复用名字级收敛 + strict 双砍）"
```

---

## Task 5: config —— admin_only_commands 未知锁校验 + 告警

**Files:**
- Modify: `palworld_terminal/config.py`
- Test: `tests/unit/config_admin_only_warn_test.py`（新建）

**Interfaces:**
- Consumes: `command_registry.LOCKABLE_COMMANDS`（T6 会改为完整路径——本任务先按现值校验，T6 更新后自然对齐；为避免循环依赖，`_parse_permissions` 运行时 import LOCKABLE 或接受注入）。
- Produces: `PermissionsConfig.unknown_locks: list[str]`（未知锁条目，供状态页/日志告警）。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/config_admin_only_warn_test.py`：`admin_only_commands` 含一个**在扁平与完整路径下都不存在**的条目（如 `"totally_not_a_command"`——避免用 `"player"`，因本任务在 T6 前 LOCKABLE 仍扁平、`"player"` 此刻是合法锁）→ 该条**保留在 unknown_locks 且不静默丢**（admin_only_commands 仍含它——保留但标记）；一个合法条目（此刻扁平如 `"player"`，T8 后须改完整路径）不进 unknown_locks。**注**：真实「旧扁平 `player` 升级后变未知」场景在 T8（LOCKABLE 变完整路径）后自然成立，由 T8/收尾复核覆盖。

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_admin_only_warn_test.py -v`
Expected: FAIL

- [ ] **Step 3: _parse_permissions 校验 + unknown_locks**

`config.py` `_parse_permissions`：解析 `admin_only_commands` 时，对每条判是否属 `LOCKABLE_COMMANDS`（运行时 `from .presentation.command_registry import LOCKABLE_COMMANDS`——**函数体内相对 import 但不是绝对自导入**；确认 no_absolute_self_import 只禁绝对 `palworld_terminal...` 前缀，相对 import 合规）。未知条目**保留**（不改现有锁行为）但收集进 `PermissionsConfig.unknown_locks`。`PermissionsConfig` 加 `unknown_locks: list[str]` 字段（默认空）。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/config_admin_only_warn_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/config.py tests/unit/config_admin_only_warn_test.py
git commit -m "feat(config): admin_only_commands 未知锁条目校验+告警（防格式迁移静默失锁）"
```

---

## Task 6: command_registry —— 分发表 + PAL_REGISTERED + 完整路径常量（additive）

**Files:**
- Modify: `palworld_terminal/presentation/command_registry.py`、`palworld_terminal/config.py`(_NON_LOCKABLE 分级)
- Test: `tests/unit/command_registry_hierarchy_test.py`（新建）

**Interfaces:**
- Produces: `DISPATCH: dict[str, dict[str, ActionSpec]]`（`{组: {动作: (方法名, 功能门组, 是否管理员写)}}`）；`PAL_REGISTERED: list[str]`（11 首词）；`PAL_COMMAND_STRINGS`（完整路径集）；`_NON_LOCKABLE`（完整路径）；`LOCKABLE_COMMANDS`（=PAL_COMMAND_STRINGS − _NON_LOCKABLE）。T7/T8 消费。**本任务 additive**：定义新常量/表，**不动** command_names_test（仍锚旧 26，T8 翻新）。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/command_registry_hierarchy_test.py`：
- `PAL_REGISTERED` == `{world,guild,player,server,link,rank,online,me,help,whoami,confirm}`（11）。
- `DISPATCH` 各组子动作齐（world: status/overview/rules/events/today；guild: list/info/bases/base；player: info/bind/unbind；server: announce/save/kick/unban/ban/shutdown/stop；link: list/add/remove）。
- 完整路径：`"world status" in PAL_COMMAND_STRINGS`；`"server kick" in _NON_LOCKABLE`；`"world status" in LOCKABLE_COMMANDS`；`"rank" in PAL_COMMAND_STRINGS and "rank" in LOCKABLE_COMMANDS`（rank 可锁）。
- `config._NON_LOCKABLE == command_registry._NON_LOCKABLE`（双源全等）。
- **DISPATCH 每个方法名可 `getattr(Commands, m)`**：`for g in DISPATCH: for a,(m,_,_) in DISPATCH[g].items(): assert callable(getattr(Commands, m, None))`（T7 补齐方法后才全绿——本任务此断言可先只跑「方法名是 str」，getattr 断言标注 T7 补；或本任务把断言写上、允许该子测试到 T7 才绿并在 T8 收口。**决策**：本任务只断言表结构/常量，getattr introspection 锚定移到 T7 步骤，避免本任务红）。

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/command_registry_hierarchy_test.py -v`
Expected: FAIL

- [ ] **Step 3: 定义 DISPATCH + 常量**

`command_registry.py`：加 `ActionSpec = tuple[str, str, bool]`（方法名, 功能门组, 是否管理员写）+ `DISPATCH` 表（按 §3 命令树 + 门；写动作 is_admin_write=True 走 admin_write）+ 扁平命令表（rank/online/me/help/whoami/confirm 各自方法名+组）。`PAL_REGISTERED` = 5 组 + 6 扁平。`PAL_COMMAND_STRINGS` = 完整路径集（`f"{g} {a}"` for 组内 + 扁平名）。`_NON_LOCKABLE` = server 各动作路径 + link 各动作路径 + 元命令（help/whoami/confirm）。`LOCKABLE_COMMANDS = frozenset(PAL_COMMAND_STRINGS) - _NON_LOCKABLE`。`config.py` `_NON_LOCKABLE` 同步为同一完整路径集。**保留旧 COMMANDS/HELP_LINE/PAL_COMMAND_STRINGS 扁平定义暂不删**（T8 删）——若命名冲突，新常量用新名（如旧 `PAL_COMMAND_STRINGS` 暂重命名 `_LEGACY_...` 或本任务直接替换但保证 command_names_test 仍绿：因 command_names 锚 PAL_COMMAND_STRINGS==26 注册，若此处改成完整路径会红——**故本任务把注册锚定测试同步指向 `PAL_REGISTERED`？不行，main 仍 26**）。

  **关键排序决策**：`command_names_test::test_pal_command_strings_match_main_registrations` 现锚 `PAL_COMMAND_STRINGS`==26 注册。本任务改 `PAL_COMMAND_STRINGS` 为完整路径会**立即红**。故本任务把该测试**临时改为锚 `PAL_REGISTERED` 的补集判定或标记**——最干净：本任务同时**把 command_names 的注册锚定改为「注册串 ⊆ PAL_REGISTERED」的子集桥接**（main 仍 26 扁平，26 串 ⊄ 11 首词 → 仍红）。**结论**：注册锚定与 main.py 强耦合，无法在 T6 单独绿。**采用**：T6 只加**新常量/表 + 新测试文件**（command_registry_hierarchy_test），**不改** command_names_test、**不改**旧 PAL_COMMAND_STRINGS（新增 `PAL_COMMAND_PATHS` 完整路径常量与旧并存）；`LOCKABLE`/`_NON_LOCKABLE` 暂各留新旧（新 `_NON_LOCKABLE_PATHS`）。T8 统一改名收口 + 删旧 + 翻锚定。相应 Step 1 测试用新常量名 `PAL_COMMAND_PATHS`/`_NON_LOCKABLE_PATHS`/`DISPATCH`/`PAL_REGISTERED`。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/command_registry_hierarchy_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: PASS（旧命令/锚定不破，因新常量并存）

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/presentation/command_registry.py palworld_terminal/config.py tests/unit/command_registry_hierarchy_test.py
git commit -m "feat(registry): DISPATCH 分发表 + PAL_REGISTERED + 完整路径常量（additive）"
```

---

## Task 7: commands —— 组分发方法 + 门控下沉（additive）

**Files:**
- Modify: `palworld_terminal/presentation/commands.py`
- Test: `tests/unit/commands_dispatch_test.py`（新建）

**Interfaces:**
- Consumes: `DISPATCH`/常量（T6）、`parse_group`（T1）、`admin_denied`/`admin_write`/`_gated` 现有。
- Produces: `Commands.world/guild/player/server_grp/link(umo, message_str, is_group, sender_id, is_admin) -> str`（组分发）。**命名一致性铁律**：本任务 additive，旧扁平 `Commands.server`(server add/remove 分发) 仍在，故组方法名用 **`server_grp`**；T8 删旧 `server` 方法后**把 `server_grp` 改名为 `server`**（handler `@pal.command("server")` 调 `c.commands.server`）。其余组 `world/guild/player/link` 无旧同名方法，直接用组名。门控下沉：分发循环内 per-子动作功能门 + `admin_denied` 完整路径 + 写走 admin_write。**additive**：新方法与旧扁平方法并存。

- [ ] **Step 1: 写失败测试（门控红线）**

新建 `tests/unit/commands_dispatch_test.py`——构造 Commands（注入 fake），断言：
- `world` 分发 `status`→core 门、`events`→events 门、`today`→report 门（组关各回 feature_disabled）——**验证 per-子动作功能门**（非方法级单组）。
- `admin_denied` 下沉：锁 `"player info"`，非管理员发 `/pal player info Alice` → `admin_required` 且**不触达底层查询**。
- `server` 组写动作走 admin_write（非管理员 → admin_required，门序 admin 先于 feature）；每个写动作映射正确组（kick→basic、stop→danger）。
- 未知子动作 → 用法；缺必填参数（`/pal player info` 无名）→ 该子动作用法。
- `getattr(Commands, m)` for all DISPATCH 方法名可解析（introspection 锚定）。

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_dispatch_test.py -v`
Expected: FAIL

- [ ] **Step 3: 实现组分发 + 门控下沉**

`commands.py` 加组分发方法。核心分发骨架（以 world 为例，查询组）：

```python
    async def world(self, umo, message_str, is_group, sender_id, is_admin):
        p = parse_group(message_str, "world")
        if not p.sub:
            return self._group_help("world", is_admin)     # 裸组迷你帮助(T9 formatters)
        spec = DISPATCH["world"].get(p.sub)
        if spec is None:
            return L("world_usage")                        # 未知子动作
        method, feat_group, is_write = spec
        if not self._cfg.features.enabled(feat_group):     # per-子动作功能门(下沉)
            return L("feature_disabled")
        if self._admin_locked(f"world {p.sub}", sender_id, is_admin):  # admin_denied 完整路径(下沉)
            return L("admin_required")
        return await getattr(self, method)(umo, p.rest, is_group, sender_id)
```

`_admin_locked(path, sender, is_admin)`：`path in self._cfg.permissions.admin_only_commands and not is_admin`。`server` 组分发：写动作走 `admin_write("server "+sub 的完整路径, feat_group, ...)`（复用现有 admin_write，门序不变）；**server 组不套 `_gated`**。查询子动作的具体实现方法（`status`/`overview`/…）可复用现有扁平实现体（重命名或直接调）。`_group_help` 占位调用（T9 formatters 补齐；本任务可先返回 stub 文案，T9 替换为复用 format_help 谓词）。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_dispatch_test.py tests/unit/command_registry_hierarchy_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS（旧扁平方法仍在，既有测试不破）

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/presentation/commands.py tests/unit/commands_dispatch_test.py
git commit -m "feat(cmd): 组分发方法 + 门控下沉（功能门 per-子动作 + admin_denied 完整路径，additive）"
```

---

## Task 8: main.py 切换 —— 11 handler + 删旧 + 锚定翻新

**Files:**
- Modify: `main.py`、`palworld_terminal/presentation/commands.py`(删旧扁平方法)、`palworld_terminal/presentation/command_registry.py`(收口改名删旧)、`tests/unit/command_names_test.py`、`tests/unit/main_test.py`、`tests/unit/commands_test.py`、`tests/unit/namespace_runtime_smoke_test.py`、`tests/unit/frontend_pal_commands_test.py`
- Test: 上述迁移

**Interfaces:** 无新产出；这是**原子切换**——把注册从 26 扁平翻成 11，删旧，所有命令测试迁移到分级，锚定指向 PAL_REGISTERED。

- [ ] **Step 1: 锚定翻新（先红）**

`command_names_test.py`：`test_pal_command_strings_match_main_registrations` 改为锚 `@pal.command` 正则 == `PAL_REGISTERED`（11）；加 DISPATCH getattr introspection 锚定；`test_non_lockable_matches_registry_complement` 用完整路径 `_NON_LOCKABLE`。`command_registry.py` 收口：删旧扁平 `COMMANDS`/`HELP_LINE`/`PAL_COMMAND_STRINGS`/`_NON_LOCKABLE`，把 T6 的 `PAL_COMMAND_PATHS`/`_NON_LOCKABLE_PATHS` 改名为正式 `PAL_COMMAND_STRINGS`/`_NON_LOCKABLE`（config.py 同步）。此刻 main 仍 26 → 锚定红。

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/command_names_test.py -v`
Expected: FAIL（26 注册 ≠ 11 PAL_REGISTERED）

- [ ] **Step 3: main.py 翻 11 handler**

`main.py`：删 26 个旧扁平 `@pal.command`；加 5 组 handler（world/guild/player/server/link）+ 6 扁平（rank/online/me/whoami/help/confirm）。组 handler 照现有 server handler 范式，走 busy/inflight 门（`_guarded` 或拆出的只做门闩的包裹），传 `sender_id` + `is_admin`：

```python
    @pal.command("world")
    async def world(self, event):
        yield event.plain_result(await self._guarded(lambda c: c.commands.world(
            self._umo(event), self._msg(event), self._is_group(event),
            self._sender_id(event), c.commands.is_plugin_admin(self._sender_id(event)))))
```

（`server` 组因含写命令，仍须过 busy/inflight，但写门在 admin_write 内——用 `_guarded` 门闩即可，admin_denied 已下沉 Commands。`link` handler T9 加单模式守卫。）删 `commands.py` 旧扁平方法（status/world/rules/... 的旧 handler 方法），保留被组分发调用的实现体。

- [ ] **Step 4: 迁移破裂测试**

`main_test.py`/`commands_test.py`/`namespace_runtime_smoke_test.py`（calls 改分组形 `(plugin.world,"world status")`，命令数更新）/`frontend_pal_commands_test.py`（锚完整路径，与前端 T10 呼应——本任务先按后端 LOCKABLE 完整路径改断言，前端值 T10 补齐；若跨端此刻不匹配，本任务标注该测试待 T10，或本任务同步改前端 PAL_COMMANDS 值）。**决策**：为保持每任务绿，本任务同步把 `frontend/src/lib/schema.ts` 的 `PAL_COMMANDS` 值改完整路径（前端渲染 T10 再定稿，此处仅同步锚定值）。

- [ ] **Step 5: 运行确认通过 + 全套 + mypy**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/command_names_test.py tests/unit/main_test.py tests/unit/namespace_runtime_smoke_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/ && cd frontend && npm run test:run && cd ..`
Expected: PASS（分级命令锚定绿；前端跨端锚定绿）

- [ ] **Step 6: 提交**

```bash
git add main.py palworld_terminal/presentation/commands.py palworld_terminal/presentation/command_registry.py palworld_terminal/config.py frontend/src/lib/schema.ts tests/unit/
git commit -m "feat(main): 26 扁平命令切换为 11 分级 handler + 删旧 + 锚定翻新"
```

---

## Task 9: formatters —— 分级 help + 裸组迷你帮助 + link 单模式守卫

**Files:**
- Modify: `palworld_terminal/presentation/formatters.py`、`palworld_terminal/presentation/commands.py`(_group_help 复用谓词)、`main.py`(link handler 单模式守卫)、`palworld_terminal/presentation/locale.py`
- Test: `tests/unit/formatters_hierarchy_test.py`（新建）、`tests/unit/main_link_single_test.py`（新建）

**Interfaces:** 无新产出；help 分级化 + 裸组迷你帮助复用同一谓词 + link 单模式运行时拒 + **暴露告警**（`single_restricted_warning` T3 + `unknown_locks` T5 在 initialize 经 logger 输出，spec §5/§7 要求）。

- [ ] **Step 1: 写失败测试**

`formatters_hierarchy_test.py`：`format_help` 分级视图（组 + 子动作，按功能门 + 角色过滤）；**guest 发 `/pal server` 裸组帮助不含 kick/ban/stop**；guilds_bases 关时 `/pal guild` 不列子动作；confirm 仅管理员见；单模式 help 省略 link 组。`main_link_single_test.py`：single 模式 `/pal link add alpha` → 回「单世界模式无需选择服务器」且**不触达 routing.use**（fake 断言 use 未被调）。**告警暴露测试**：single+restricted 配置下 initialize 后 `single_restricted_warning` 非 None 被 logger 记（可断言 caplog 含关键短语）；`unknown_locks` 非空时同样记一条。

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/formatters_hierarchy_test.py tests/unit/main_link_single_test.py -v`
Expected: FAIL

- [ ] **Step 3: format_help 分级 + _group_help 复用 + link 守卫**

`formatters.py` `format_help` 重写为分级：遍历 DISPATCH 组 + 子动作，按 `features.enabled(组)` + is_admin（写动作/confirm 须 is_admin）过滤；单模式省略 link 组。抽一个**过滤谓词函数** `visible_actions(group, is_admin, features, world_mode)` 作单一真相源，`_group_help`（T7 的裸组迷你帮助）**复用它**。`commands.py` `_group_help` 改为调该谓词生成迷你帮助。`main.py` link handler 顶部（先于 Commands.link 调用或在 Commands.link 内最前）判 `world_mode=="single"` → 回提示，不调 use/revoke。

**告警暴露**（spec §5/§7）：`main.py` 的 `initialize`（容器装配后）经 `logger` 输出两条告警——`self._container.routing.single_restricted_warning()`（非 None 则 warning）+ `permissions.unknown_locks`（非空则 warning「以下 admin_only_commands 条目不是合法命令路径、锁未生效：...」）。先读 main.py `initialize` 现有 logger 用法对齐。

- [ ] **Step 4: 运行确认通过 + 源码红线 + 回归**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/formatters_hierarchy_test.py tests/unit/main_link_single_test.py tests/unit/formatters_admin_help_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add palworld_terminal/presentation/formatters.py palworld_terminal/presentation/commands.py main.py palworld_terminal/presentation/locale.py tests/unit/formatters_hierarchy_test.py tests/unit/main_link_single_test.py
git commit -m "feat(help): 分级 help + 裸组迷你帮助复用谓词 + link 单模式守卫"
```

---

## Task 10: 前端 —— world_mode enum + PAL_COMMANDS 完整路径 + 产物

**Files:**
- Modify: `frontend/src/lib/schema.ts`、`frontend/src/components/SettingsPanel.vue`、`frontend/src/lib/chapters.ts`、`pages/settings/`
- Test: `frontend/src/**/*.test.ts`（扩）

**Interfaces:** routing 章加 world_mode enum 字段；PAL_COMMANDS 完整路径（T8 已改值，本任务定稿渲染 + build）。

- [ ] **Step 1: 写失败测试（vitest）**

routing ObjectSection 含 `world_mode` enum 字段（options multi/single）；SettingsPanel 连接章渲染该单选；PAL_COMMANDS 为完整路径集（若 T8 已改，此为守护测试）。

- [ ] **Step 2: 运行确认失败** `cd frontend && npm run test:run && cd ..`

- [ ] **Step 3: 实现**

`schema.ts` routing 的 `ObjectSection.fields` 加 `world_mode`（`type:'enum', options:['multi','single'], default:'multi'`，label「运行模式」，hint 含单模式访问告警）。SettingsPanel 连接章自动渲染（数据驱动，照现有 enum 字段如 access_mode）。确认 PAL_COMMANDS 完整路径值正确。**不得用 v-html**。

- [ ] **Step 4: 前端全测 + typecheck + 源码红线**

Run: `cd frontend && npm run test:run && npm run typecheck && cd .. && ./.venv/Scripts/python.exe -m pytest tests/unit/frontend_source_test.py -v`
Expected: PASS

- [ ] **Step 5: 重建产物 + verify-bundle + no-drift**

Run: `cd frontend && npm run build && cd .. && node frontend/scripts/verify-bundle.mjs && git add pages/settings && git status --short pages/settings`
Expected: 产物变更、单 JS

- [ ] **Step 6: 全套回归 + 提交**

Run: `./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
```bash
git add frontend/src/lib/schema.ts frontend/src/components/SettingsPanel.vue frontend/src/lib/chapters.ts frontend/src/**/*.test.ts pages/settings
git commit -m "feat(fe): routing world_mode enum + PAL_COMMANDS 完整路径 + 产物"
```

---

## Task 11: 文档 + 锁迁移映射表 + 版本 v0.9.5

**Files:**
- Modify: `docs/commands.md`、`docs/configuration.md`、`README.md`、`tests/unit/readme_test.py`、`metadata.yaml`、`main.py`、`palworld_terminal/__init__.py`、`tests/unit/phase1_smoke_test.py`、`tests/unit/skeleton_test.py`

**Interfaces:** 无。

- [ ] **Step 1: readme_test 锚点 + 版本断言（先红）**

`readme_test.py`：命令锚点从 `/pal status` 等改分级 `/pal world status` 等；加 `world_mode`/`单世界`/`受控写`（若变）等锚点。`phase1_smoke_test.py`/`skeleton_test.py`：版本 `0.9.0`→`0.9.5`。

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py tests/unit/phase1_smoke_test.py tests/unit/skeleton_test.py -v`
Expected: FAIL

- [ ] **Step 3: 文档重写**

- `docs/commands.md`：全命令表改分级（5 组 + 6 扁平 + 子动作）；rank 变体 today/total/level；**flat→full-path 锁迁移映射表**（`player`→`player info`、`status`→`world status`… + 「不迁移=失锁」告警）；单模式说明。
- `docs/configuration.md`：`world_mode`(routing) + **单模式×restricted 访问告警粗体** + admin_only_commands 值格式（完整路径）。
- `README.md`：命令示例改分级；命令计数更新；版本徽章 v0.9.5；单模式一句话。

- [ ] **Step 4: 版本四源**

`metadata.yaml` v0.9.5；`main.py @register` 版本 + 描述（分级/命令数）；`__init__.py __version__="0.9.5"`；README 徽章。先 grep 每处实际串。

- [ ] **Step 5: 运行确认通过 + grep 无残留 + 全套**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py tests/unit/phase1_smoke_test.py tests/unit/skeleton_test.py -v && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: PASS（grep 无 `0.9.0` 版本源残留、无旧扁平命令示例残留）

- [ ] **Step 6: 提交**

```bash
git add docs/commands.md docs/configuration.md README.md tests/unit/readme_test.py metadata.yaml main.py palworld_terminal/__init__.py tests/unit/phase1_smoke_test.py tests/unit/skeleton_test.py
git commit -m "docs+chore: 分级命令文档 + 锁迁移映射表 + 单模式告警 + 版本 v0.9.5"
```

---

## 收尾：整体验证

- [ ] **全套 + lint + mypy + 前端 + no-drift**

Run:
```bash
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m mypy palworld_terminal/
cd frontend && npm run test:run && npm run build && cd ..
node frontend/scripts/verify-bundle.mjs
git diff --exit-code -- pages/settings
```
Expected: 全绿；no-drift 无差异。

- [ ] **安全/锚定关键路径单独复核**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/commands_dispatch_test.py tests/unit/command_names_test.py tests/unit/command_registry_hierarchy_test.py tests/unit/routing_world_mode_test.py tests/unit/rank_total_test.py tests/unit/formatters_hierarchy_test.py tests/unit/config_admin_only_warn_test.py tests/unit/no_absolute_self_import_test.py -v`
Expected: PASS —— 门控下沉 fail-open 防回归、锚定分家、单模式、rank total 隐私、裸组角色隔离、锁迁移告警。
