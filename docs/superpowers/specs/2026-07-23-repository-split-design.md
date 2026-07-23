# Repository god 对象拆解：mixin 组合（架构解耦 Spec D）

**日期**：2026-07-23
**分支**：`feat/repository-split`（叠于 main @ v1.1.0）
**类型**：纯结构重构，零行为变化
**前序**：架构解耦三部曲 A（PR #29 presentation 解耦）/ B（PR #32 拆 commands.py）/ C（PR #31 适配器解耦）已合并 main v1.1.0。本 Spec 是三部曲揪出的"实现层 god 对象"收尾。

---

## 1. 背景与目标

三部曲把**跨层耦合**解决透了（application 对 presentation + adapters 反向依赖 = 0）。但收尾评估发现两个"活下来的巨类"，其中最大的是：

- **`adapters/sqlite_repository.py` = 900 行 / 单个 `Repository` 类 / 57 个非 `__init__` 方法**，全库最大文件。
- Spec C 已把 Repository 的**消费者契约**切成了 4 个 `Protocol`（`ReadRepositoryPort` 17 / `WriteRepositoryPort` 2 / `RoutingRepositoryPort` 5 / `AuditRepositoryPort` 2），但**实现层仍是一整块**——这是"接口隔离（ISP）只做了一半"：类型层隔离了，实现层还是巨类。

**目标**：沿实体表族把 `Repository` 的实现拆成 7 个 mixin（各一文件），主类多重继承组合。**零行为变化、零字节方法体（逐字搬）、全站零改动**。

**非目标（YAGNI）**：
- 不改任何 SQL、不改任何方法签名/行为。
- 不改 `application/ports.py` 的 4 端口（消费者契约不动）。
- 不改任何调用点（全站 `repo.x()` 不变）。
- 不改 `container.py` 的装配（唯一构造点 `Repository(db, clock)` 不变）。
- 不拆数据库表、不改 migrations。
- 不做独立注入式的端口分道（Q1 已否决：破坏跨表原子事务、非零字节、风险最高）。

---

## 2. 现状锚点（重构前必须为真）

| 事实 | 值 | 来源 |
|---|---|---|
| `Repository` 类 | 单类，`__init__(db, clock)` + 57 方法 | sqlite_repository.py:38 |
| 唯一构造点 | `Repository(self._db, self._clock)` | container.py:100 |
| 全站调用形态 | `repo.<method>()`（`self.repo` / `self._repo` 别名） | container.py:101-102 |
| monkeypatch seam | **无**——真 in-memory sqlite 实例测试（非 mock） | tests 全库 grep 零命中 |
| 端口满足方式 | 结构化（duck typing），`Repository` 无继承/无声明 | ports.py:5 |
| 跨表原子方法 | `purge_server_data`（跨 15 表单 `write_tx`）、`prune`（跨 6 表单 `write_tx`） | sqlite_repository.py:155,363 |
| 类级常量 | `_PURGE_WORLD_TABLES`（12 元组，只被 `purge` 用） | sqlite_repository.py:149 |
| 模块级常量 | `_SECONDS_PER_DAY = 86400`（只被 `prune` 用） | sqlite_repository.py:35 |
| **跨 mixin 方法调用** | **零**——每个方法只触达 `self._db` / `self._clock` / 同组 `_row_to_session` / 主体 `_PURGE_WORLD_TABLES` | 全文件核查 |

**"零跨 mixin 调用"是 mixin 方案成立的硬前提**：`_row_to_session`（staticmethod）只被同组 session 方法调用；`_PURGE_WORLD_TABLES` 只被主体 `purge` 用。拆分后每个 mixin 完全自足。

**导出路径不变量**：`Repository` 类名、所在模块 `sqlite_repository.py`、构造签名 `(db, clock)` 全部不变，故 `from .sqlite_repository import Repository`（container.py:12 与约 50 个测试文件的 import 路径）保持有效。这些测试文件构造**真实 Repository 实例**并 `repo.x()` 调用——既是"全站零改动"的一部分，也是本次拆分等价性的主要安全网（覆盖 CRUD/事务/迁移）。

---

## 3. 拆分方案：Mixin 组合

### 3.1 主类组合形态

