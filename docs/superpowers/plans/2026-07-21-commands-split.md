# 拆分 commands.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 953 行的 `presentation/commands.py`（`Commands` god 对象）按职责拆成协调器 + 两焦点单元（ReadCommands 查询 handler、AdminWriteFlow 写安全心脏）+ 避环支撑模块，零运行时行为/输出字节变化。

**Architecture:** 新增 `command_support.py`（跨单元共享模块 helper，避免导入环）、`read_commands.py`（ReadCommands）、`admin_write_flow.py`（AdminWriteFlow）；`Commands` 瘦身为协调器（分发/门控/link/meta/gating）+ 门面委派 stub。**方法体逐字搬迁不改逻辑**；`Commands.__init__` 内部构造两子对象（container.py 不变）；分发/server_grp/link 的 `getattr(self,…)`/`self.admin_write` 反射目标**保持 `self`**（命中委派 stub，保 monkeypatch 语义）。golden `.txt` + 全量 1194 是安全网。

**Tech Stack:** Python 3.13、pytest、ruff、mypy。

## Global Constraints

- **零字节变化**：全部 golden `*_golden_test.py` 的 `.txt` 输出字节不变（最终裁判）。
- **零行为/逻辑变化**：方法体、门控、门序、隐私逻辑**逐字搬迁**，只换文件位置 + 机械替换（`self._world_mode()`→`_world_mode(self._cfg)` 等）。
- **门面保面**：`main.py` / `container.py` 对 Commands 的调用契约**零改动**；委派 stub 保住外部直调面。
- **反射目标铁律**：`_dispatch_read` 的 `getattr(self, method)`、`server_grp` 的 `self.admin_write(...)`、`link` 的 `getattr(self, method)`/`self.link_list`——**保持 `self` 一字不改**。改指 `self._reads`/`self._writes` = 静默行为变化，禁止。
- **无导入环**：共享 helper 下沉 `command_support`；`command_support` 绝不 import commands/read_commands/admin_write_flow。
- **ruff 门跑 `ruff check .`（全仓含 tests）**；三新文件须被 `no_absolute_self_import_test`（rglob）覆盖。
- 相对 import；AstrBot 命名空间安全（无绝对自导入）。
- commit 无 Claude / Co-Authored-By；不 bump 版本。
- 分支 `feat/commands-split`（栈于 feat/presentation-decoupling @0c1c78b；spec 已提交 c88f2b5）。

---

## File Structure

**Create:**
- `palworld_terminal/presentation/command_support.py` — 跨单元共享模块 helper
- `palworld_terminal/presentation/read_commands.py` — `class ReadCommands`
- `palworld_terminal/presentation/admin_write_flow.py` — `class AdminWriteFlow`

**Modify:**
- `palworld_terminal/presentation/commands.py` — 瘦身为协调器 + 门面委派
- 5 个测试文件（`_resolve_world` patch 测点改指 `c._reads`）：`commands_me_bind_test.py`、`commands_player_test.py`、`commands_rank_test.py`、`commands_guild_test.py`、`rank_total_test.py`

**依赖 DAG（无环）**：`commands → {read_commands, admin_write_flow, command_support}`；`read_commands → command_support`；`admin_write_flow → command_support`；`command_support → {shared.command_registry, application.command_permissions, application.routing_service, presentation.locale}`。

---

## Task 1: command_support.py（避环共享模块 helper）

**Files:**
- Create: `palworld_terminal/presentation/command_support.py`
- Modify: `palworld_terminal/presentation/commands.py`（删移出的 defs、import command_support、改 _world_mode/_fold_limit 调用点）

**Interfaces:**
- Produces（command_support 导出）：`feature_disabled_text(path)`、`_gated(fn)`、`_render_routing_error(err, params)`、`_world_mode(cfg) -> str`、`_fold_limit(cfg) -> int`、`_SENDER_METHODS: frozenset`

