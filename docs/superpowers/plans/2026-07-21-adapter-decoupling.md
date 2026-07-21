# 适配器解耦 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 application 层对 adapters 层的 12 处反向依赖：纯逻辑/契约迁到中立层（domain/shared），有状态 Repository 依赖抽象为 Protocol 端口（adapter 结构化满足）。零运行时行为/输出字节变化。

**Architecture:** privacy_filter→domain/privacy.py（+PrivacyConfig 迁 domain 解 config 环）；RestResponse→shared/rest.py；_ADMIN_PATH→domain.enums.ADMIN_ACTIONS；normalize_players 注入 AdminService；application/ports.py 定义 ReadRepositoryPort/WriteRepositoryPort/RoutingRepositoryPort/AuditRepositoryPort，5 service 重标注（Repository 结构化满足经 mypy 校验）。golden `.txt` + 全量 1194 是安全网。

**Tech Stack:** Python 3.13、pytest、ruff、mypy、typing.Protocol。

## Global Constraints

- **零字节变化**：全部 golden `*_golden_test.py` 的 `.txt` 输出字节不变。
- **零行为变化**：纯迁移/重标注/注入，逻辑逐字不改。
- **re-export 不变量（铁律）**：①config.py 迁移后须模块级 `from .domain.privacy import PrivacyConfig`（供 AppConfig.privacy 注解 + 构造），保 `config.PrivacyConfig` 供 ~28 测试零改——**不得挪进函数局部**；②palworld_rest 须 `from ..shared.rest import RestResponse`（供构造），保 `palworld_rest.RestResponse` 供旧路径零改。
- **注入必填无默认**：normalize_players 必填、无 adapter 默认值（默认会引回 adapters import）。
- 全绿门：`( py -m pytest -q )` + `ruff check .`（**全仓含 tests**）+ `mypy palworld_terminal` 全绿。
- 相对 import；AstrBot 命名空间安全（新文件相对 import、无绝对自导入，rglob 守卫自动覆盖）。
- commit 无 Claude / Co-Authored-By；不 bump 版本。用 `py -m pytest`（`python` 撞 Windows Store 别名）。行尾敏感：用 Edit 不用 `sed -i`。
- 分支 `feat/adapter-decoupling`（栈于 feat/commands-split @6c20b23；spec 已提交 1f8b661）。

---

## File Structure

**Create:** `domain/privacy.py`、`shared/rest.py`、`application/ports.py`、`tests/unit/adapter_layering_guard_test.py`
**Delete:** `adapters/privacy_filter.py`（迁 domain 后，不留 shim）
**Modify:** `application/{admin,base,guild,player,query,report,routing,event,snapshot}_service.py`、`application/name_resolver.py`、`presentation/read_commands.py`、`adapters/palworld_rest.py`、`infrastructure/scheduler.py`、`config.py`、`container.py`、`domain/enums.py` + 测试若干（各 Task 内列）

---

## Task 1: privacy_filter → domain/privacy.py（+ PrivacyConfig 迁 domain）

**Files:**
- Create: `palworld_terminal/domain/privacy.py`
- Delete: `palworld_terminal/adapters/privacy_filter.py`
- Modify: `config.py`（PrivacyConfig 迁出 + re-export）、`application/{admin,base,guild,player}_service.py`、`presentation/read_commands.py`、`container.py`（_privacy_mod 模块注入）、~12 测试文件

**Interfaces:**
- Produces: `domain/privacy.py` 导出 `PrivacyConfig`（dataclass，从 config 迁来）+ `hash_user_id`/`bucketize_ping`/`quantize_cell`/`_hash_or_none`/`redact_players`/`redact_game_data`（从 privacy_filter 迁来）

- [ ] **Step 1: 建 domain/privacy.py（搬入函数 + PrivacyConfig）**

