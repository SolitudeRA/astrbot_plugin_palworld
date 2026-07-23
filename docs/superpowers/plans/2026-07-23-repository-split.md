# Repository god 对象拆解（mixin 组合）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `adapters/sqlite_repository.py`（900 行、单 `Repository` 类、57 方法 god 对象）沿实体表族拆成 7 个 mixin（各一文件），主类多重继承组合，零行为变化。

**Architecture:** 先 additive 建 7 个 mixin 文件（逐字搬方法体，主体不动、方法暂时重复共存但无冲突），再在一个原子任务里切换主体（删 55 方法、加 7 继承、import 一次收缩到最终态、重写 docstring），最后加结构守卫。跨表原子事务 `purge_server_data`/`prune` 留主体（直接持 `self._db.write_tx`）。

**Tech Stack:** Python 3.11 / mixin 组合（无 __init__ 的纯行为混入 + 纯类型注解自类型）/ pytest / ruff / mypy。

**Spec:** `docs/superpowers/specs/2026-07-23-repository-split-design.md`（方法归属见 §4、每 mixin import 见 §5、守卫配方见 §7）。

## Global Constraints

- **逐字搬（字节级）**：方法体（含 docstring、方法内注释、空行）从 `sqlite_repository.py` 对应行号逐字复制，不改一字。**不要在本 plan 里重抄方法体**——照源文件行号复制，避免转写引入偏差。
- **按方法名清单抽取，不按连续源码范围切**：源码方法**物理交错**——`_PURGE_WORLD_TABLES`+`purge_server_data`（行 149-185，留主体）夹在 routing 方法之间；`insert_audit`/`list_audit`/`prune_audit`+`prune`（行 331-395）夹在 world 簇与 metrics 簇之间。**逐个方法按名字抽取**，绝不能剪一段连续行。
- **行尾（CRLF 陷阱）**：`sqlite_repository.py` 是 **CRLF**（仓库 `.gitattributes` 不管 `.py`）。改主体（Task 8）用 Edit 工具**字节保真保 CRLF**，绝不能用会翻 LF 的写法（三部曲版本升级曾踩此坑致整文件 churn）。新建的 7 个 mixin 文件与守卫测试用 **LF**（新文件无保真义务，LF 更简单、与 `normalizer.py`/`tests/` 一致；"逐字搬"指方法体内容[缩进/SQL/注释]字节一致，行尾 LF 非实质）。
- **零行为变化**：现有全库 **1195 passed / 1 skipped** 不变。任何搬移漂移都会在现有真-sqlite 测试转红。
- **验收命令**：`ruff check .`（全仓，含 tests）+ `python -m mypy palworld_terminal/`（Success）+ `python -m pytest -q`（1195 passed/1 skipped + 新守卫）全绿。
- **TDD 偏离**：本重构无新行为，搬迁任务（Task 1-8）的 test cycle = **全库回归**（现有测试即等价性安全网）；仅 Task 9 守卫是新测试、走 TDD。
- **commit 不含 Claude/Co-Authored-By 署名。**
- **零改动**：`container.py`、`application/ports.py`、所有 service、所有调用点、所有现有测试文件。

## File Structure

- Create（LF）：`adapters/repo_routing.py` · `repo_player_binding.py` · `repo_world.py` · `repo_player_profile.py` · `repo_guild_base.py` · `repo_event.py` · `repo_audit.py`——各承载一个实体表族的 mixin。
- Modify（CRLF，保真）：`adapters/sqlite_repository.py`——900 行 god 类 → ~130 行组合主体。
- Create（LF）：`tests/unit/repository_split_guard_test.py`——结构守卫。

---

## Task 1: `_ServerRoutingRepo` → `repo_routing.py`（12 方法）

**Files:**
- Create: `palworld_terminal/adapters/repo_routing.py`（LF）

**Interfaces:**
- Produces: `class _ServerRoutingRepo`（供 Task 8 主体继承）——含 `sync_servers`/`seed_bindings`/`cleanup_orphan_bindings`/`list_allowed_bindings`/`list_orphan_server_ids`/`bind_umos_to_server`/`clear_all_group_servers`/`get_binding_active`/`get_allowed`/`list_group_servers`/`set_active`/`revoke`。

- [ ] **Step 1: 建文件（import 头 + 自类型 + docstring + 逐字搬 12 方法）**