- [ ] **Step 1: 建 command_support.py，搬入 5 helper + 2 常量方法转函数**

新建 `palworld_terminal/presentation/command_support.py`。从 commands.py **逐字搬入**（含 docstring）：
- 模块函数 `feature_disabled_text`（当前 commands.py:45-55）、`_gated`（99-110）、`_render_routing_error`（58-65）。
- 模块常量 `_SENDER_METHODS = frozenset({"bind","me","unbind_self"})`（当前 115）。
- **方法转模块函数**：把 `Commands._world_mode`（当前 455-457）、`Commands._fold_limit`（当前 180-186）改写为模块函数——去掉 `self`，签名 `def _world_mode(cfg) -> str:` / `def _fold_limit(cfg) -> int:`，函数体把 `self._cfg` 改为 `cfg`（逻辑逐字不变）：
```python
def _world_mode(cfg) -> str:
    """真实 AppConfig 恒有 routing.world_mode；默认 multi 兼容不完整测试替身。"""
    return getattr(getattr(cfg, "routing", None), "world_mode", "multi")


def _fold_limit(cfg) -> int:
    """列表折叠上限（spec §2.7）：全部列表 formatter 共用 cfg.players.list_fold_limit
    单一真相源；测试替身缺 cfg/players 时回默认 7。"""
    if cfg is None:
        return 7
    return getattr(getattr(cfg, "players", None), "list_fold_limit", 7)
```
command_support.py 顶部 import：
```python
from __future__ import annotations

import functools

from ..application.command_permissions import effective_enabled, upstream_unavailable
from ..application.routing_service import RoutingError
from ..presentation.locale import L
from ..shared.command_registry import METHOD_PATH
```
（`_gated` 用 functools/METHOD_PATH/effective_enabled；`feature_disabled_text` 用 upstream_unavailable/L；`_render_routing_error` 用 RoutingError/L。以搬入函数实际引用为准增删。）

- [ ] **Step 2: commands.py 改为 import + 删除移出的 defs + 改调用点**

`commands.py`：
- 删除已移出的 `feature_disabled_text`/`_gated`/`_render_routing_error`（模块函数）、`_SENDER_METHODS`（常量）、`Commands._world_mode`/`Commands._fold_limit`（方法）。
- 顶部加：`from .command_support import (feature_disabled_text, _gated, _render_routing_error, _world_mode, _fold_limit, _SENDER_METHODS)`。
- 改所有 `self._world_mode()` → `_world_mode(self._cfg)`（8 处：当前行 353/360/397/414/425/464/631/654）。
- 改所有 `self._fold_limit()` → `_fold_limit(self._cfg)`（当前行 596 link_list + 读区 handler 内各处——grep `_fold_limit(` 全量替换）。
- `_render_routing_error(...)` 调用点不变（现从 command_support import）。

- [ ] **Step 3: 跑测试**

Run: `( py -m pytest -q ) && ruff check . && ( py -m mypy palworld_terminal )`
Expected: 全 PASS（纯 helper 外移 + 2 方法→函数 + 调用点替换，逻辑零改）。golden 字节不变。若 ruff I001，`ruff check . --fix`（纯 import 重排）。

- [ ] **Step 4: 咬合自证（可选但推荐）**

确认 `_gated` 从 command_support import 后仍生效：跑 gating 测试 `( py -m pytest tests/unit/commands_gating_test.py -q )` 全绿。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: 抽 command_support 共享模块 helper（_world_mode/_fold_limit 方法转函数）"
```

---

## Task 2: read_commands.py（ReadCommands + 门面委派 + 改 5 处测点）

**Files:**
- Create: `palworld_terminal/presentation/read_commands.py`
- Modify: `commands.py`（建 self._reads、加委派 stub、删移出方法体）、5 个测试文件（改 _resolve_world patch 测点）

**Interfaces:**
- Consumes: command_support（`_gated`/`_world_mode`/`_fold_limit`/`_render_routing_error`）
- Produces: `class ReadCommands(routing, query, repo, cfg, clock, salt=b"")`，方法 `_resolve_world`/`handle_query`/`_guilds_bases_on`/`_is_strict`/`_server_anchor`/status/online/world/rules/guilds/guild/bases/base/events/today/rank/player/bind/me/unbind_self

- [ ] **Step 1: 建 read_commands.py（ReadCommands），逐字搬入读方法**

新建 `palworld_terminal/presentation/read_commands.py`：
```python
from __future__ import annotations