`git mv palworld_terminal/adapters/privacy_filter.py palworld_terminal/domain/privacy.py`。然后编辑 `domain/privacy.py`：
- 把 `class PrivacyConfig`（当前 config.py:112 处的整块 dataclass 定义）**剪切搬入** domain/privacy.py 顶部（在函数之前）。
- 改 import：删 `from ..config import PrivacyConfig`（现在本文件定义它）；`from ..domain.enums import PingBucket` → `from .enums import PingBucket`（同 domain 包相对）；`from ..domain.models import (...)` → `from .models import (...)`。确认 domain/privacy 只依赖 domain 内部（enums/models）+ stdlib（hmac/math/hashlib）——无 config/application 依赖。

- [ ] **Step 2: config.py 迁出 PrivacyConfig + 保 re-export 不变量**

`config.py`：
- 删除 `class PrivacyConfig`（原 :112 整块）。
- **顶部加模块级 `from .domain.privacy import PrivacyConfig`**（供 `AppConfig.privacy` 字段注解[原 :220] + `PrivacyConfig(...)` 构造[原 :501]）——此 import **在模块顶层**，使 `from palworld_terminal.config import PrivacyConfig` re-export 自动保住（~28 测试零改）。**铁律：不得挪进函数局部**。
- 其余（:220 注解、:501 构造）不变（名字现从 re-export 解析）。

- [ ] **Step 3: 重指生产代码消费者**

- `application/{admin,base,guild,player}_service.py`：`from ..adapters.privacy_filter import ...` → `from ..domain.privacy import ...`（导入名不变）。
- `presentation/read_commands.py`：`from ..adapters.privacy_filter import ...` → `from ..domain.privacy import ...`。
- `container.py`：`_privacy_mod` 是**模块整体注入**给 SnapshotService——原 `from .adapters import privacy_filter as _privacy_mod`（或 `from .adapters.privacy_filter import ...`，以实际为准，约 :9）→ `from .domain import privacy as _privacy_mod`。用法（约 :129 传给 SnapshotService）不变。

- [ ] **Step 4: 重指 ~12 测试文件（grep 全量为准）**

Run: `grep -rn "adapters.privacy_filter\|adapters import privacy_filter" tests/`
对每个命中改：`from palworld_terminal.adapters.privacy_filter import ...` → `from palworld_terminal.domain.privacy import ...`；`from palworld_terminal.adapters import privacy_filter as X` → `from palworld_terminal.domain import privacy as X`。已知约 12 文件：`privacy_filter_{primitives,players,game_data}_test`（直接 import 函数）+ `cache_wiring`/`player_uncertain`/`pipeline`（集成，模块注入）+ `snapshot_{game_data_guard,ingest_guard,service_metrics,service_delegation,service_info,service_settings}_test`（单测，模块注入）。**以 grep 结果为准，别漏**。

- [ ] **Step 5: 跑测试**

Run: `( py -m pytest -q ) && ruff check . && ( py -m mypy palworld_terminal )`
Expected: 全 PASS。**特别确认**：无 `adapters.privacy_filter` 残留（`grep -rn "adapters.privacy_filter" palworld_terminal tests` 应仅 docs）；`from palworld_terminal.config import PrivacyConfig` 仍可解析（~28 测试绿）；golden 字节不变；无导入环（mypy 绿）。若 ruff I001 用 `ruff check . --fix`。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: privacy_filter 迁 domain/privacy + PrivacyConfig 迁 domain（解 config 环，config re-export 保面）"
```

---

## Task 2: RestResponse → shared/rest.py

**Files:**
- Create: `palworld_terminal/shared/rest.py`
- Modify: `adapters/palworld_rest.py`、`application/{admin,snapshot}_service.py`、`infrastructure/scheduler.py`、`container.py`

**Interfaces:**
- Produces: `shared/rest.py` 导出 `RestResponse`（dataclass，从 palworld_rest 迁来）

- [ ] **Step 1: 建 shared/rest.py（RestResponse 搬入）**

新建 `palworld_terminal/shared/rest.py`：
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RestResponse:
    ok: bool
    status: int | None
    data: Any | None
    duration_ms: int
    payload_bytes: int
    error: str | None  # 已脱敏：不含凭证/URL/host
```
（逐字复制自 palworld_rest.py:28-34；仅需 dataclass + Any，零重依赖、叶子。）