```python
# adapters/sqlite_repository.py（主体，~130 行）
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


class Repository(
    _ServerRoutingRepo,
    _PlayerBindingRepo,
    _WorldMetricRepo,
    _PlayerProfileRepo,
    _GuildBaseRepo,
    _EventRepo,
    _AuditRepo,
):
    """所有表读写。实现按实体表族拆入 7 个 mixin（repo_*.py）；跨表原子事务
    （purge/prune）留主体，直接持 self._db.write_tx 保单事务原子性。"""

    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    _PURGE_WORLD_TABLES = (
        "players", "player_sessions", "player_observations", "guilds",
        "palboxes", "bases", "base_observations", "world_metrics",
        "world_events", "daily_aggregates", "player_bindings", "hidden_players",
    )

    async def purge_server_data(self, server_id: str) -> dict[str, int]:
        ...  # 逐字搬，不改一字节

    async def prune(self, history: HistoryConfig, now: int, audit_retention_days: int) -> None:
        ...  # 逐字搬，不改一字节
```

- MRO 干净：7 mixin 均直接继承 `object`，无钻石继承。`Repository.__init__` 唯一设 `self._db`/`self._clock`。
- mixin 不定义 `__init__`（纯行为混入、无自身状态）；`Repository.__init__` 无需调用 `super().__init__()`（仅跳过 `object.__init__` 这一 no-op；原 `__init__` 逐字搬模板本就未调 `super()`）。
- `_PURGE_WORLD_TABLES` 与 `_SECONDS_PER_DAY` 留主体（`purge`/`prune` 的私有依赖）。

### 3.2 mixin 自类型声明（mypy 惯用法）

每个 mixin 引用 `self._db`（全部）与 `self._clock`（部分），但这两个属性由主类 `__init__` 提供、mixin 自己不赋值。用**纯类型注解**告诉 mypy 属性存在（零运行时开销）：

```python
class _WorldMetricRepo:            # 文件完整 import 头见 §5
    _db: Database
    _clock: Clock       # 仅当该 mixin 有方法调 self._clock.now() 才声明
    ...
```

**`_clock` 声明只在 3 个 mixin**（其余 4 个只声明 `_db`）：

| mixin | 声明 `_db` | 声明 `_clock` | 用 clock 的方法 |
|---|:---:|:---:|---|
| `_ServerRoutingRepo` | ✓ | ✓ | sync_servers / seed_bindings / bind_umos_to_server / set_active |
| `_PlayerBindingRepo` | ✓ | ✓ | upsert_binding / set_hidden |
| `_WorldMetricRepo` | ✓ | ✓ | upsert_unknown_classes |
| `_AuditRepo` | ✓ | — | — |
| `_PlayerProfileRepo` | ✓ | — | — |
| `_GuildBaseRepo` | ✓ | — | — |
| `_EventRepo` | ✓ | — | — |

**规则**：mixin 声明它**实际引用**的 `self` 属性。漏声明 `_clock` → mypy `attr-defined` 转红（安全网）。多声明未用属性注解 → mypy/ruff 均不报（但按上表精确声明，不多不少）。

---

## 4. 方法归属（57 方法完整分配，防搬漏/搬重）

### 4.1 `_ServerRoutingRepo` → `repo_routing.py`（12 方法）
`sync_servers` · `seed_bindings` · `cleanup_orphan_bindings` · `list_allowed_bindings` · `list_orphan_server_ids` · `bind_umos_to_server` · `clear_all_group_servers` · `get_binding_active` · `get_allowed` · `list_group_servers` · `set_active` · `revoke`

### 4.2 `_PlayerBindingRepo` → `repo_player_binding.py`（6 方法）
`upsert_binding` · `get_binding` · `set_hidden` · `unset_hidden` · `delete_binding` · `get_hidden_keys`

### 4.3 `_WorldMetricRepo` → `repo_world.py`（8 方法）
`upsert_world` · `get_current_world` · `list_worlds_with_open_sessions` · `insert_metric` · `latest_metric` · `world_day_bounds` · `peak_online` · `upsert_unknown_classes`

### 4.4 `_PlayerProfileRepo` → `repo_player_profile.py`（14 方法）
`upsert_player` · `get_player` · `get_player_by_name` · `list_players_by_name` · `list_players_by_level` · `_row_to_session`（保持 `@staticmethod`；迁后 `self._row_to_session(...)` 经 MRO 解析不变）· `insert_session` · `update_session` · `get_open_session` · `list_open_sessions` · `sessions_in_day` · `total_durations` · `insert_observation` · `latest_observation`

### 4.5 `_GuildBaseRepo` → `repo_guild_base.py`（8 方法）
`upsert_guild` · `list_guilds` · `upsert_palbox` · `list_palboxes` · `upsert_base` · `list_bases` · `insert_base_observation` · `latest_base_observation`

### 4.6 `_EventRepo` → `repo_event.py`（4 方法）
`insert_event` · `list_events` · `upsert_daily_aggregate` · `get_daily_aggregate`