文件开头照抄（import 头来自 spec §5）：
```python
from __future__ import annotations

from ..config import BindingConfig, ServerConfig
from ..infrastructure.clock import Clock
from ..infrastructure.database import Database


class _ServerRoutingRepo:
    """servers / group_servers 表族：服务器同步、群绑定/路由授权、active 与 revoke。"""

    _db: Database
    _clock: Clock
```
然后从 `sqlite_repository.py` **逐字复制**以下方法（按名字，注意跳过夹在中间的 149-185=purge/常量，**不要搬**）到类体内，保持原相对顺序与 CRLF：

| 方法 | 源行号 |
|---|---|
| `sync_servers` | 44–55 |
| `seed_bindings`（含段头注释 `# ---- bindings / routing ----`）| 57–86 |
| `cleanup_orphan_bindings` | 88–97 |
| `list_allowed_bindings` | 99–105 |
| `list_orphan_server_ids` | 107–116 |
| `bind_umos_to_server` | 118–141 |
| `clear_all_group_servers` | 143–147 |
| `get_binding_active` | 187–192 |
| `get_allowed` | 194–198 |
| `list_group_servers` | 200–204 |
| `set_active` | 206–219 |
| `revoke` | 221–224 |

- [ ] **Step 2: 新文件 lint 干净 + 全库回归不破坏**

Run: `ruff check palworld_terminal/adapters/repo_routing.py && python -m pytest -q`
Expected: ruff 无输出（clean）；pytest `1195 passed, 1 skipped`（mixin 此刻是未继承的"死代码"，不影响现有行为）。

- [ ] **Step 3: mypy 通过**

Run: `python -m mypy palworld_terminal/`
Expected: `Success: no issues found in 52 source files`（自类型 `_db`/`_clock` 声明使 `self._db`/`self._clock` 可解析）。

- [ ] **Step 4: 健全性检查——方法名齐全**

Run: `python -c "from palworld_terminal.adapters.repo_routing import _ServerRoutingRepo; m=[x for x in dir(_ServerRoutingRepo) if not x.startswith('__')]; print(sorted(m)); assert len([x for x in m if not x.startswith('_')])>=12"`
Expected: 打印 12 个方法名，assert 通过。

- [ ] **Step 5: Commit**

```bash
git add palworld_terminal/adapters/repo_routing.py
git commit -m "refactor: 抽出 _ServerRoutingRepo mixin（repo_routing.py）"
```

---

## Task 2: `_PlayerBindingRepo` → `repo_player_binding.py`（6 方法）

**Files:**
- Create: `palworld_terminal/adapters/repo_player_binding.py`（LF）

**Interfaces:**
- Produces: `class _PlayerBindingRepo`——含 `upsert_binding`/`get_binding`/`set_hidden`/`unset_hidden`/`delete_binding`/`get_hidden_keys`。

- [ ] **Step 1: 建文件**

```python
from __future__ import annotations

from ..infrastructure.clock import Clock
from ..infrastructure.database import Database


class _PlayerBindingRepo:
    """player_bindings / hidden_players 表族：平台账号↔玩家绑定、玩家自助隐藏。"""

    _db: Database
    _clock: Clock
```
逐字复制（含段头注释 `# ---- player bindings / hidden ----` 行 226）：

| 方法 | 源行号 |
|---|---|
| `upsert_binding` | 227–235 |
| `get_binding` | 237–242 |
| `set_hidden` | 244–252 |
| `unset_hidden` | 254–258 |
| `delete_binding` | 260–264 |
| `get_hidden_keys` | 266–270 |

- [ ] **Step 2: lint + 回归**

Run: `ruff check palworld_terminal/adapters/repo_player_binding.py && python -m pytest -q`
Expected: clean；`1195 passed, 1 skipped`。

- [ ] **Step 3: mypy**

Run: `python -m mypy palworld_terminal/`
Expected: `Success ... 53 source files`。

- [ ] **Step 4: 健全性检查**

Run: `python -c "from palworld_terminal.adapters.repo_player_binding import _PlayerBindingRepo; m=[x for x in dir(_PlayerBindingRepo) if not x.startswith('_')]; print(sorted(m)); assert len(m)>=6"`
Expected: 6 方法名，assert 通过。

- [ ] **Step 5: Commit**

```bash
git add palworld_terminal/adapters/repo_player_binding.py
git commit -m "refactor: 抽出 _PlayerBindingRepo mixin（repo_player_binding.py）"
```

