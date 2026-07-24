# QueryService god 类拆解：Mixin + 隐私基座（工程化 Spec ②）

**日期**：2026-07-24
**分支**：`feat/query-service-split`（叠于 main @ v1.1.0 @ `86e15ce`）
**类型**：纯结构重构，零行为变化，**不 bump 版本**
**前序**：架构解耦三部曲 A/B/C（PR #29/#32/#31）+ Spec D（PR #33，Repository god 类拆 7 mixin）已合并 main v1.1.0。本 Spec 是三部曲收尾评估揪出的**第二大 god 类**、与 Spec D 同套路的实现层拆分。

---

## 1. 背景与目标

三部曲 + Spec D 解决了**跨层耦合**（application 对 presentation/adapters 反向依赖 = 0）与**最大 god 类**（`sqlite_repository.py` 900→106 行）。收尾评估揪出**第二大巨类**：

- **`application/query_service.py` = 730 行 / 单个 `QueryService` 类 / 31 方法（30 非 `__init__` + `__init__`）**，全库第二大文件，纯读查询 god 对象。
- 与 Repository 不同，`QueryService` 有一条**跨组共享脊柱**：三个隐私方法（`load_excluded_keys` / `name_banned` / `resolve_event_subjects`）被 status/guild/events/players 四组的方法经 `self` 调用——这是**本质耦合**，不是可消除的坏味道。

**目标**：沿查询关注点把 `QueryService` 拆成 **5 个 mixin（各一文件）+ 1 个中立 `query_support.py`**，主类多重继承组合为**门面**。**零行为变化、零字节方法体（逐字搬）、全站零改动、外部 import 路径全保留**。

**为什么选 Mixin + 隐私基座（而非门面委派）**：`QueryService` 的跨组协作走一条共享脊柱（隐私三方法）。Mixin 单实例天然让 `self.load_excluded_keys()` 经 MRO 解析到脊柱；门面委派则需把脊柱注入每个子单元、或让子单元互相持有引用，更繁。脊柱本质耦合 → mixin 是最小改动路径。（此决策用户已拍板，勿重议。）

**非目标（YAGNI）**：
- 不改任何查询逻辑、SQL、缓存键、方法签名/行为。
- 不改 `application/ports.py`（消费者契约 `ReadRepositoryPort` 不动）。
- 不改任何调用点（`container.py` / `read_commands.py` / `Commands` 的 `self._query.X()` 全不变）。
- 不改 `container.py` 装配（唯一构造点 `QueryService(...)` 9 参数不变）。
- 不动 `dtos.py`（`event_view` / `EventView` / 各 DTO 定义留原处，mixin import 消费）。
- 不改任何 DTO 定义（`PlayerProfileDTO`/`RankBoardsDTO` 仅**物理迁**到 `query_support.py`，字段字节不变）。
- 不重命名任何 public 方法、不改 help/golden 输出。

---

## 2. 现状锚点（重构前必须为真，已逐条独立核实）