### 4.7 `_AuditRepo` → `repo_audit.py`（3 方法）
`insert_audit` · `list_audit` · `prune_audit`

### 4.8 主体 `Repository`（2 跨表方法）
`purge_server_data` · `prune`

**合计**：12+6+8+14+8+4+3 = 55 迁 mixin，+2 留主体 = **57**。✓

---

## 5. 每 mixin 的 imports（精确分配，ruff isort 预排序）

ruff `I`/`F401` 会抓 import 排序错误与未用 import，故每个 mixin 只 import 它实际用到的符号，且已按 isort（`__future__` → stdlib → 本地一级 → 本地同级）预排。

**`repo_routing.py`**
```python
from __future__ import annotations

from ..config import BindingConfig, ServerConfig
from ..infrastructure.clock import Clock
from ..infrastructure.database import Database
```

**`repo_player_binding.py`**
```python
from __future__ import annotations

from ..infrastructure.clock import Clock
from ..infrastructure.database import Database
```

**`repo_world.py`**
```python
from __future__ import annotations

from ..domain.models import World, WorldMetric
from ..infrastructure.clock import Clock
from ..infrastructure.database import Database
```

**`repo_player_profile.py`**
```python
from __future__ import annotations

from typing import cast

from ..domain.enums import IdConfidence, LeaveReason, PingBucket, SessionStatus
from ..domain.models import PlayerIdentity, PlayerObservation, PlayerSession
from ..infrastructure.database import Database
```

**`repo_guild_base.py`**
```python
from __future__ import annotations

import json

from ..domain.enums import Confidence
from ..domain.models import Base, BaseObservation, Guild, PalBox
from ..infrastructure.database import Database
```

**`repo_event.py`**
```python
from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..domain.enums import Confidence, EventType
from ..domain.models import WorldEvent
from ..infrastructure.database import Database
```

**`repo_audit.py`**
```python
from __future__ import annotations

from typing import Any

from ..infrastructure.database import Database
```

**`sqlite_repository.py`（主体）** — 见 §3.1（`HistoryConfig` + `Clock`/`Database` + 7 mixin import + `_SECONDS_PER_DAY`）。

> 注：`insert_event` 只引用 `e.event_type.value` / `e.confidence.value`（实例属性），不需 import `EventType`/`Confidence`；但同文件 `list_events` 需 `EventType(...)`/`Confidence(...)` 构造，故 `repo_event.py` import 两者。`sqlite3` 仅 `insert_event` 的 `IntegrityError` 用。

---

## 6. 硬约束

1. **逐字搬（方法体）**：每个方法体（含 docstring、方法内注释、空行）从原文件字节级复制到目标文件，不改一字。方法在目标文件内保持原文件相对顺序（便于 diff 审阅"搬移=纯移动"）。段头注释与 docstring 的处置见下第 6、7 条。
2. **零行为变化**：现有全部 repository 测试（`repository_sessions_test` / `repository_mode_transfer_test` / 及所有经 Repository 的集成测试）保持全绿。全库 1195 passed / 1 skipped 不变。
3. **mypy 不增违规**：`python -m mypy palworld_terminal/` 仍 `Success`，文件数增至 ~58（+7 mixin）。
4. **ruff 全绿**：`ruff check .`（全仓，含 tests）通过——imports 精确、无 F401、isort 有序。
5. **golden 间接锚定**：Repository 不直接进 golden .txt，但所有经它的读命令 golden 全过 = 行为等价的端到端证据。
6. **按 §4 名字清单抽取，不按连续源码范围切**：真码方法**物理交错**——`purge_server_data`（留主体）夹在 `clear_all_group_servers` 与 `get_binding_active`（均 routing）之间、audit 三方法夹在 world 簇与 metrics 簇之间。实现须按 §4 方法名逐个抽取，**绝不能剪一段连续源码搬**，否则会误把 `purge`/`prune`/`_PURGE_WORLD_TABLES` 拖进 mixin。
7. **段头注释与 docstring**：原文件 `# ---- servers ----` 等段头注释随其方法簇迁入对应 mixin；每个 mixin 与主体写**新的**模块/类 docstring 说明其表族职责；原文件顶部过时的 "Phase 1…" 模块 docstring 丢弃（不搬）。

---

## 7. 新增守卫：`repository_split_guard_test`

`tests/unit/repository_split_guard_test.py`，锚定拆分完整性与 mixin 隔离。三条断言，配方钉死到实现者可照抄：