---

## Task 3: `_WorldMetricRepo` → `repo_world.py`（8 方法）

**Files:**
- Create: `palworld_terminal/adapters/repo_world.py`（LF）

**Interfaces:**
- Produces: `class _WorldMetricRepo`——含 `upsert_world`/`get_current_world`/`list_worlds_with_open_sessions`/`insert_metric`/`latest_metric`/`world_day_bounds`/`peak_online`/`upsert_unknown_classes`。

- [ ] **Step 1: 建文件（⚠️ 方法分两不连续块，跳过夹在中间的 audit+prune）**

```python
from __future__ import annotations

from ..domain.models import World, WorldMetric
from ..infrastructure.clock import Clock
from ..infrastructure.database import Database


class _WorldMetricRepo:
    """worlds / world_metrics / unknown_classes 表族：世界档案与性能指标。"""

    _db: Database
    _clock: Clock
```
逐字复制（**注意**：world 段 273–329 与 metrics 段 398–479 之间夹着 `# ---- admin audit ----`+`# ---- retention ----`，**不要搬那些**；段头 `# ---- world ----` 行 272、`# ---- metrics ----` 行 397 随本组迁入）：

| 方法 | 源行号 |
|---|---|
| `upsert_world` | 273–286 |
| `get_current_world` | 288–302 |
| `list_worlds_with_open_sessions` | 304–329 |
| `insert_metric` | 398–408 |
| `latest_metric` | 410–429 |
| `world_day_bounds` | 431–452 |
| `peak_online` | 454–468 |
| `upsert_unknown_classes` | 470–479 |

- [ ] **Step 2: lint + 回归**

Run: `ruff check palworld_terminal/adapters/repo_world.py && python -m pytest -q`
Expected: clean；`1195 passed, 1 skipped`。

- [ ] **Step 3: mypy**

Run: `python -m mypy palworld_terminal/`
Expected: `Success ... 54 source files`。

- [ ] **Step 4: 健全性检查**

Run: `python -c "from palworld_terminal.adapters.repo_world import _WorldMetricRepo; m=[x for x in dir(_WorldMetricRepo) if not x.startswith('_')]; print(sorted(m)); assert len(m)>=8"`
Expected: 8 方法名，assert 通过。

- [ ] **Step 5: Commit**

```bash
git add palworld_terminal/adapters/repo_world.py
git commit -m "refactor: 抽出 _WorldMetricRepo mixin（repo_world.py）"
```

---

## Task 4: `_PlayerProfileRepo` → `repo_player_profile.py`（14 方法）

**Files:**
- Create: `palworld_terminal/adapters/repo_player_profile.py`（LF）

**Interfaces:**
- Produces: `class _PlayerProfileRepo`——含 `upsert_player`/`get_player`/`get_player_by_name`/`list_players_by_name`/`list_players_by_level`/`_row_to_session`（@staticmethod）/`insert_session`/`update_session`/`get_open_session`/`list_open_sessions`/`sessions_in_day`/`total_durations`/`insert_observation`/`latest_observation`。

- [ ] **Step 1: 建文件**

```python
from __future__ import annotations

from typing import cast

from ..domain.enums import IdConfidence, LeaveReason, PingBucket, SessionStatus
from ..domain.models import PlayerIdentity, PlayerObservation, PlayerSession
from ..infrastructure.database import Database


class _PlayerProfileRepo:
    """players / player_sessions / player_observations 表族：玩家档案、会话、观测。"""

    _db: Database
```
（**本组无方法用 `self._clock`，故不声明 `_clock`**。）逐字复制（`_row_to_session` 保持 `@staticmethod` 装饰器行；段头 `# ---- players ----`(481)/`# ---- sessions ----`(566)/`# ---- observations ----`(654) 随迁）：

| 方法 | 源行号 |
|---|---|
| `upsert_player` | 482–498 |
| `get_player` | 500–516 |
| `get_player_by_name` | 518–537 |
| `list_players_by_name` | 539–544 |
| `list_players_by_level` | 546–564 |
| `_row_to_session`（`@staticmethod`）| 567–575 |
| `insert_session` | 577–592 |
| `update_session` | 594–604 |
| `get_open_session` | 606–615 |
| `list_open_sessions` | 617–626 |
| `sessions_in_day` | 628–641 |
| `total_durations` | 643–652 |
| `insert_observation` | 655–665 |
| `latest_observation` | 667–687 |