# 从 commands.py 现有 import 中，读方法体实际用到的原样搬来（parse_arg/ArgError、
# format_* formatters、DISPATCH? 不用、metric_stale/server_timezone、EndpointName/
# AccessMode、application.dtos、hash_user_id 等——以移入方法体实际引用为准）
from .command_support import _fold_limit, _gated, _render_routing_error, _world_mode
... （其余 import 照搬 commands.py 顶部中被读方法用到的项）


class ReadCommands:
    def __init__(self, routing, query, repo, cfg, clock, salt: bytes = b"") -> None:
        self._routing = routing
        self._query = query
        self._repo = repo
        self._cfg = cfg
        self._clock = clock
        self._salt = salt
```
**逐字搬入**（含 `@_gated` 装饰器、注释、措辞）以下方法（当前 commands.py 行号）：`_resolve_world`(132)、`handle_query`(154)、`_guilds_bases_on`(166)、`_is_strict`(174)、`_server_anchor`(357)、status(188)、online(200)、world(213)、rules(224)、guilds(234)、guild(248)、bases(266)、base(280)、events(295)、today(312)、rank(323)、player(340)、bind(363)、me(391)、unbind_self(419)。
- 方法体内 `self._world_mode()`/`self._fold_limit()` 已在 Task 1 改为 `_world_mode(self._cfg)`/`_fold_limit(self._cfg)`——搬来时保持该形态（ReadCommands 有 self._cfg）。
- `@_gated` 从 command_support import，逐字保留。

- [ ] **Step 2: commands.py 建 self._reads + 加读委派 stub + 删移出方法体**

`commands.py`：
- 顶部加 `from .read_commands import ReadCommands`。
- `Commands.__init__` 末尾加：`self._reads = ReadCommands(routing, query, repo, cfg, clock, salt)`（`routing/query/repo/cfg/clock/salt` 均为 __init__ 现有参数）。
- **删除**上述 21 个已搬方法的**方法体**。
- **加委派 stub**（1 行/个，签名与原方法逐字一致），覆盖被外部直调/反射命中者——`_resolve_world`、`handle_query`、status、online、world、rules、guilds、guild、bases、base、events、today、rank、player、bind、me、unbind_self（`_guilds_bases_on`/`_is_strict`/`_server_anchor` 仅 ReadCommands 内部用，**不 stub**）。示例：
```python
async def status(self, umo, message_str, is_group) -> str:
    return await self._reads.status(umo, message_str, is_group)

async def rank(self, umo, message_str, is_group) -> str:
    return await self._reads.rank(umo, message_str, is_group)

async def bind(self, umo, message_str, is_group, sender_id) -> str:
    return await self._reads.bind(umo, message_str, is_group, sender_id)

async def _resolve_world(self, umo, message_str, subcommand, is_group):
    return await self._reads._resolve_world(umo, message_str, subcommand, is_group)

async def handle_query(self, *a, **k):
    return await self._reads.handle_query(*a, **k)