- [ ] **Step 2: palworld_rest 删定义 + re-export（不变量）**

`adapters/palworld_rest.py`：删除 `@dataclass class RestResponse`（28-34）；顶部加 `from ..shared.rest import RestResponse`（palworld_rest 仍构造 RestResponse[:69/73/105/109/124]，此 import 天然 re-export → `palworld_rest.RestResponse` 供旧路径消费者零改）。

- [ ] **Step 3: 重指消费者**

- `application/{admin,snapshot}_service.py`：`from ..adapters.palworld_rest import RestResponse` → `from ..shared.rest import RestResponse`。**注**：admin_service.py:8 是合并 import `from ..adapters.palworld_rest import _ADMIN_PATH, RestResponse`——本 Task 只把 RestResponse 拆走改 shared，保留 `from ..adapters.palworld_rest import _ADMIN_PATH`（该 `_ADMIN_PATH` 由 Task 3 再迁 domain 后删）。
- `infrastructure/scheduler.py`：`from ..adapters.palworld_rest import RestResponse` → `from ..shared.rest import RestResponse`。
- `container.py:12`：`from .adapters.palworld_rest import PalworldRestClient, RestResponse` → 拆成 `from .adapters.palworld_rest import PalworldRestClient` + `from .shared.rest import RestResponse`（:172/178/185 标注不变）。

- [ ] **Step 4: 跑测试**