- [ ] **Step 2: lint + 回归**

Run: `ruff check palworld_terminal/adapters/repo_player_profile.py && python -m pytest -q`
Expected: clean；`1195 passed, 1 skipped`。

- [ ] **Step 3: mypy**

Run: `python -m mypy palworld_terminal/`
Expected: `Success ... 55 source files`。

- [ ] **Step 4: 健全性检查（含下划线 `_row_to_session`）**

Run: `python -c "import inspect; from palworld_terminal.adapters.repo_player_profile import _PlayerProfileRepo; m={n for n,_ in inspect.getmembers(_PlayerProfileRepo, inspect.isfunction) if not n.startswith('__')}; print(sorted(m)); assert '_row_to_session' in m and len(m)>=14"`
Expected: 14 方法名（含 `_row_to_session`），assert 通过。

- [ ] **Step 5: Commit**

```bash
git add palworld_terminal/adapters/repo_player_profile.py
git commit -m "refactor: 抽出 _PlayerProfileRepo mixin（repo_player_profile.py）"
```

---

## Task 5: `_GuildBaseRepo` → `repo_guild_base.py`（8 方法）

**Files:**
- Create: `palworld_terminal/adapters/repo_guild_base.py`（LF）

**Interfaces:**
- Produces: `class _GuildBaseRepo`——含 `upsert_guild`/`list_guilds`/`upsert_palbox`/`list_palboxes`/`upsert_base`/`list_bases`/`insert_base_observation`/`latest_base_observation`。

- [ ] **Step 1: 建文件**

```python
from __future__ import annotations

import json

from ..domain.enums import Confidence
from ..domain.models import Base, BaseObservation, Guild, PalBox
from ..infrastructure.database import Database


class _GuildBaseRepo:
    """guilds / palboxes / bases / base_observations 表族：公会、帕鲁箱、据点及其观测。"""

    _db: Database
```
逐字复制（段头 `# ---- guilds ----`(689)/`# ---- palboxes ----`(721)/`# ---- bases ----`(752)/`# ---- base observations ----`(791) 随迁）：

| 方法 | 源行号 |
|---|---|
| `upsert_guild` | 690–706 |
| `list_guilds` | 708–719 |
| `upsert_palbox` | 722–737 |
| `list_palboxes` | 739–750 |
| `upsert_base` | 753–772 |
| `list_bases` | 774–789 |
| `insert_base_observation` | 792–802 |
| `latest_base_observation` | 804–822 |

- [ ] **Step 2: lint + 回归**

Run: `ruff check palworld_terminal/adapters/repo_guild_base.py && python -m pytest -q`
Expected: clean；`1195 passed, 1 skipped`。

- [ ] **Step 3: mypy**

Run: `python -m mypy palworld_terminal/`
Expected: `Success ... 56 source files`。

- [ ] **Step 4: 健全性检查**

Run: `python -c "from palworld_terminal.adapters.repo_guild_base import _GuildBaseRepo; m=[x for x in dir(_GuildBaseRepo) if not x.startswith('_')]; print(sorted(m)); assert len(m)>=8"`
Expected: 8 方法名，assert 通过。

- [ ] **Step 5: Commit**

```bash
git add palworld_terminal/adapters/repo_guild_base.py
git commit -m "refactor: 抽出 _GuildBaseRepo mixin（repo_guild_base.py）"
```

---

## Task 6: `_EventRepo` → `repo_event.py`（4 方法）

**Files:**
- Create: `palworld_terminal/adapters/repo_event.py`（LF）

**Interfaces:**
- Produces: `class _EventRepo`——含 `insert_event`/`list_events`/`upsert_daily_aggregate`/`get_daily_aggregate`。

- [ ] **Step 1: 建文件**

```python
from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..domain.enums import Confidence, EventType
from ..domain.models import WorldEvent
from ..infrastructure.database import Database


class _EventRepo:
    """world_events / daily_aggregates 表族：世界事件与日聚合。"""

    _db: Database
```
逐字复制（段头 `# ---- world events ----`(824)/`# ---- daily aggregates ----`(879) 随迁）：

| 方法 | 源行号 |
|---|---|
| `insert_event` | 825–848 |
| `list_events` | 850–877 |
| `upsert_daily_aggregate` | 880–889 |
| `get_daily_aggregate` | 891–900 |

- [ ] **Step 2: lint + 回归**