1. **方法集完整性（57 一个不多不少）**：用**类级**内省取实际方法集，避免实例内省把非方法属性算进来（`dir(instance)` 会带进 `_db`/`_clock`/`_PURGE_WORLD_TABLES`；`iscoroutinefunction` 又会漏掉同步 staticmethod `_row_to_session`）：
   ```python
   import inspect
   actual = {n for n, _ in inspect.getmembers(Repository, inspect.isfunction)
             if not n.startswith("__")}
   ```
   `inspect.isfunction` 在**类**上取：实例属性 `_db`/`_clock`（Database/Clock 实例）与 `_PURGE_WORLD_TABLES`（tuple）天然不在其中；staticmethod `_row_to_session` 是 `isfunction` → **正确纳入**。期望集 = §4 全表 57 个方法名的字面量集合（**含单下划线的 `_row_to_session`**，排除 `_db`/`_clock`/`_PURGE_WORLD_TABLES`），在测试里硬编码为唯一真相源。断言 `actual == expected`（缺 → 搬漏，多 → 意外新增/重复）。**切勿用 `not n.startswith("_")` 过滤**——会连带砍掉 `_row_to_session` 得 56≠57 假红。
2. **mixin 互不 import**：glob `adapters/repo_*.py`（**天然排除主体 `sqlite_repository.py` 与既有 `metadata_repository.py`**——二者文件名不匹配 `repo_*.py`）逐文件读源码，断言不出现子串 `from .repo_` / `import palworld_terminal.adapters.repo_`。主体 `sqlite_repository.py` 合法 import 全部 7 mixin，但不在此 glob 内，不被误判。
3. **端口结构化满足（运行时兜底）**：断言组合后的 `Repository` 具备 4 端口全部方法。**硬编码**各端口方法名清单（`typing.Protocol` 的成员内省需私有 API `__protocol_attrs__`、跨版本不稳，故不 introspect）：Read 17 / Write 2 / Routing 5 / Audit 2（全部列于 `application/ports.py`），逐个 `hasattr(repo, m)`。注意**端口分组 ≠ mixin 分组**：如 `AuditRepositoryPort` 的 `get_current_world` 落在 `_WorldMetricRepo`、`insert_audit` 落在 `_AuditRepo`——两者经继承都在 `Repository` 上，这正是"结构化满足与表族拆分无关"的具体证据。mypy 静态已校验，此为运行时冗余防线。

---

## 8. 测试策略

- **等价性**：靠现有 repository 套件 + 全库 1195 测试（真 sqlite 实例，覆盖 CRUD/事务/迁移）。拆分是纯移动，任何行为漂移都会在这些测试转红。
- **完整性**：靠 §7 新守卫锚定"57 方法一个不多不少"。
- **隔离性**：靠 §7 守卫锚定 mixin 零互相依赖。
- **无新增行为测试**：本 Spec 不引入新行为，故不写行为测试；只加结构守卫。

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 搬 mixin 时漏搬某方法 → 运行时 `AttributeError` | §7 守卫方法集断言（缺一即红）+ 全库 1195 测试（漏搬必炸调用点） |
| import 遗漏（漏 import 用到的符号）| mypy `name-defined` / 运行时 `NameError`（测试炸） |
| import 多余（搬后不再用）| ruff `F401` 转红 |
| 漏声明 `self._clock` 自类型 | mypy `attr-defined` 转红 |
| MRO 顺序影响方法解析 | 零跨 mixin 同名方法（§2 核查）→ MRO 顺序不影响任何解析；顺序仅为可读性 |
| 跨表原子事务被拆散 | `purge`/`prune` 留主体、直接 `self._db.write_tx()`，单事务原子性不受影响 |
| ruff isort 排序错误 | §5 已预排；`ruff check .` 兜底 |
| 触发现有 layering 守卫回归 | `layering_guard_test`/`adapter_layering_guard_test` 仅扫 `application/*.py`，新增 `adapters/repo_*.py` 在扫描范围外，不回归 |

---

## 10. 交付形态

- **新增 7 文件**：`adapters/repo_routing.py` · `repo_player_binding.py` · `repo_world.py` · `repo_player_profile.py` · `repo_guild_base.py` · `repo_event.py` · `repo_audit.py`
- **改 1 文件**：`adapters/sqlite_repository.py` 从 900 行 god 类 → ~130 行组合主体（`__init__` + 2 跨表方法 + 常量 + 7 mixin 组合）。
- **新增 1 测试**：`tests/unit/repository_split_guard_test.py`
- **零改动**：`container.py`、`application/ports.py`、所有 service、所有调用点、所有现有测试。
- **验收**：`ruff check .` + `python -m mypy palworld_terminal/`（Success，~58 文件）+ 全库 `pytest -q`（1195 passed / 1 skipped + 新守卫）+ 前端不受影响。