```
（bind/me/unbind_self 带 sender_id；me 签名 `(umo, message_str, is_group, sender_id)`；handle_query 参数以原签名为准，或用 `*a, **k` 透传。）
- **`_dispatch_read` 的 `getattr(self, method)` 一字不改**——它命中委派 stub（stub 委派 self._reads；被 monkeypatch 时用 patch）。

- [ ] **Step 3: 改 5 个测试文件的 _resolve_world patch 测点（对抗复核 Blocker）**

读 handler 迁 ReadCommands 后，其内部 `self._resolve_world` 的 patch seam 迁到 `c._reads`。把下列 5 文件的 `c._resolve_world = _rw`（或 `<var>._resolve_world = ...`）改为 `c._reads._resolve_world = _rw`：
- `tests/unit/commands_me_bind_test.py`（约 :45）
- `tests/unit/commands_player_test.py`（约 :36）
- `tests/unit/commands_rank_test.py`（约 :23）
- `tests/unit/commands_guild_test.py`（约 :63）
- `tests/unit/rank_total_test.py`（约 :133）

以各文件实际 patch 赋值行为准（grep `._resolve_world =` 定位）。仅改 patch 目标对象（`c` → `c._reads`），赋的替身函数不变。

- [ ] **Step 4: 跑测试**

Run: `( py -m pytest -q ) && ruff check . && ( py -m mypy palworld_terminal )`
Expected: 全 PASS。**特别确认**：
- `commands_dispatch_test`（patch `c.admin_write`/`c.bind` 经 dispatch）仍绿——证反射目标保持 self、monkeypatch 存活。
- 5 个改测点的文件绿——证 patch 迁 c._reads 后读 handler 内部 self._resolve_world 命中 patch。
- golden 字节不变。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: 抽 ReadCommands（查询 handler）+ 门面委派 + 迁 5 处 _resolve_world patch 测点"
```

---

## Task 3: admin_write_flow.py（AdminWriteFlow 写安全心脏）+ 收尾

**Files:**
- Create: `palworld_terminal/presentation/admin_write_flow.py`
- Modify: `commands.py`（建 self._writes、加写委派 stub、删移出方法体）

**Interfaces:**
- Consumes: command_support（`_render_routing_error` 等，以实际引用为准）
- Produces: `class AdminWriteFlow(admin_service, routing, confirmations, cfg, clock)`，方法 `admin_write`/`confirm`/`_store_pending`/`_pending_phrase`/`_render_result`/`_render_admin_ok`/`clear_pending`

- [ ] **Step 1: 建 admin_write_flow.py（AdminWriteFlow），逐字搬入写方法 + admin 常量/函数**

新建 `palworld_terminal/presentation/admin_write_flow.py`：
```python
from __future__ import annotations

# 照搬 commands.py 顶部中写方法体实际用到的 import（PendingAction、L、
# _render_routing_error[from command_support]、application 相关等——以实际引用为准）


_SHUTDOWN_MAX_SECONDS = ...   # 逐字搬自 commands.py:42
_ACTION_LABEL = { ... }        # 逐字搬自 commands.py:77-85


def _parse_shutdown_seconds(token):   # 逐字搬自 commands.py:67-86
    ...


def _target_phrase(name, userid):     # 逐字搬自 commands.py:88-97
    ...


class AdminWriteFlow:
    def __init__(self, admin_service, routing, confirmations, cfg, clock) -> None:
        self._admin = admin_service
        self._routing = routing
        self._confirmations = confirmations
        self._cfg = cfg
        self._clock = clock
```
**逐字搬入**方法（当前 commands.py 行）：`admin_write`(675)、`_pending_phrase`(791)、`_store_pending`(805)、`confirm`(820)、`_render_result`(871)、`_render_admin_ok`(906)、`clear_pending`(941)。
- 这些方法体内部互调（admin_write→self._store_pending/self._render_result；confirm→self._render_result 等）**保持 self**（同类内，AdminWriteFlow 自持）——逐字不变。
- `_SHUTDOWN_MAX_SECONDS`/`_ACTION_LABEL`/`_parse_shutdown_seconds`/`_target_phrase` 是 admin 专用模块级，一并搬入（漏则 NameError）。

- [ ] **Step 2: commands.py 建 self._writes + 加写委派 stub + 删移出方法体 + 删 admin 模块级**