Run: `ruff check palworld_terminal/adapters/repo_event.py && python -m pytest -q`
Expected: clean；`1195 passed, 1 skipped`。

- [ ] **Step 3: mypy**

Run: `python -m mypy palworld_terminal/`
Expected: `Success ... 57 source files`。

- [ ] **Step 4: 健全性检查**

Run: `python -c "from palworld_terminal.adapters.repo_event import _EventRepo; m=[x for x in dir(_EventRepo) if not x.startswith('_')]; print(sorted(m)); assert len(m)>=4"`
Expected: 4 方法名，assert 通过。

- [ ] **Step 5: Commit**

```bash
git add palworld_terminal/adapters/repo_event.py
git commit -m "refactor: 抽出 _EventRepo mixin（repo_event.py）"
```

---

## Task 7: `_AuditRepo` → `repo_audit.py`（3 方法）

**Files:**
- Create: `palworld_terminal/adapters/repo_audit.py`（LF）

**Interfaces:**
- Produces: `class _AuditRepo`——含 `insert_audit`/`list_audit`/`prune_audit`。

- [ ] **Step 1: 建文件**

```python
from __future__ import annotations

from typing import Any

from ..infrastructure.database import Database


class _AuditRepo:
    """admin_audit 表族：管理操作审计写入、读取、留存裁剪。"""

    _db: Database
```
逐字复制（段头 `# ---- admin audit ----`(331) 随迁；**注意**：`prune`(363-395) 紧随 `prune_audit` 但属主体、不搬）：

| 方法 | 源行号 |
|---|---|
| `insert_audit` | 332–344 |
| `list_audit` | 346–353 |
| `prune_audit` | 355–360 |

- [ ] **Step 2: lint + 回归**

Run: `ruff check palworld_terminal/adapters/repo_audit.py && python -m pytest -q`
Expected: clean；`1195 passed, 1 skipped`。

- [ ] **Step 3: mypy**

Run: `python -m mypy palworld_terminal/`
Expected: `Success ... 58 source files`。

- [ ] **Step 4: 健全性检查**

Run: `python -c "from palworld_terminal.adapters.repo_audit import _AuditRepo; m=[x for x in dir(_AuditRepo) if not x.startswith('_')]; print(sorted(m)); assert len(m)>=3"`
Expected: 3 方法名，assert 通过。

- [ ] **Step 5: Commit**

```bash
git add palworld_terminal/adapters/repo_audit.py
git commit -m "refactor: 抽出 _AuditRepo mixin（repo_audit.py）"
```

---

## Task 8: 原子切换主体 `sqlite_repository.py`（删 55 方法、加 7 继承、收缩 import、重写 docstring）

**Files:**
- Modify: `palworld_terminal/adapters/sqlite_repository.py`（CRLF，Edit 字节保真）

**Interfaces:**
- Consumes: 7 mixin 类（Task 1-7）。
- Produces: `class Repository`——组合 7 mixin，仍暴露全部 57 方法；保留 `__init__(db, clock)`、`purge_server_data`、`prune`、`_PURGE_WORLD_TABLES`、`_SECONDS_PER_DAY`。类名/模块/构造签名不变（`from .sqlite_repository import Repository` 全站有效）。

- [ ] **Step 1: 删掉已迁走的 55 方法及其段头注释**

用 Edit 工具，从 `sqlite_repository.py` **删除** Task 1-7 已迁走的 55 个方法（及随迁的段头注释 `# ---- servers ----`/`# ---- bindings / routing ----`/`# ---- player bindings / hidden ----`/`# ---- world ----`/`# ---- admin audit ----`/`# ---- metrics ----`/`# ---- players ----`/`# ---- sessions ----`/`# ---- observations ----`/`# ---- guilds ----`/`# ---- palboxes ----`/`# ---- bases ----`/`# ---- base observations ----`/`# ---- world events ----`/`# ---- daily aggregates ----`）。

**保留**：模块 docstring（下一步重写）、imports（Step 3 收缩）、`_SECONDS_PER_DAY`(35)、`__init__`(38-41)、`_PURGE_WORLD_TABLES`(149-153)、`purge_server_data`(155-185)、`# ---- retention ----`+`prune`(362-395)。保持 CRLF。

- [ ] **Step 2: 加 7 mixin import + class 继承列表**