Run: `( py -m pytest -q ) && ruff check . && ( py -m mypy palworld_terminal )`
Expected: 全 PASS。application 的 admin/snapshot 现无 RestResponse 的 adapters import；golden 字节不变。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: RestResponse 迁 shared/rest（三层共用，palworld_rest re-export 保旧路径）"
```

---

## Task 3: _ADMIN_PATH → domain ADMIN_ACTIONS + normalize_players 注入

**Files:**
- Modify: `domain/enums.py`（加 ADMIN_ACTIONS）、`adapters/palworld_rest.py`（删 _ADMIN_PATH，若用则 import）、`application/admin_service.py`（reach-in 改 + 注入）、`container.py`（构造 AdminService 传 normalize_players）、`tests/unit/admin_service_test.py`、`tests/unit/commands_admin_write_test.py`

**Interfaces:**
- Produces: `domain.enums.ADMIN_ACTIONS`（frozenset）；`AdminService.__init__` 末位增 `normalize_players` 必填参数

- [ ] **Step 1: _ADMIN_PATH → domain.enums.ADMIN_ACTIONS**

- `domain/enums.py` 尾部加：`ADMIN_ACTIONS: frozenset[str] = frozenset({"announce", "save", "kick", "unban", "ban", "shutdown", "stop"})`（逐字复制自 palworld_rest.py:25 的 `_ADMIN_PATH` 值）。
- `adapters/palworld_rest.py`：删 `_ADMIN_PATH = ...`（:25）；若 palworld_rest 内部用到则 `from ..domain.enums import ADMIN_ACTIONS`（grep 确认 palworld_rest 是否自用；若不用则纯删）。
- `application/admin_service.py`：`from ..adapters.palworld_rest import _ADMIN_PATH, RestResponse` → RestResponse 已在 Task 2 改走 shared，此处删 `_ADMIN_PATH` 部分；加 `from ..domain.enums import ADMIN_ACTIONS`；`:66` 的 `if path not in _ADMIN_PATH` → `if path not in ADMIN_ACTIONS`。

- [ ] **Step 2: normalize_players 注入 AdminService**

`application/admin_service.py`：
- `__init__` 末位加必填参数 `normalize_players`（callable）；存 `self._normalize_players = normalize_players`。
- 删 `from ..adapters.normalizer import normalize_players`（:7）。
- `:203` 的 `normalize_players(resp.data, now)` → `self._normalize_players(resp.data, now)`。

- [ ] **Step 3: 6 处构造点追加 normalize_players= kwarg**

- `container.py`（约 :141 构造 AdminService）：追加 `normalize_players=normalizer.normalize_players`（container 已 import adapters.normalizer 或从 `_normalizer_mod` 取；以实际为准，在 adapters 边界注入）。
- `tests/unit/admin_service_test.py:60/93/143/192/263`：各追加 `normalize_players=`。**`:143`/`:263`（`_svc_players`=resolve_target/kick 路径，fetch 返回 `{"players":...}`）须传 `normalize_players=normalize_players`（测试文件 `from palworld_terminal.adapters.normalizer import normalize_players` 拿真函数）保注入等价**；其余不触达该路径的构造传真函数或等价桩。
- `tests/unit/commands_admin_write_test.py:106`：追加 `normalize_players=`（其 routing 先失败不触达该 callable，传真函数或桩皆可）。
- 以 grep `AdminService(` 全量为准，别漏构造点。

- [ ] **Step 4: 跑测试**

Run: `( py -m pytest -q ) && ruff check . && ( py -m mypy palworld_terminal )`
Expected: 全 PASS。**特别确认**：`admin_service.py` 现 **0 处 adapters import**（RestResponse→shared[T2]、_ADMIN_PATH→domain、normalizer→注入、privacy hash_user_id→domain[T1]）；`admin_service_test` 的 `resolve_target` 三测绿 = 注入等价；golden 字节不变。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: _ADMIN_PATH 迁 domain ADMIN_ACTIONS + normalize_players 注入 AdminService（admin 清零 adapters）"
```

---

## Task 4: RepositoryPort 4 分离端口 + 重标注

**Files:**
- Create: `palworld_terminal/application/ports.py`
- Modify: `application/{query,report,routing,event}_service.py`、`application/name_resolver.py`、`application/admin_service.py`

**Interfaces:**
- Produces: `application/ports.py` 导出 `ReadRepositoryPort`/`WriteRepositoryPort`/`RoutingRepositoryPort`/`AuditRepositoryPort`（Protocol）

- [ ] **Step 1: 建 application/ports.py（4 Protocol）**

新建 `palworld_terminal/application/ports.py`。定义 4 个 `Protocol`，**每个方法的签名逐字复制自 `adapters/sqlite_repository.py` 对应 public 方法**（含参数、默认值、返回类型、async）：
```python
from __future__ import annotations

from typing import Protocol

# ... 从 domain.models/enums import 端口签名用到的返回/参数类型 ...


class ReadRepositoryPort(Protocol):
    # 逐字抄 Repository 的这 17 个方法签名：
    # get_hidden_keys, get_open_session, get_player, get_player_by_name,
    # latest_base_observation, latest_metric, latest_observation, list_bases,
    # list_events, list_guilds, list_open_sessions, list_players_by_level,
    # list_players_by_name, peak_online, sessions_in_day, total_durations, world_day_bounds
    ...


class WriteRepositoryPort(Protocol):
    # insert_event, peak_online
    ...


class RoutingRepositoryPort(Protocol):
    # get_allowed, get_binding_active, list_group_servers, revoke, set_active
    ...


class AuditRepositoryPort(Protocol):
    # get_current_world, insert_audit
    ...
```
从 `sqlite_repository.py` 逐一抄准每个方法的 `async def NAME(self, ...) -> RetType: ...`（Protocol 内方法体用 `...`）。ports.py 只依赖 domain（models/enums）+ typing——不 import adapters。

- [ ] **Step 2: 重标注 5 service + name_resolver**

- `application/query_service.py` / `report_service.py`：删 `from ..adapters.sqlite_repository import Repository`；加 `from .ports import ReadRepositoryPort`；构造函数 `repo: Repository` → `repo: ReadRepositoryPort`（`self._repo` 类型随之）。
- `application/name_resolver.py`：删 Repository import；加 `from .ports import ReadRepositoryPort`；自由函数的 `repo: Repository` 参数 → `repo: ReadRepositoryPort`。
- `application/event_service.py`：Repository → `WriteRepositoryPort`。
- `application/routing_service.py`：Repository → `RoutingRepositoryPort`。
- `application/admin_service.py`：`self._repo` 加标注 `AuditRepositoryPort`（admin 原 duck-type，此为新增标注，`from .ports import AuditRepositoryPort`；构造参数 `repo` 标注 AuditRepositoryPort）。

- [ ] **Step 3: 跑测试（mypy 结构化校验是关键）**

Run: `( py -m pytest -q ) && ruff check . && ( py -m mypy palworld_terminal )`
Expected: 全 PASS。**mypy 绿 = Repository 结构化满足 4 端口的证明**（container 传 Repository 实例到各 service，mypy 校验 Repository ⊇ 各端口；若某端口漏方法或签名不符，mypy 在 container 装配处或 service 内报错）。golden 字节不变。若 mypy 报「Repository 不满足端口」→ 对照报错补齐端口方法签名（从 sqlite_repository 抄准）。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: RepositoryPort 4 分离端口 + 重标注 5 service（application 清零 Repository import）"
```

---

## Task 5: application→adapters=0 静态守卫 + 收尾

**Files:**
- Create: `tests/unit/adapter_layering_guard_test.py`

**Interfaces:** 无（纯静态扫描）

- [ ] **Step 1: 写守卫测试**

`tests/unit/adapter_layering_guard_test.py`：
```python
import pathlib

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "palworld_terminal" / "application"


def test_application_has_no_adapters_import():
    """application 层绝不 import adapters（依赖倒置守卫，Spec C §6）。"""
    offenders = []
    for py in APP_DIR.glob("*.py"):
        src = py.read_text(encoding="utf-8")
        if "from ..adapters" in src or "import palworld_terminal.adapters" in src:
            offenders.append(py.name)
    assert offenders == [], f"application 层残留 adapters import：{offenders}"
```

- [ ] **Step 2: 跑守卫 + 咬合自证**

Run: `( py -m pytest tests/unit/adapter_layering_guard_test.py -q )`
Expected: PASS（T1-T4 已清零 12 处）。**咬合自证**：临时在某 application 文件插 `from ..adapters.sqlite_repository import Repository` → 跑守卫应 FAIL 并列出该文件 → 删除还原 → PASS（证守卫真咬合、路径真定位 application）。若守卫意外 FAIL 列出残留者 → 回对应 Task 补清。

- [ ] **Step 3: 全量终验**

Run: `( py -m pytest -q ) && ruff check . && ( py -m mypy palworld_terminal )`
Expected: 全 PASS（1194 passed/1 skipped 量级）。golden `.txt` 对分支起点字节不变（`git diff --stat 6c20b23 HEAD -- tests/golden/` 空）。`no_absolute_self_import_test`/`namespace_runtime_smoke` 绿（三新文件 domain/privacy、shared/rest、application/ports 被 rglob 覆盖、相对导入链拉起）。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: 新增 application 无 adapters-import 分层守卫"
```

---

## Self-Review 备忘（已核对 spec 覆盖）
- §4.1 privacy+PrivacyConfig+re-export → Task 1；§4.2 RestResponse → Task 2；§4.3 _ADMIN_PATH + §4.4 normalize_players 注入 → Task 3；§5 RepositoryPort 4 端口 → Task 4；§6 守卫 → Task 5。
- 复核修正全落地：re-export 不变量（T1 Step2 config / T2 Step2 palworld_rest）、normalize_players 6 构造点（T3 Step3）、~12 privacy 测试重指（T1 Step4）、注入等价回归网=admin_service_test resolve_target（T3 Step4）。
- 验收 §10：application→adapters=0（T5 守卫）、golden 字节（各任务+T5）、无环（T1 mypy）、Repository 满足 4 端口（T4 mypy）、三新文件守卫覆盖（T5）。
- 每相独立绿：T1（privacy 迁移，golden 兜底）、T2（RestResponse 迁移）、T3（admin 清零，resolve_target 兜注入）、T4（端口，mypy 校验）、T5（守卫锁死）。