`commands.py`：
- 顶部加 `from .admin_write_flow import AdminWriteFlow`。删除已移出的 admin 模块级 `_SHUTDOWN_MAX_SECONDS`/`_ACTION_LABEL`/`_parse_shutdown_seconds`/`_target_phrase`。
- `Commands.__init__` 末尾加：`self._writes = AdminWriteFlow(admin_service, routing, confirmations, cfg, clock)`（`admin_service/confirmations` 为 __init__ 现有参数）。
- **删除** admin_write/_pending_phrase/_store_pending/confirm/_render_result/_render_admin_ok/clear_pending 的**方法体**。
- **加委派 stub**：
```python
async def admin_write(self, **kwargs):
    return await self._writes.admin_write(**kwargs)

async def confirm(self, admin_id, umo, is_group, is_admin) -> str:
    return await self._writes.confirm(admin_id, umo, is_group, is_admin)

def clear_pending(self) -> None:
    self._writes.clear_pending()
```
（admin_write 现有调用方 server_grp 用关键字参数 `command_str=/group=/admin_id=/umo=/is_group=/arg_str=/is_admin=`；测试直调也多用 kwargs——stub 用 `**kwargs` 透传最稳，或照 admin_write 原签名逐字复制。以原签名为准。）
- **`server_grp` 的 `self.admin_write(...)` 一字不改**（命中委派 stub，保 patch 语义）。

- [ ] **Step 3: 收尾核对**

- commands.py 现应净剩：协调器（_dispatch_read/world_grp/guild_grp/player_grp/server_grp/_admin_locked/_group_help/_rebuild_arg）+ link（link/link_list/link_add/link_remove/_server_reachable）+ meta（help/whoami/whereami）+ gating（is_plugin_admin/admin_denied）+ 门面委派 stub（reads 17 + writes 3）+ __init__。目标 ~350 行。
- 核实三新文件被绝对自导入守卫覆盖：`( py -m pytest tests/unit/no_absolute_self_import_test.py -q )` 绿（rglob 自动含新文件）。
- 核实无导入环：mypy 绿即无环；另可 `( py -m pytest tests/unit/namespace_runtime_smoke_test.py -q )` 绿（相对导入链拉起）。

- [ ] **Step 4: 全量终验**

Run: `( py -m pytest -q ) && ruff check . && ( py -m mypy palworld_terminal )`
Expected: 全 PASS（1194 passed/1 skipped 量级）。**特别确认**：
- `commands_admin_write_test`（52 处 admin_write + 门序 + 字节 + admin_resolve_failed 嵌套回归）全绿——证写编排搬迁零行为变化。
- `commands_dispatch_test`（patch c.admin_write 经 server_grp）绿——证反射保 patch。
- golden `.txt` 字节不变（`git diff --stat <task2-head> HEAD -- tests/golden/` 为空）。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: 抽 AdminWriteFlow（写安全心脏隔离）+ 门面委派；commands.py 净剩协调器"
```

---

## Self-Review 备忘（已核对 spec 覆盖）
- §4 command_support → Task 1；§5 ReadCommands → Task 2；§6 AdminWriteFlow → Task 3；§7 门面委派 + 反射保 self → Task 2/3 各自 stub；§7.1 monkeypatch Blocker（5 处改测点）→ Task 2 Step 3；§8 约束贯穿 Global Constraints。
- 验收 §11：commands.py ~350 行（T3 Step 3）、golden 字节（各任务 + T3 Step 4）、main.py/container 零改（全程不碰）、无环+守卫覆盖（T3 Step 3）、门控/门序逐字未改（逐字搬迁）、反射保 self（T2/T3）。
- 每相独立可跑独立绿：Task 1（helper 外移）、Task 2（读抽离，golden+dispatch/patch 测试兜底）、Task 3（写抽离，commands_admin_write_test 兜底）。