class 定义改为（顺序即 spec §3.1）：
```python
class Repository(
    _ServerRoutingRepo,
    _PlayerBindingRepo,
    _WorldMetricRepo,
    _PlayerProfileRepo,
    _GuildBaseRepo,
    _EventRepo,
    _AuditRepo,
):
```

- [ ] **Step 3: 收缩 import 到最终态 + 重写模块/类 docstring**

模块顶部最终形态（**替换**原 1-33 行的 docstring+imports；旧 "Phase 1…" docstring 丢弃）：
```python
"""Repository 组合主体：按实体表族拆入 7 个 mixin（repo_*.py）继承组合；
跨表原子事务（purge_server_data/prune）留本体，直接持 self._db.write_tx。"""
from __future__ import annotations

from ..config import HistoryConfig
from ..infrastructure.clock import Clock
from ..infrastructure.database import Database
from .repo_audit import _AuditRepo
from .repo_event import _EventRepo
from .repo_guild_base import _GuildBaseRepo
from .repo_player_binding import _PlayerBindingRepo
from .repo_player_profile import _PlayerProfileRepo
from .repo_routing import _ServerRoutingRepo
from .repo_world import _WorldMetricRepo

_SECONDS_PER_DAY = 86400
```
类 docstring 改为：
```python
    """所有表读写。实现按实体表族拆入 7 个 mixin（repo_*.py）继承组合；
    跨表原子事务（purge/prune）留主体，直接持 self._db.write_tx 保单事务原子性。"""
```
（`Repository.__init__` 不调 `super().__init__()`——mixin 无状态，仅跳过 `object.__init__` no-op；原 `__init__` 本就未调 super。）

- [ ] **Step 4: 全库回归——等价性总验证（最关键）**

Run: `python -m pytest -q`
Expected: `1195 passed, 1 skipped`。此步接上继承后，任何 mixin 副本的字节漂移都会在此暴露转红。若红 → 逐字对照该方法的 mixin 副本与源提交（Task 1-7 前的 sqlite_repository.py）。

- [ ] **Step 5: ruff + mypy 全绿**

Run: `ruff check . && python -m mypy palworld_terminal/`
Expected: `All checks passed!`；`Success: no issues found in 58 source files`。若 ruff 报主体 F401（收缩漏删的 import），删之。

- [ ] **Step 6: 确认主体行数塌缩 + 类名/构造不变**

Run: `python -c "from palworld_terminal.adapters.sqlite_repository import Repository; import inspect; print('lines', len(inspect.getsource(Repository).splitlines())); r=Repository.__init__; print('ctor', list(inspect.signature(r).parameters))" && wc -l palworld_terminal/adapters/sqlite_repository.py`
Expected: 主体文件 ~130 行；构造参数 `['self','db','clock']`。

- [ ] **Step 7: Commit**

```bash
git add palworld_terminal/adapters/sqlite_repository.py
git commit -m "refactor: Repository 主体切换为 7 mixin 继承组合（拆分收尾）"
```

---

## Task 9: 结构守卫 `repository_split_guard_test.py`

**Files:**
- Create: `tests/unit/repository_split_guard_test.py`（LF）

**Interfaces:**
- Consumes: `Repository`（Task 8）、7 mixin、`application/ports.py` 的 4 Protocol。

- [ ] **Step 1: 写守卫测试（3 断言，spec §7 配方）**