| 事实 | 值 | 来源（行号已核实） |
|---|---|---|
| `QueryService` 类 | 单类，`__init__`（9 参）+ 30 方法 | query_service.py:129 |
| `__init__` 签名 | `(self, repo, cache, cfg, meta, clock, settings_cache, world_cache=None, report=None, info_cache=None)` | :134-137 |
| `__init__` 赋值属性 | `_repo`/`_cache`/`_cfg`/`_meta`/`_clock`/**`_settings_cache`**/`_world_cache`/`_report`/**`_info_cache`** | :138-146 |
| **属性名纠正** | 真码是 `self._settings_cache`（非 `_settings`）与 `self._info_cache`（非 `_info`）——手册 §3 简写有误 | :143,146 已核实 |
| 类级常量（TTL） | `_GUILDS_TTL=90` / `_BASES_TTL=90` / `_EVENTS_TTL=15`，全部经 `self._X_TTL` 访问 | :130-132 |
| 模块级常量/符号（8） | `_STATUS_TTL`/`_ONLINE_TTL`/`metric_stale`/`_STATUS_RULE_FIELDS`/`_RULES_SECTIONS`/`_fmt_rules_num`/`PlayerProfileDTO`/`RankBoardsDTO` | :31-126 |
| 隐私脊柱三方法 | `load_excluded_keys`:575 / `resolve_event_subjects`:581 / `name_banned`:664 | 已核实 |
| `event_view(` 调用点 | **仅 2 处**：`_guild_recent_events`:378、`events`:472 | grep 核实 |
| `_GUILD_BASE_EVENTS` | 类级元组 `(EventType.NEW_BASE, WORKER_DELTA, BASE_VANISHED)`，**类定义期求值**（需运行时 `EventType`）| :361，用于 :373 |
| monkeypatch seam | **无**——测试构造真 `QueryService` 实例（非 mock 方法/属性） | 手册接口勘探（agentId a1ba25c1） |
| 端口满足方式 | 结构化（duck typing），无继承声明 | ports.py |

**外部 import 路径消费者（全部保留，零改动）**：
| 消费者 | 从 `query_service` import | 处置 |
|---|---|---|
| `container.py:19` | `QueryService`（类） | 门面保留同名同模块 → 有效 |
| `presentation/commands.py:10` | `metric_stale` | 门面 re-export |
| `presentation/formatters.py:16` | `PlayerProfileDTO, RankBoardsDTO` | 门面 re-export |
| `tests/*`（9 文件） | `QueryService` / `metric_stale` / `PlayerProfileDTO` / `RankBoardsDTO` / `_STATUS_RULE_FIELDS` | 门面 re-export 4 符号 + 保留类 |
| `output_consistency_test.py:15` | `query_service`（**整模块**，getsource 护栏） | 见 §8.1 护栏升级 |

**须门面 re-export 的最小集 = 4**：`metric_stale` / `PlayerProfileDTO` / `RankBoardsDTO` / `_STATUS_RULE_FIELDS`（`QueryService` 类本身留门面，天然有效）。

---

## 3. 拆分方案：Mixin 组合 + 隐私基座

### 3.1 门面（主类）组合形态

```python
# application/query_service.py（门面，~40 行）
from __future__ import annotations

from ..config import AppConfig
from ..infrastructure.cache import TTLCache
from ..infrastructure.clock import Clock
from .ports import ReadRepositoryPort
from .query_events import _EventSummaryQueries
from .query_guild import _GuildBaseQueries
from .query_players import _RankProfileQueries
from .query_status import _StatusQueries
# 保外部 import 路径（门面 re-export，见 §6）——冗余别名规避 ruff F401：
from .query_support import PlayerProfileDTO as PlayerProfileDTO
from .query_support import RankBoardsDTO as RankBoardsDTO
from .query_support import _STATUS_RULE_FIELDS as _STATUS_RULE_FIELDS
from .query_support import metric_stale as metric_stale


class QueryService(
    _StatusQueries,
    _GuildBaseQueries,
    _EventSummaryQueries,
    _RankProfileQueries,
):
    """读查询门面。实现按查询关注点拆入 5 个 mixin（query_*.py）；隐私三方法
    （load_excluded_keys/name_banned/resolve_event_subjects）为跨组共享脊柱，
    落 _PrivacyBase，**四查询 mixin 均继承 _PrivacyBase**，跨组调用经 self/MRO
    解析到脊柱（门面只列四 mixin，_PrivacyBase 由它们传递继承）。模块级
    helper/DTO/常量迁中立 query_support.py。"""

    _GUILDS_TTL = 90
    _BASES_TTL = 90
    _EVENTS_TTL = 15

    def __init__(
        self, repo: ReadRepositoryPort, cache: TTLCache, cfg: AppConfig, meta, clock: Clock,
        settings_cache, world_cache=None, report=None, info_cache=None,
    ) -> None:
        self._repo = repo
        self._cache = cache
        self._cfg = cfg
        self._meta = meta
        self._clock = clock
        self._settings_cache = settings_cache
        self._world_cache = world_cache if world_cache is not None else {}
        self._report = report
        self._info_cache = info_cache if info_cache is not None else {}
```

- **脊柱作共享基类（关键·经实测）**：四查询 mixin **各继承 `_PrivacyBase`**（`class _StatusQueries(_PrivacyBase): ...`，每个非脊柱 mixin 模块 `from .query_privacy import _PrivacyBase`）。**这是硬约束不是风格选择**：非脊柱 mixin 内 `self.resolve_event_subjects()`/`self.load_excluded_keys()`/`self.name_banned()` 跨组调用，mypy 按 mixin 类**单独**检查——若 mixin 只继承 `object`，脊柱方法不可见 → `attr-defined` 转红（已用隔离 scratch 复现：`"_MixinEvents" has no attribute "resolve..."`）。令非脊柱 mixin 继承脊柱即让 mypy 解析这些调用。
- **MRO 一致（钻石·经实测）**：四 mixin 共享 `_PrivacyBase` 尾基 → 钻石继承，C3 线性化干净：`QueryService → _StatusQueries → _GuildBaseQueries → _EventSummaryQueries → _RankProfileQueries → _PrivacyBase → object`。四 mixin 各自方法集 + 脊柱三方法**全互不重叠**（disjoint）→ MRO 顺序不影响任何方法解析（顺序仅可读性）。已用隔离 scratch 跑 mypy `Success` + ruff 全绿 + 运行时 MRO/TTL 解析 OK 三向验证本形态。
- mixin **不定义 `__init__`**（纯行为混入、无自身状态）；门面 `__init__` 唯一设全部 `self._` 属性、无需 `super().__init__()`（仅跳过 no-op `object.__init__`，与原类一致）。门面**只列四查询 mixin**，`_PrivacyBase` 经它们传递继承（不重复列，避免与 mixin 已含的 `_PrivacyBase` 造 MRO 冗余）。
- `__init__` 签名 **9 参逐字节不变**（`(repo, cache, cfg, meta, clock, settings_cache, world_cache=None, report=None, info_cache=None)`），保 7 处直接构造 + `container.py:137` 装配等价。

### 3.2 类级 TTL 常量归属（决策：留门面 + mixin 注解声明）

`_GUILDS_TTL`/`_BASES_TTL`/`_EVENTS_TTL` 经 `self._X_TTL` 访问（非裸名），故**必须留作可经 self/MRO 解析的类属性**（不能迁 `query_support` 变裸名——那是字节改动）。**值留门面**（组合根，逐字保留 :130-132）；引用它的 mixin 加**纯注解声明**（`_X_TTL: int`）令 mypy 解析：

| 常量 | 值持有 | 引用它的 mixin（加 `: int` 注解声明） | 访问点 |
|---|---|---|---|
| `_GUILDS_TTL` | 门面 | `_GuildBaseQueries` | guilds:321, guild:355 |
| `_BASES_TTL` | 门面 | `_GuildBaseQueries` **且** `_EventSummaryQueries`（共享） | bases:405 / world_summary:563 |
| `_EVENTS_TTL` | 门面 | `_EventSummaryQueries` | events:473 |

> **为何值留门面而非迁 mixin**：`_BASES_TTL` 被两 mixin 共用；若值放某一 mixin，则另一 mixin 经 MRO 依赖它 = leaf-to-leaf 耦合，违背「脊柱是唯一跨切点」。值留组合根消除该耦合。注解声明不建运行时属性、不与门面赋值冲突（标准 mixin 惯用法）。

### 3.3 隐私脊柱与 `_GUILD_BASE_EVENTS`

- **脊柱 `_PrivacyBase`**：`load_excluded_keys`/`name_banned`/`resolve_event_subjects` 三方法，声明自类型 `_repo: ReadRepositoryPort` + `_cfg: AppConfig`。四查询 mixin **继承本类**，跨组调用经 `self.X()` 由 MRO 解析到脊柱（§3.1）。`resolve_event_subjects`:588 内调 `self.load_excluded_keys`（同类，经自身 MRO）。
- **`_GUILD_BASE_EVENTS`**（:361）：类级元组，**类定义期求值**（真 tuple 值，非注解），故 `EventType` 须为 `_GuildBaseQueries` 的**运行时** import（虽 `EventType` 在该 mixin 别处不出现）。随其唯一消费方法簇（`_guild_recent_events`）迁入 `_GuildBaseQueries`，作类体属性。

### 3.4 mixin 自类型声明（mypy 惯用法）

mixin 引用 `self._X` 属性但不赋值（门面 `__init__` 赋）。用**纯类型注解**告知 mypy（零运行时开销）。**规则**：`_repo`/`_cfg` 声明在**脊柱** `_PrivacyBase`，四查询 mixin 继承脊柱 → **自动获得**（直接 `self._repo`/`self._cfg` 访问经继承注解解析，已实测；**非脊柱 mixin 不重复声明** `_repo`/`_cfg`）。每查询 mixin 只**额外**声明它引用的非脊柱属性（`_cache`/`_clock`/`_meta`/…）。漏声明 → mypy `attr-defined` 转红（安全网）。

**关键**：`_meta`/`_settings_cache`/`_world_cache`/`_report`/`_info_cache` 在 `__init__` 中**无类型注解**（隐式 `Any`）→ mixin 一律声明为 `Any`。这既**字节忠实**（保持当前有效 mypy 类型），又**必需**：若给 `_meta` 标 `MetadataRepository` 会引入 `application→adapters` import，炸 `adapter_layering_guard_test`。`Any` 需 `from typing import Any`。

| 属性 | 类型注解 | 声明位置 |
|---|---|---|
| `_repo` | `ReadRepositoryPort` | **脊柱 `_PrivacyBase`**（四 mixin 继承，不重声明） |
| `_cfg` | `AppConfig` | **脊柱 `_PrivacyBase`**（四 mixin 继承，不重声明） |
| `_cache` | `TTLCache` | status / guild / events（各自额外声明） |
| `_clock` | `Clock` | status / events / players |
| `_meta` | `Any` | status / events |
| `_settings_cache` | `Any` | status / events |
| `_world_cache` | `Any` | events |
| `_report` | `Any` | events |
| `_info_cache` | `Any` | status |

> `_repo`/`_cfg` 只在脊柱声明一次，四 mixin 经继承共享（DRY，避免跨 base 重声明）。其余属性各 mixin 按实际引用额外声明；同一属性在多 mixin 声明须**同一类型**（如 `_cache: TTLCache`），否则 mypy 报 base 不兼容——故 `_meta` 等一律 `Any`（不混用具体类型）。整形态已用隔离 scratch（含非脊柱 mixin 直接 `self._repo`/`self._cfg` 访问 + 跨组 `self.spine()` 调用）跑 mypy `Success` 验证。

---

## 4. 方法归属（30 方法 + 8 模块符号完整分配，防搬漏/搬重）

### 4.1 `_PrivacyBase`（脊柱，隐私敏感）→ `query_privacy.py`（3 方法）
`load_excluded_keys`:575 · `resolve_event_subjects`:581 · `name_banned`:664

### 4.2 `_StatusQueries` → `query_status.py`（8 方法）
`_smoothness_label`:148 · `_online_rows`:158（组内 helper，2 跨脊柱调用）· `status`:193 · `_server_address`:235 · `_config_server_name`:241 · `_status_rules`:249 · `_build_status_detail`:261 · `online`:274

### 4.3 `_GuildBaseQueries` → `query_guild.py`（8 方法 + `_GUILD_BASE_EVENTS`）
`_health_score`:295（`@staticmethod`，迁后保装饰器；`self._health_score(obs)` 经 MRO 不变）· `_base_counts_by_guild`:299 · `guilds`:307 · `guild`:324 · `_guild_recent_events`:363 · `_bases_indexed`:380（组内 helper）· `bases`:387 · `base`:408
- 携类级 `_GUILD_BASE_EVENTS`:361（+ 前置说明注释）；`_GUILDS_TTL`/`_BASES_TTL` 注解声明。

### 4.4 `_EventSummaryQueries` → `query_events.py`（5 方法）
`events`:448（隐私敏感）· `_render_rule_value`:476（普通实例方法，非 staticmethod）· `rules`:494 · `world_summary`:526 · `today`:566
- `_EVENTS_TTL`/`_BASES_TTL` 注解声明。

### 4.5 `_RankProfileQueries` → `query_players.py`（6 方法）
`_converge_by_name`:591（不用 self，但**保 `self` 参**以字节保调用点 :629/:646）· `rank`:606 · `_profile_extras`:671 · `_build_profile`:696（组内 helper）· `player_profile`:710 · `profile_for_key`:721

### 4.6 中立 `query_support.py`（8 模块级符号，非方法）
`_STATUS_TTL`:31 · `_ONLINE_TTL`:32 · `metric_stale`:35 · `_STATUS_RULE_FIELDS`:46 · `_RULES_SECTIONS`:61 · `_fmt_rules_num`:92 · `PlayerProfileDTO`:104 · `RankBoardsDTO`:122
- 8 符号**互不依赖**；模块只需 `from dataclasses import dataclass, field`（+ `from __future__ import annotations`）。携各自前置注释块逐字迁。

### 4.7 门面 `QueryService`（组合，无查询方法）
`__init__` + 3 TTL 类常量 + 组合 4 查询 mixin（`_PrivacyBase` 经它们传递继承）+ re-export 4 符号。

**合计**：3+8+8+5+6 = **30 方法**迁 mixin，+`__init__` 留门面 = **31**。✓ 8 模块符号迁 `query_support`。3 TTL 常量留门面。

---

## 5. 每 mixin 的 imports（精确分配，ruff isort 预排）

> ruff `I`/`F401` 抓排序错与未用 import；每 mixin 只 import 实际用到的符号，已按 isort（`__future__`→stdlib→`..` 一级→`.` 同级）预排。`from __future__ import annotations` 令所有注解字符串化（仅 mypy 需可解析，运行时不 eval）；ruff 仍视注解内符号为「已用」。**最终排序以 `ruff check --fix` 钉死；本节为实现起点 + 复核基准。**

**`query_privacy.py`**（脊柱）
```python
from __future__ import annotations

from ..config import AppConfig
from ..domain.models import World, WorldEvent
from .name_resolver import resolve_subjects
from .name_resolver import load_excluded_keys as _load_excluded_keys
from .ports import ReadRepositoryPort
```
自类型：`_repo: ReadRepositoryPort` · `_cfg: AppConfig`
> `keep_world_subject_under_strict`（原 query_service.py:26 import）**不属脊柱**（仅 events 用）→ 不 import 进脊柱。别名 `load_excluded_keys as _load_excluded_keys` 逐字保留（原 :27）。

**`query_status.py`** — `class _StatusQueries(_PrivacyBase):`
```python
from __future__ import annotations

from typing import Any

from ..domain.models import World
from ..infrastructure.cache import TTLCache
from ..infrastructure.clock import Clock
from .dtos import OnlineDTO, OnlinePlayerRow, StatusDetailDTO, StatusDTO
from .query_privacy import _PrivacyBase
from .query_support import _ONLINE_TTL, _STATUS_RULE_FIELDS, _STATUS_TTL, metric_stale
from .report_service import day_bounds
```
自类型（额外，`_repo`/`_cfg` 继承脊柱）：`_cache: TTLCache` · `_clock: Clock` · `_meta: Any` · `_settings_cache: Any` · `_info_cache: Any`
> 继承 `_PrivacyBase` → `self._repo`/`self._cfg` 直接访问经继承注解解析（已实测），故**不** import `ReadRepositoryPort`/`AppConfig`（二者全库仅 `__init__` 用，留门面）。`day_bounds` 自 `.report_service`（application 同层自由函数，status:204/online:285 用）——无新循环（report_service 不反向 import query_*）。`_STATUS_TTL`/`_ONLINE_TTL` 原为裸名访问（:232/:292）→ 迁 query_support 后 import 裸名，字节不变。

**`query_guild.py`** — `class _GuildBaseQueries(_PrivacyBase):`
```python
from __future__ import annotations

from ..domain.enums import EventType
from ..domain.models import Base, BaseObservation, World
from ..infrastructure.cache import TTLCache
from .dtos import (
    BaseDetailDTO,
    BaseDTO,
    EventView,
    GuildDetailDTO,
    GuildDTO,
    event_view,
)
from .query_privacy import _PrivacyBase
```
自类型（额外，`_repo` 继承脊柱）：`_cache: TTLCache`（+ 注解 `_GUILDS_TTL: int` · `_BASES_TTL: int`）
> 继承 `_PrivacyBase` → **不** import `ReadRepositoryPort`（`self._repo` 经继承解析）。`EventType` 为 `_GUILD_BASE_EVENTS`（类定义期求值）所需**运行时** import。`event_view`/DTO 类均运行时构造（:378），须真 import。`self.resolve_event_subjects`(:377) 经继承脊柱解析。

**`query_events.py`** — `class _EventSummaryQueries(_PrivacyBase):`
```python
from __future__ import annotations

from typing import Any

from ..domain.models import World
from ..infrastructure.cache import TTLCache
from ..infrastructure.clock import Clock
from .dtos import (
    EventView,
    RulesDTO,
    RuleSection,
    WildTopRow,
    WorldSummaryDTO,
    event_view,
)
from .name_resolver import keep_world_subject_under_strict
from .query_privacy import _PrivacyBase
from .query_support import _RULES_SECTIONS, _fmt_rules_num
from .report_service import day_bounds
```
自类型（额外，`_repo`/`_cfg` 继承脊柱）：`_cache: TTLCache` · `_clock: Clock` · `_meta: Any` · `_settings_cache: Any` · `_world_cache: Any` · `_report: Any`（+ 注解 `_EVENTS_TTL: int` · `_BASES_TTL: int`）
> 继承 `_PrivacyBase` → **不** import `ReadRepositoryPort`/`AppConfig`（`self._repo`/`self._cfg` 经继承解析）。`keep_world_subject_under_strict`（:461，strict 下 world-only 过滤）仅此 mixin 用。`resolve_event_subjects`/`load_excluded_keys`/`resolve_subjects` **不** import——名字解析全经 `self.resolve_event_subjects`（继承脊柱）。

**`query_players.py`** — `class _RankProfileQueries(_PrivacyBase):`
```python
from __future__ import annotations

from ..domain.models import PlayerIdentity, World
from ..infrastructure.clock import Clock
from .query_privacy import _PrivacyBase
from .query_support import PlayerProfileDTO, RankBoardsDTO
from .report_service import day_bounds
```
自类型（额外，`_repo`/`_cfg` 继承脊柱）：`_clock: Clock`
> 继承 `_PrivacyBase` → **不** import `ReadRepositoryPort`/`AppConfig`（`self._repo`/`self._cfg` 经继承解析）。仅构造 `PlayerProfileDTO`/`RankBoardsDTO`（不定义，故无 `dataclass` import）。`day_bounds` 用于 rank:613/`_profile_extras`:678。`self.load_excluded_keys`/`self.name_banned`（:607/:716/:717）经继承脊柱解析。

**`query_support.py`**（中立）
```python
from __future__ import annotations

from dataclasses import dataclass, field
```
> `field` 仅 `RankBoardsDTO.total_rows` 的 `default_factory=list` 用；`dataclass` 两 DTO 用。函数/常量元组零 import。

**`query_service.py`**（门面）— 见 §3.1。

---

## 6. 门面 re-export（保外部 import 路径 + F401 规避）

模块级 `metric_stale`/`PlayerProfileDTO`/`RankBoardsDTO`/`_STATUS_RULE_FIELDS` 迁至 `query_support.py`，但外部消费者仍 `from ...query_service import X`（§2 表）。门面 import 这 4 符号但**本地不使用** → 触发 ruff `F401`。

**本仓无现成 F401 规避惯用法可抄**（勘探证实：`config.py` 的 `PrivacyConfig` re-export 因**真本地用**而非 F401 技巧；全仓零 `# noqa: F401`/零 `__all__`/零冗余别名）。故引入新惯用法。

**决策：冗余别名 `X as X`**（PEP 484 显式 re-export 约定，ruff 0.15.21 实测抑制 F401，且同时满足 mypy re-export 语义）。因本仓未设 `combine-as-imports`（默认 `false`），ruff isort 会把多别名括号块**拆成每符号一 `from` 语句**，故按 ruff 规范形直接写四行（见 §3.1）：
```python
from .query_support import PlayerProfileDTO as PlayerProfileDTO
from .query_support import RankBoardsDTO as RankBoardsDTO
from .query_support import _STATUS_RULE_FIELDS as _STATUS_RULE_FIELDS
from .query_support import metric_stale as metric_stale
```
- **ruff 配置事实**（`pyproject.toml`）：`select = ["E","F","W","I","B","UP"]`（F401 开），`per-file-ignores` 仅 `tests/** = [E501,E702]`（F401 不豁免，全仓 `ruff check .` 覆盖门面）。
- 排序以 `ruff check --fix` 钉死（按成员名/order-by-type）。
- **备选（不采用）**：`__all__` 列表——亦过 ruff，但破本仓零 `__all__` 惯例且把私有名塞进 `__all__`，不如冗余别名自文档。

---

## 7. 硬约束

1. **逐字搬（方法体/符号体）**：每方法体、每模块符号定义（含 docstring、内注释、空行、前置注释块）字节级复制到目标文件，不改一字。方法在目标文件内保持原相对顺序（便于 diff 审「搬移=纯移动」）。
2. **零行为变化**：现有全部 query 测试（`query_service_status/bases/players/rules_test`、`rank_total_test`、`status_detail_shape_test`、经 QueryService 的命令/格式化集成测试）保持全绿。全库 **1198 passed / 1 skipped**（当前基线，已核）不变；+新守卫 3 条 → 终 1201 passed。
3. **golden 间接锚定**：QueryService 不直接进 golden .txt，但所有经它的读命令 golden（status/online/guild/events/today/rank/player/rules）全过 = 行为等价的端到端证据。
4. **mypy 全绿**：`.venv/Scripts/python.exe -m mypy palworld_terminal/` 仍 `Success`，文件数从当前 58 增至 64（+6 新模块：5 mixin + query_support）。
5. **ruff 全绿**：`ruff check .`（**全仓含 tests**）通过——imports 精确、无 F401、isort 有序、门面 re-export 冗余别名不报 F401。
6. **按 §4 名字清单抽取，不按连续源码范围切**：真码方法**物理交错**（脊柱三方法 :575/:581/:664 夹在 rank/profile 簇之间；`_render_rule_value`:476 在 events:448 与 rules:494 之间）。实现须按 §4 方法名逐个抽取，**绝不剪连续源码段搬**，否则误把邻组方法/常量拖入错 mixin。
7. **段头注释与 docstring**：原文件段头注释随方法簇迁对应 mixin；每 mixin 与门面写**新的**模块/类 docstring 说明其查询职责；`query_support.py` 写中立模块 docstring。模块级符号的前置注释块（如 `_STATUS_RULE_FIELDS` 的 :44-45、`_RULES_SECTIONS` 的 :53-60）随符号迁 `query_support`。
8. **行尾 LF**：`query_service.py` 及全部新模块（5 mixin + query_support）+ 改动的测试文件一律 **LF**（本文件族无 CRLF 陷阱）。
9. **不 bump 版本**：纯重构，v1.1.0 不动（六版本源不改）。
10. **隐私不减强**：§8.1 护栏升级后，`event_wording` 缺失（∀ 全 query_* + report_service）+ `event_view(` 仍用（∃ 跨拆分模块）两不变量强度**不减**（详见 §8.1 对抗论证）。

---

## 8. 护栏：升级现有 + 新增守卫

### 8.1 升级 `output_consistency_test`（方案 A，隐私敏感）

**为何必须升级**：现护栏（:15、:63-72）对 `query_service` **整模块** `inspect.getsource` 扫两不变量。拆分后 `event_view(` 迁出（→ `query_guild.py`:378、`query_events.py`:472），门面 `query_service.py` 不再含 `event_view(`：
- **假红**：:66 `assert "event_view(" in src` 对门面失败（门面已无该调用）。
- **假绿（隐私漏洞）**：新 `query_events.py`/`query_guild.py` 若泄漏 `event_wording` 或 re-inline 措辞，**不被扫到**——预措辞串可无声重入 application 查询层。

**升级配方（钉死）**：把「扫单模块 `query_service`」升级为「动态发现全部 `query_*` 模块」，两不变量按**量词语义**分治：
- **(a) `event_wording` 缺失 + 措辞不 re-inline**：**逐模块 ∀**，须对**每个** `query_*` 模块 + `report_service` 成立 → 留循环内，迭代全发现集。
- **(b) `event_view(` 被用**：**跨并集 ∃**，须在 `query_*` 全体中**某处**成立 → 移出循环，聚合断言 `any(...)`，否则对合法无 `event_view` 的门面/query_players/query_status/query_privacy/query_support 假红。

**替换 :15**（改动态发现）：
```python
import importlib
import pkgutil

from palworld_terminal import application as _application_pkg
from palworld_terminal.application import report_service
from palworld_terminal.presentation import event_wording as event_wording_module
from palworld_terminal.presentation import formatters as formatters_module


def _query_modules():
    """application 包内所有 query_* 模块（含未来新增，防漂移自动覆盖）。"""
    mods = []
    for info in pkgutil.iter_modules(_application_pkg.__path__):
        if info.name.startswith("query_"):
            mods.append(importlib.import_module(f"{_application_pkg.__name__}.{info.name}"))
    return mods
```
**替换 :63-72 循环**：
```python
    query_mods = _query_modules()
    assert query_mods, "未发现任何 query_* 模块——discovery 失效将使护栏假绿"
    query_sources = {m.__name__: inspect.getsource(m) for m in query_mods}

    # (a) 每个 query_* + report_service：绝不引用 event_wording、绝不 re-inline 措辞（∀）。
    for name, src in {
        **query_sources,
        report_service.__name__: inspect.getsource(report_service),
    }.items():
        assert "event_wording" not in src, f"{name} 仍引用已废弃的 event_wording"
        code_strings = _code_string_literals(src)
        for frag in _WORDING_FRAGMENTS:
            assert frag not in code_strings, (
                f"{name} 代码内 re-inline 措辞 {frag!r}——八类措辞应唯一源自 "
                f"presentation.render_event（改词即漂移）"
            )

    # (b) event_view 单一构造入口在 query_* 全体中确被使用（∃，跨拆分模块）。
    assert any("event_view(" in src for src in query_sources.values()), (
        "query_* 全体未经 event_view 单一构造入口——措辞构造被绕过"
    )
    # report_service 未拆分，独立保留其自身 present-check（恒含 event_view）。
    assert "event_view(" in inspect.getsource(report_service)
```
- `:74`（`render_event(` in formatters）+ 第二测试 `test_formatters_delegate_textkit...` **不受影响，原样保留**。`_code_string_literals` helper + `_WORDING_FRAGMENTS` 不动。

**强度不减对抗论证**（隐私核心）：
- **(a) 覆盖面严格扩大**：旧只扫 `query_service` 1 模块；新扫 `query_events`/`query_guild`/`query_players`/`query_privacy`/`query_status`/`query_support`/`query_service` 7 个 + `report_service`。任一模块（含未来 `query_*` 新增）泄漏 `event_wording`/re-inline 措辞立即转红。**动态发现**杜绝硬编码清单的漏网。
- **旧绿 → 新绿等价性**：拆分是**字节搬**——原 monolith 的 code-string 并集 = 拆分后各模块 code-string 并集。旧护栏证明并集无措辞片段 ⟹ 每子集无 ⟹ (a) 逐模块必过（无假红），且 `query_support` 的 `_RULES_SECTIONS` 中文串（"难度"/"经验"…）与 8 措辞片段无交集（已核）→ 过。
- **(b) 不弱化**：`event_view(` 现存于 `query_guild.py`+`query_events.py` → ∃ 成立。聚合而非丢弃该断言——保住「单一构造入口确被行使」的证明，仅从「每模块」放宽为「并集存在」（因门面等合法无此调用）。
- **空集防御**：`assert query_mods, ...` 阻止 discovery 失效致 ∀ 空过、∃ 退化。

### 8.2 新增守卫 `query_service_split_guard_test`

`tests/unit/query_service_split_guard_test.py`，锚定拆分完整性 + 脊柱隔离 + 构造契约。三条断言，配方钉死到实现者可照抄：

**断言 1 — 方法集完整性（30 一个不多不少）**：类级内省，避免实例内省带进 `_db` 等属性；`inspect.isfunction` 在类上取 async/sync/staticmethod 全纳、int 类常量与实例属性天然排除：
```python
import inspect
from palworld_terminal.application.query_service import QueryService

actual = {n for n, _ in inspect.getmembers(QueryService, inspect.isfunction)
          if not n.startswith("__")}
```
期望集 = §4 全 30 方法名字面量集合（**含单下划线 helper** `_smoothness_label`/`_online_rows`/`_server_address`/`_config_server_name`/`_status_rules`/`_build_status_detail`/`_health_score`/`_base_counts_by_guild`/`_guild_recent_events`/`_bases_indexed`/`_render_rule_value`/`_converge_by_name`/`_profile_extras`/`_build_profile`/`load_excluded_keys`/`resolve_event_subjects`/`name_banned`），硬编码为唯一真相源。`assert actual == expected`（缺→搬漏，多→意外新增/重复）。
> **切勿用 `not n.startswith("_")` 过滤**——会砍掉 14 个单下划线 helper 得 16≠30 假红（三脊柱方法 `load_excluded_keys`/`name_banned`/`resolve_event_subjects` **无前导下划线**、不受此过滤影响仍保留，故是 16 非 13）。断言本体用 `not n.startswith("__")`（**双**下划线，仅排除 dunder `__init__`）正确得 30。`_GUILDS_TTL`/`_BASES_TTL`/`_EVENTS_TTL`（int 类常量）非 function、天然不在 `isfunction` 集；`_GUILD_BASE_EVENTS`（tuple 类属性）同理排除。

**断言 2 — 脊柱是唯一跨切点（非脊柱 mixin 只调自身或脊柱方法）**：AST 扫每个 mixin 模块，收集 `self.<name>(...)` 直接调用（`func` 为 `Attribute(value=Name('self'), attr=name)`；`self._cache.set(...)` 这类 `func.value` 为 `Attribute` 不计入），断言调用名集 ⊆（该 mixin 自身方法名 ∪ 脊柱三方法）：
```python
import ast
SPINE = {"load_excluded_keys", "name_banned", "resolve_event_subjects"}
# 逐 query_{privacy,status,guild,events,players}.py：
#   own = {mixin 类内 def/async def 名}
#   calls = {self.NAME() 调用名}
#   assert calls <= (own | SPINE), f"{module} 跨组调用越出脊柱：{calls - own - SPINE}"
```
锁死「脊柱是唯一跨切点」：任何 leaf-to-leaf `self.method()` 调用（非脊柱、非自身）立即转红。脊柱自身 `own` 已含三方法 → 该断言对脊柱是无害超集（脊柱只调 `self.load_excluded_keys`=自身）。
> `own` 由 AST **只取类体直接 def/async def**（非脊柱 mixin 虽 `class _X(_PrivacyBase)` 继承脊柱，但 AST 不把继承方法算进 `own`）；非脊柱 mixin 调 `self.load_excluded_keys()` 等脊柱方法经 `SPINE` 集放行——这正锁死「跨组只经脊柱（继承而来），绝不 leaf-to-leaf」。类常量访问 `self._BASES_TTL`（`ast.Attribute` 非 `ast.Call`）不计入调用集，不误伤 §3.2 的跨门面常量解析。

**断言 3 — 门面构造契约不变**：
```python
import inspect
params = list(inspect.signature(QueryService.__init__).parameters)
assert params == ["self", "repo", "cache", "cfg", "meta", "clock",
                  "settings_cache", "world_cache", "report", "info_cache"]
```
锁 9 参名 + 顺序（保 7 处直接构造 + container 装配等价）。

---

## 9. 测试策略

- **等价性**：靠现有 query 套件 + 全库 1198 测试（真 QueryService 实例，覆盖 status/online/guild/base/events/today/rank/profile/rules 全读路径 + 隐私过滤 + 缓存 + 降级态）。拆分纯移动，任何行为漂移在这些测试转红。
- **隐私不减强**：§8.1 升级后护栏（∀ 全 query_* + report_service 无 event_wording/re-inline；∃ event_view 仍用）。**终审须对抗验证升级后强度不减**（§10 铁律）。
- **完整性/隔离性/契约**：§8.2 新守卫锚定「30 方法不多不少」+「脊柱唯一跨切点」+「构造签名不变」。
- **无新增行为测试**：本 Spec 零新行为，只加结构守卫 + 升级隐私护栏。

---

## 10. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 搬 mixin 漏搬某方法 → 运行时 `AttributeError` | §8.2 断言 1（缺一即红）+ 全库 1198 测试（漏搬必炸调用点） |
| import 遗漏用到的符号 | mypy `name-defined` / 运行时 `NameError`（测试炸） |
| import 多余（搬后不再用） | ruff `F401` 转红 |
| 漏声明 `self._X` 自类型 | mypy `attr-defined` 转红 |
| 跨 base `_meta` 等类型不一致 | §3.4 一律 `Any`；不一致则 mypy 报 base 不兼容 |
| **非脊柱 mixin 跨组 `self.spine()` 调用 mypy 不可见** → `attr-defined`（**已用 scratch 复现**） | 非脊柱 mixin **继承 `_PrivacyBase`**（§3.1/§3.3/§5，`class _X(_PrivacyBase)`）令 mypy 解析脊柱方法；隔离 scratch 已验 mypy `Success` |
| 钻石 MRO 不一致（四 mixin 共享脊柱尾基）| C3 线性化干净（`QueryService→…→_PrivacyBase→object`，已实测运行时 + mypy）；四 mixin + 脊柱方法集全 disjoint → 顺序不影响解析 |
| 门面 re-export 触发 F401 | §6 冗余别名（ruff 0.15.21 实测抑制）；`ruff check .` 兜底 |
| `_GUILD_BASE_EVENTS` 漏运行时 `EventType` import → 类加载 `NameError` | §5 query_guild.py 头含 `EventType`；import 后模块加载即炸测试 |
| `_BASES_TTL` 跨两 mixin 解析失败 | 值留门面（§3.2）+ 两 mixin 注解声明；mypy `attr-defined` 兜底 |
| 护栏升级弱化隐私强度 | §8.1 对抗论证 + §10 终审对抗验证；∀ 扩大、∃ 聚合、空集防御 |
| 现有 layering 守卫回归 | `layering_guard_test`/`adapter_layering_guard_test` 扫 `application/*.py` import；新 query_*.py 全 application 内、无 presentation/adapters import（§5 头已核）→ 不回归。**注**：新模块本身受这两守卫约束，须零 presentation/adapters import（已满足）。 |
| 护栏动态发现把 `query_service`/`query_support` 也纳入扫描 | 期望内且有益：门面/support 无 event_wording/措辞、(a) 过；(b) 靠 query_guild/events 满足 |

---

## 11. 交付形态

- **新增 6 文件**：`application/query_privacy.py`（脊柱）· `query_status.py` · `query_guild.py` · `query_events.py` · `query_players.py` · `query_support.py`（中立）
- **改 1 文件**：`application/query_service.py` 从 730 行 god 类 → ~40 行组合门面（`__init__` + 3 TTL 常量 + **4 查询 mixin 组合**（脊柱经它们传递继承）+ 4 re-export）。
- **升级 1 测试**：`tests/unit/output_consistency_test.py`（§8.1，动态发现全 query_* + 量词分治）。
- **新增 1 测试**：`tests/unit/query_service_split_guard_test.py`（§8.2 三断言）。
- **零改动**：`container.py`、`application/ports.py`、`dtos.py`、`name_resolver.py`、`report_service.py`、`presentation/*`（commands/formatters 的 import 路径经 re-export 保留）、所有 service、所有现有 query/命令测试。
- **验收**：`ruff check .` + `.venv/Scripts/python.exe -m mypy palworld_terminal/`（Success，64 文件）+ 全库 `pytest -q`（1201 passed / 1 skipped：1198 基线 + 3 守卫）+ 前端不受影响。
- **不 bump**：v1.1.0 不动。

---

## 12. 执行结构（供 plan/SDD 参考，同 Spec D「additive → 原子切换」）

1. **T1**：建 `query_support.py`（迁 8 模块符号，逐字）——additive，门面暂仍持原符号（过渡共存）。
2. **T2**：建脊柱 `query_privacy.py`（`_PrivacyBase` 三方法 + `_repo`/`_cfg` 自类型）——**必须先于 T3-T6**（四查询 mixin `class _X(_PrivacyBase)` 继承它、`from .query_privacy import _PrivacyBase`）。additive，门面暂仍持原方法。
3. **T3-T6**：逐个建四查询 mixin（`query_status`/`query_guild`/`query_events`/`query_players`），各 `class _X(_PrivacyBase)`，方法逐字搬入、加 import 头 + 额外自类型注解——additive，门面暂仍持原方法（过渡态死代码共存，靠逐字审 + T7 全库回归兜等价）。
4. **T7**：**升级 `output_consistency_test`（§8.1）——必须先于 T8 门面切换**。理由：门面切换会把 `event_view(` 从 query_service 移出，旧的「单模块扫 query_service」护栏（`assert "event_view(" in query_service_src`）在切换后必假红。升级为动态发现全 query_* 后，护栏在**两态皆绿**：additive 态（query_service 仍是 monolith 含 event_view + 六新模块皆 clean 副本，∀ 过 ∃ 过）与切换后态（query_service 变薄无 event_view，∃ 由 query_guild/query_events 满足）。故先升级、后切换，每步绿。
5. **T8**：**原子切换门面** `query_service.py`——删 30 方法 + 8 模块符号定义、改类为组合 4 查询 mixin（脊柱经继承传递）、加 re-export、留 3 TTL 常量、import 收缩到最终态；全库回归（含已升级护栏）= 等价性总验证。
6. **T9**：新增 `query_service_split_guard_test`（§8.2）。

> 「additive 建新单元 → 原子切换门面」比逐单元增量切换更稳（门面 import 一次收缩到最终态，避 N 个易错中间态）；过渡态死代码靠逐字审 + T8 全库回归兜等价（Spec D 同款验证结构）。**T7 护栏升级先于 T8 门面切换**是本 Spec 相对 Spec D 的新排序约束（Spec D 无护栏耦合）。