```python
import inspect
import pathlib

from palworld_terminal.adapters.sqlite_repository import Repository

ADAPTERS_DIR = (
    pathlib.Path(__file__).resolve().parents[2] / "palworld_terminal" / "adapters"
)

# §4 全表 57 方法完整清单（唯一真相源；含单下划线 _row_to_session）
EXPECTED_METHODS = {
    # routing (12)
    "sync_servers", "seed_bindings", "cleanup_orphan_bindings",
    "list_allowed_bindings", "list_orphan_server_ids", "bind_umos_to_server",
    "clear_all_group_servers", "get_binding_active", "get_allowed",
    "list_group_servers", "set_active", "revoke",
    # player_binding (6)
    "upsert_binding", "get_binding", "set_hidden", "unset_hidden",
    "delete_binding", "get_hidden_keys",
    # world (8)
    "upsert_world", "get_current_world", "list_worlds_with_open_sessions",
    "insert_metric", "latest_metric", "world_day_bounds", "peak_online",
    "upsert_unknown_classes",
    # player_profile (14)
    "upsert_player", "get_player", "get_player_by_name", "list_players_by_name",
    "list_players_by_level", "_row_to_session", "insert_session",
    "update_session", "get_open_session", "list_open_sessions",
    "sessions_in_day", "total_durations", "insert_observation",
    "latest_observation",
    # guild_base (8)
    "upsert_guild", "list_guilds", "upsert_palbox", "list_palboxes",
    "upsert_base", "list_bases", "insert_base_observation",
    "latest_base_observation",
    # event (4)
    "insert_event", "list_events", "upsert_daily_aggregate",
    "get_daily_aggregate",
    # audit (3)
    "insert_audit", "list_audit", "prune_audit",
    # 主体跨表 (2)
    "purge_server_data", "prune",
}


def test_repository_exposes_exactly_57_methods():
    # 类级内省：实例属性 _db/_clock/_PURGE_WORLD_TABLES 不在其中；
    # staticmethod _row_to_session 是 isfunction → 正确纳入。不可用 startswith("_") 过滤。
    actual = {
        n for n, _ in inspect.getmembers(Repository, inspect.isfunction)
        if not n.startswith("__")
    }
    assert actual == EXPECTED_METHODS
    assert len(EXPECTED_METHODS) == 57


def test_mixins_do_not_import_each_other():
    for py in sorted(ADAPTERS_DIR.glob("repo_*.py")):  # 天然排除 sqlite_repository.py
        src = py.read_text(encoding="utf-8")
        assert "from .repo_" not in src, f"{py.name} 跨 mixin import"
        assert "import palworld_terminal.adapters.repo_" not in src, f"{py.name} 跨 mixin import"


def test_repository_satisfies_all_port_methods():
    # 硬编码各端口方法名（不 introspect Protocol 私有 API）。端口分组 ≠ mixin 分组：
    # 如 AuditPort.get_current_world 落 _WorldMetricRepo、insert_audit 落 _AuditRepo，
    # 两者经继承都在 Repository 上。
    port_methods = {
        # ReadRepositoryPort (17)
        "get_hidden_keys", "get_open_session", "get_player", "get_player_by_name",
        "latest_base_observation", "latest_metric", "latest_observation",
        "list_bases", "list_events", "list_guilds", "list_open_sessions",
        "list_players_by_level", "list_players_by_name", "peak_online",
        "sessions_in_day", "total_durations", "world_day_bounds",
        # WriteRepositoryPort (2) — peak_online 与 Read 重合
        "insert_event",
        # RoutingRepositoryPort (5)
        "get_allowed", "get_binding_active", "list_group_servers", "revoke",
        "set_active",
        # AuditRepositoryPort (2)
        "get_current_world", "insert_audit",
    }
    for m in port_methods:
        assert hasattr(Repository, m), f"Repository 缺端口方法 {m}"
```

- [ ] **Step 2: 跑守卫——应通过（拆分已在 Task 8 完成）**

Run: `python -m pytest tests/unit/repository_split_guard_test.py -v`
Expected: 3 passed。

- [ ] **Step 3: 验证守卫有效性（临时反证，可选但推荐）**

临时在 `repo_audit.py` 注释掉 `prune_audit` 一个方法，跑 `pytest tests/unit/repository_split_guard_test.py::test_repository_exposes_exactly_57_methods` → 应 FAIL（`actual != EXPECTED`）。**还原**。确认守卫真能抓搬漏。

- [ ] **Step 4: 全套验收 + ruff/mypy**

Run: `ruff check . && python -m mypy palworld_terminal/ && python -m pytest -q`
Expected: `All checks passed!`；`Success ... 58 source files`；`1198 passed, 1 skipped`（1195 + 3 守卫）。

- [ ] **Step 5: Commit**

```bash
git add tests/unit/repository_split_guard_test.py
git commit -m "test: repository 拆分结构守卫（方法集完整性 + mixin 隔离 + 端口满足）"
```

---

## 完成标准

- `adapters/sqlite_repository.py` 从 900 行 god 类塌缩为 ~130 行组合主体。
- 7 个 mixin 各承一实体表族，互不 import。
- `Repository` 仍暴露全部 57 方法、满足 4 端口、类名/模块/构造签名不变、全站零改动。
- `ruff check .` + `mypy(58)` + `pytest`（1198 passed/1 skipped）全绿。
- 全程零行为变化（现有 1195 测试不变）、方法体逐字搬（CRLF 保真）。
