# QueryService god 类拆解（Mixin + 隐私基座）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `application/query_service.py`（730 行、单 `QueryService` 类、30 方法读 god 对象）沿查询关注点拆成 5 个 mixin（各一文件）+ 1 个中立 `query_support.py`，主类多重继承组合为门面，零行为变化。

**Architecture:** 先 additive 建 `query_support.py`（8 模块符号）与 5 个 mixin 文件（逐字搬方法体，门面不动、方法暂重复共存但无冲突）；脊柱 `_PrivacyBase` 先建，四查询 mixin 各 `class _X(_PrivacyBase)` 继承它（令跨组 `self.spine()` 调用过 mypy）。**护栏升级（T7）先于门面原子切换（T8）**——切换会把 `event_view(` 移出 query_service，旧单模块护栏必假红，故先把护栏升级为动态发现全 query_*（两态皆绿）。最后加结构守卫（T9）。

**Tech Stack:** Python 3.11 / mixin 组合（脊柱作共享基类，非脊柱 mixin 继承之 + 纯类型注解自类型）/ pytest / ruff 0.15.21 / mypy。

**Spec:** `docs/superpowers/specs/2026-07-24-query-service-split-design.md`（方法归属见 §4、每 mixin import 见 §5、re-export 见 §6、护栏升级见 §8.1、守卫配方见 §8.2）。

## Global Constraints

- **逐字搬（字节级）**：方法体/符号体（含 docstring、内注释、空行、前置注释块）从 `query_service.py` 对应行号逐字复制，不改一字。**不要在本 plan 里重抄方法体**——照源文件行号复制，避免转写引入偏差。
- **按方法名清单抽取，不按连续源码范围切**：源码方法**物理交错**——尤其**隐私脊柱三方法（575/581/664）与 players 方法交错**：`name_banned`(664-669) 夹在 `rank`(606-662) 与 `_profile_extras`(671-694) 之间。逐个方法按名字/行号抽取，绝不剪一段连续行（否则把 name_banned 误拖进 players，或把 rank 误拖进 privacy）。
- **行尾 LF**：`query_service.py` 及全部新模块（5 mixin + query_support）+ 改动/新增的测试文件一律 **LF**（本文件族无 CRLF 陷阱；Spec D 的 CRLF 保真在此不适用）。
- **脊柱作共享基类**：`_PrivacyBase` 声明 `_repo: ReadRepositoryPort` + `_cfg: AppConfig`；四查询 mixin `class _X(_PrivacyBase)` 继承之 → `self._repo`/`self._cfg` 及跨组 `self.spine()` 调用经继承解析（已用隔离 scratch 实测 mypy `Success`）。非脊柱 mixin **不**重声明 `_repo`/`_cfg`、**不** import `ReadRepositoryPort`/`AppConfig`（二者全库仅 `__init__` 用，留门面 + 脊柱）。
- **零行为变化**：现有全库 **1198 passed / 1 skipped**（当前基线，已核）不变。任何搬移漂移都会在现有真-实例测试转红。
- **不 bump 版本**：v1.1.0 不动（纯重构）。
- **验收命令**（本机 python 不在 PATH，用 `.venv/Scripts/python.exe`）：`.venv/Scripts/ruff.exe check .`（全仓含 tests）+ `.venv/Scripts/python.exe -m mypy palworld_terminal/`（Success）+ `.venv/Scripts/python.exe -m pytest -q`（1198 passed/1 skipped，additive 阶段；T9 后 1201）全绿。
- **TDD 偏离**：本重构无新行为，搬迁任务（T1-T6/T8）的 test cycle = **全库回归**（现有测试即等价性安全网）；T7 护栏升级 = 改测试后跑全库确认两态绿；仅 T9 守卫走 TDD（含反证）。
- **commit 不含 Claude / Co-Authored-By / 任何 AI 署名。**
- **零改动**：`container.py`、`application/ports.py`、`dtos.py`、`name_resolver.py`、`report_service.py`、所有 service、所有调用点、所有现有非护栏测试。

## File Structure

- Create（LF）：`application/query_support.py`（8 模块级符号：DTO/helper/常量）· `query_privacy.py`（脊柱 `_PrivacyBase`）· `query_status.py`（`_StatusQueries`）· `query_guild.py`（`_GuildBaseQueries`）· `query_events.py`（`_EventSummaryQueries`）· `query_players.py`（`_RankProfileQueries`）。
- Modify（LF）：`application/query_service.py`——730 行 god 类 → ~40 行组合门面。`tests/unit/output_consistency_test.py`——护栏升级为动态发现全 query_*。
- Create（LF）：`tests/unit/query_service_split_guard_test.py`——结构守卫。

**方法/符号归属总表**（源行号已逐一核实；各方法「逐字搬到目标类体、保原相对顺序」）：

| 目标文件 | 类 | 符号（源行号） |
|---|---|---|
| `query_support.py` | （模块级，无类）| `_STATUS_TTL`:31 · `_ONLINE_TTL`:32 · `metric_stale`:35–42 · `_STATUS_RULE_FIELDS`（含注释 44-45）:44–51 · `_RULES_SECTIONS`（含注释 53-60）:53–89 · `_fmt_rules_num`:92–101 · `PlayerProfileDTO`:104–119 · `RankBoardsDTO`:122–126 |
| `query_privacy.py` | `_PrivacyBase` | `load_excluded_keys`:575–579 · `resolve_event_subjects`:581–589 · `name_banned`:664–669 |
| `query_status.py` | `_StatusQueries(_PrivacyBase)` | `_smoothness_label`:148–156 · `_online_rows`:158–191 · `status`:193–233 · `_server_address`:235–239 · `_config_server_name`:241–247 · `_status_rules`:249–259 · `_build_status_detail`:261–272 · `online`:274–293 |
| `query_guild.py` | `_GuildBaseQueries(_PrivacyBase)` | `_health_score`(@staticmethod):295–297 · `_base_counts_by_guild`:299–305 · `guilds`:307–322 · `guild`:324–356 · `_GUILD_BASE_EVENTS`（含注释 358-360）:358–361 · `_guild_recent_events`:363–378 · `_bases_indexed`:380–385 · `bases`:387–406 · `base`:408–446 |
| `query_events.py` | `_EventSummaryQueries(_PrivacyBase)` | `events`:448–474 · `_render_rule_value`:476–492 · `rules`:494–524 · `world_summary`:526–564 · `today`:566–573 |
| `query_players.py` | `_RankProfileQueries(_PrivacyBase)` | `_converge_by_name`:591–604 · `rank`:606–662 · `_profile_extras`:671–694 · `_build_profile`:696–708 · `player_profile`:710–719 · `profile_for_key`:721–730 |
| `query_service.py`（门面，留）| `QueryService(4 mixin)` | `__init__`:134–146 · `_GUILDS_TTL`/`_BASES_TTL`/`_EVENTS_TTL`:130–132 + re-export 4 符号 |

---

## Task 1: `query_support.py`（8 模块级符号）

**Files:**
- Create: `palworld_terminal/application/query_support.py`（LF）

**Interfaces:**
- Produces: 模块级 `metric_stale`/`_fmt_rules_num`/`PlayerProfileDTO`/`RankBoardsDTO`/`_STATUS_TTL`/`_ONLINE_TTL`/`_STATUS_RULE_FIELDS`/`_RULES_SECTIONS`（供 T2-T6 mixin import、T8 门面 re-export）。

- [ ] **Step 1: 建文件（import 头 + 中立 docstring + 逐字搬 8 符号）**

文件开头（spec §5）：
```python
"""QueryService 拆分的中立支撑层：模块级 helper / DTO / 常量（无类、无 self 依赖）。
从 query_service.py 迁出，供 5 个 query_* mixin 共享、门面 re-export 保外部路径。"""
from __future__ import annotations

from dataclasses import dataclass, field
```
然后从 `query_service.py` **逐字复制**以下 8 符号（各携其前置注释块）到模块体，保持原相对顺序与 LF：

| 符号 | 源行号 |
|---|---|
| `_STATUS_TTL = 15` | 31 |
| `_ONLINE_TTL = 15` | 32 |
| `metric_stale`（def + docstring）| 35–42 |
| `_STATUS_RULE_FIELDS`（含前置注释 44–45）| 44–51 |
| `_RULES_SECTIONS`（含前置注释 53–60，带类型注解）| 53–89 |
| `_fmt_rules_num`（def + docstring）| 92–101 |
| `PlayerProfileDTO`（`@dataclass(slots=True)` 104 + 类含内联注释 110–113）| 104–119 |
| `RankBoardsDTO`（`@dataclass(slots=True)` 122 + 类）| 122–126 |

- [ ] **Step 2: 新文件 lint + 全库回归不破坏**

Run: `.venv/Scripts/ruff.exe check palworld_terminal/application/query_support.py && .venv/Scripts/python.exe -m pytest -q`
Expected: ruff 无输出（clean）；pytest `1198 passed, 1 skipped`（query_support 此刻是未被引用的新模块 + query_service 原符号仍在，不影响现有行为）。

- [ ] **Step 3: mypy 通过**

Run: `.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: `Success: no issues found in 59 source files`（58 + query_support）。

- [ ] **Step 4: 健全性检查——8 符号齐全**

Run: `.venv/Scripts/python.exe -c "import palworld_terminal.application.query_support as q; assert all(hasattr(q,n) for n in ['metric_stale','_fmt_rules_num','PlayerProfileDTO','RankBoardsDTO','_STATUS_TTL','_ONLINE_TTL','_STATUS_RULE_FIELDS','_RULES_SECTIONS']); print('8 符号 OK')"`
Expected: `8 符号 OK`。

- [ ] **Step 5: Commit**

```bash
git add palworld_terminal/application/query_support.py
git commit -m "refactor: 抽出 query_support.py 中立支撑层（8 模块符号）"
```

---

## Task 2: `query_privacy.py`（脊柱 `_PrivacyBase`，3 方法）— 必须先于 T3-T6

**Files:**
- Create: `palworld_terminal/application/query_privacy.py`（LF）

**Interfaces:**
- Produces: `class _PrivacyBase`（供 T3-T6 四查询 mixin 继承、T8 门面经它们传递继承）——含 `load_excluded_keys`/`resolve_event_subjects`/`name_banned`，声明自类型 `_repo`/`_cfg`。

- [ ] **Step 1: 建文件（⚠️ 3 方法与 players 方法交错，只搬这 3 个）**

文件开头（spec §5）：
```python
from __future__ import annotations

from ..config import AppConfig
from ..domain.models import World, WorldEvent
from .name_resolver import resolve_subjects
from .name_resolver import load_excluded_keys as _load_excluded_keys
from .ports import ReadRepositoryPort


class _PrivacyBase:
    """隐私脊柱：排除名单 / 名字级封禁判定 / 事件主体解析。四查询 mixin 继承本类，
    跨组隐私调用经 self/MRO 解析到这里（脊柱是唯一跨切点）。"""

    _repo: ReadRepositoryPort
    _cfg: AppConfig
```
从 `query_service.py` **逐字复制**以下 3 方法（**注意交错**：575/581 之后跳过 591–662=`_converge_by_name`+`rank`（属 players），再到 664）：

| 方法 | 源行号 |
|---|---|
| `load_excluded_keys` | 575–579 |
| `resolve_event_subjects` | 581–589 |
| `name_banned` | 664–669 |

> `resolve_event_subjects`:588 内调 `self.load_excluded_keys`（同类）。`WorldEvent` 用于 `resolve_event_subjects` 的 `events: list[WorldEvent]` 注解。别名 `load_excluded_keys as _load_excluded_keys`（原 :27）逐字保留。

- [ ] **Step 2: lint + 回归**

Run: `.venv/Scripts/ruff.exe check palworld_terminal/application/query_privacy.py && .venv/Scripts/python.exe -m pytest -q`
Expected: clean；`1198 passed, 1 skipped`。

- [ ] **Step 3: mypy**

Run: `.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: `Success ... 60 source files`（自类型 `_repo`/`_cfg` 声明使 `self._repo`/`self._cfg` 可解析）。

- [ ] **Step 4: 健全性检查——3 方法齐全**

Run: `.venv/Scripts/python.exe -c "import inspect; from palworld_terminal.application.query_privacy import _PrivacyBase; m={n for n,_ in inspect.getmembers(_PrivacyBase, inspect.isfunction) if not n.startswith('__')}; print(sorted(m)); assert m=={'load_excluded_keys','resolve_event_subjects','name_banned'}"`
Expected: 3 方法名，assert 通过（**不多不少**——若含 `rank`/`_converge_by_name` 说明误搬了交错的 players 方法）。

- [ ] **Step 5: Commit**

```bash
git add palworld_terminal/application/query_privacy.py
git commit -m "refactor: 抽出 _PrivacyBase 隐私脊柱（query_privacy.py）"
```

---

## Task 3: `query_status.py`（`_StatusQueries`，8 方法）

**Files:**
- Create: `palworld_terminal/application/query_status.py`（LF）

**Interfaces:**
- Consumes: `_PrivacyBase`（T2）、`query_support`（T1 的 `metric_stale`/`_STATUS_TTL`/`_ONLINE_TTL`/`_STATUS_RULE_FIELDS`）。
- Produces: `class _StatusQueries(_PrivacyBase)`——含 `status`/`online` + 6 私有 helper。

- [ ] **Step 1: 建文件（方法块连续 148–293）**

文件开头（spec §5；**不** import `ReadRepositoryPort`/`AppConfig`——`_repo`/`_cfg` 继承脊柱）：
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


class _StatusQueries(_PrivacyBase):
    """状态卡 / 在线名单查询（status、online）。"""

    _cache: TTLCache
    _clock: Clock
    _meta: Any
    _settings_cache: Any
    _info_cache: Any
```
从 `query_service.py` 逐字复制（连续块，按顺序）：

| 方法 | 源行号 |
|---|---|
| `_smoothness_label` | 148–156 |
| `_online_rows`（内 :164/:187 调 `self.load_excluded_keys`/`self.name_banned`=脊柱）| 158–191 |
| `status` | 193–233 |
| `_server_address` | 235–239 |
| `_config_server_name` | 241–247 |
| `_status_rules` | 249–259 |
| `_build_status_detail` | 261–272 |
| `online` | 274–293 |

- [ ] **Step 2: lint + 回归**

Run: `.venv/Scripts/ruff.exe check palworld_terminal/application/query_status.py && .venv/Scripts/python.exe -m pytest -q`
Expected: clean；`1198 passed, 1 skipped`。

- [ ] **Step 3: mypy**

Run: `.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: `Success ... 61 source files`（继承 `_PrivacyBase` → `self._repo`/`self._cfg`/`self.load_excluded_keys`/`self.name_banned` 全解析）。

- [ ] **Step 4: 健全性检查——8 方法齐全**

Run: `.venv/Scripts/python.exe -c "import inspect; from palworld_terminal.application.query_status import _StatusQueries; m={n for n,_ in inspect.getmembers(_StatusQueries, inspect.isfunction) if not n.startswith('__')}; own=m-{'load_excluded_keys','resolve_event_subjects','name_banned'}; print(sorted(own)); assert len(own)==8"`
Expected: 8 自有方法名（减去继承的 3 脊柱方法），assert 通过。

- [ ] **Step 5: Commit**

```bash
git add palworld_terminal/application/query_status.py
git commit -m "refactor: 抽出 _StatusQueries mixin（query_status.py）"
```

---

## Task 4: `query_guild.py`（`_GuildBaseQueries`，8 方法 + `_GUILD_BASE_EVENTS`）

**Files:**
- Create: `palworld_terminal/application/query_guild.py`（LF）

**Interfaces:**
- Consumes: `_PrivacyBase`（T2 的 `resolve_event_subjects`）、`dtos`（`event_view` 等）。
- Produces: `class _GuildBaseQueries(_PrivacyBase)`——含 `guilds`/`guild`/`bases`/`base` + helper + `_GUILD_BASE_EVENTS` 类常量。

- [ ] **Step 1: 建文件（连续块 295–446，中含类常量 358–361）**

文件开头（spec §5；`EventType` 为 `_GUILD_BASE_EVENTS` 类定义期求值所需**运行时** import；**不** import `ReadRepositoryPort`）：
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


class _GuildBaseQueries(_PrivacyBase):
    """公会 / 据点查询（guilds、guild、bases、base）。"""

    _cache: TTLCache
    _GUILDS_TTL: int
    _BASES_TTL: int
```
从 `query_service.py` 逐字复制（按源顺序，**`_GUILD_BASE_EVENTS` 类常量含其前置注释 358–360 随本 mixin 迁为类体属性**）：

| 方法/常量 | 源行号 |
|---|---|
| `_health_score`（`@staticmethod` 295 + def 296–297）| 295–297 |
| `_base_counts_by_guild` | 299–305 |
| `guilds` | 307–322 |
| `guild` | 324–356 |
| `_GUILD_BASE_EVENTS`（含前置注释 358–360 + 常量 361）| 358–361 |
| `_guild_recent_events`（:377 调 `self.resolve_event_subjects`=脊柱；:378 调 `event_view(`）| 363–378 |
| `_bases_indexed` | 380–385 |
| `bases` | 387–406 |
| `base`（:444 调 `self._health_score`=组内 staticmethod）| 408–446 |

- [ ] **Step 2: lint + 回归**

Run: `.venv/Scripts/ruff.exe check palworld_terminal/application/query_guild.py && .venv/Scripts/python.exe -m pytest -q`
Expected: clean；`1198 passed, 1 skipped`。

- [ ] **Step 3: mypy**

Run: `.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: `Success ... 62 source files`。

- [ ] **Step 4: 健全性检查——8 方法齐全 + 类常量在**

Run: `.venv/Scripts/python.exe -c "import inspect; from palworld_terminal.application.query_guild import _GuildBaseQueries as G; m={n for n,_ in inspect.getmembers(G, inspect.isfunction) if not n.startswith('__')}; own=m-{'load_excluded_keys','resolve_event_subjects','name_banned'}; print(sorted(own)); assert len(own)==8 and hasattr(G,'_GUILD_BASE_EVENTS') and len(G._GUILD_BASE_EVENTS)==3"`
Expected: 8 自有方法名 + `_GUILD_BASE_EVENTS`（3 元组），assert 通过。

- [ ] **Step 5: Commit**

```bash
git add palworld_terminal/application/query_guild.py
git commit -m "refactor: 抽出 _GuildBaseQueries mixin（query_guild.py）"
```

---

## Task 5: `query_events.py`（`_EventSummaryQueries`，5 方法）

**Files:**
- Create: `palworld_terminal/application/query_events.py`（LF）

**Interfaces:**
- Consumes: `_PrivacyBase`（`resolve_event_subjects`）、`name_resolver.keep_world_subject_under_strict`、`query_support`（`_RULES_SECTIONS`/`_fmt_rules_num`）、`dtos`（`event_view` 等）。
- Produces: `class _EventSummaryQueries(_PrivacyBase)`——含 `events`/`rules`/`world_summary`/`today` + `_render_rule_value`。

- [ ] **Step 1: 建文件（连续块 448–573；隐私敏感路径 events）**

文件开头（spec §5；**不** import `ReadRepositoryPort`/`AppConfig`）：
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


class _EventSummaryQueries(_PrivacyBase):
    """世界事件 / 规则 / 摘要 / 今日查询（events、rules、world_summary、today）。"""

    _cache: TTLCache
    _clock: Clock
    _meta: Any
    _settings_cache: Any
    _world_cache: Any
    _report: Any
    _EVENTS_TTL: int
    _BASES_TTL: int
```
从 `query_service.py` 逐字复制（连续块，按顺序）：

| 方法 | 源行号 |
|---|---|
| `events`（:461 `keep_world_subject_under_strict`；:466 `self.resolve_event_subjects`=脊柱；:470 隐藏玩家抑制；:472 `event_view(`）| 448–474 |
| `_render_rule_value`（:486/:487 用 `_fmt_rules_num`）| 476–492 |
| `rules`（:505 用 `_RULES_SECTIONS`）| 494–524 |
| `world_summary` | 526–564 |
| `today` | 566–573 |

- [ ] **Step 2: lint + 回归**

Run: `.venv/Scripts/ruff.exe check palworld_terminal/application/query_events.py && .venv/Scripts/python.exe -m pytest -q`
Expected: clean；`1198 passed, 1 skipped`。

- [ ] **Step 3: mypy**

Run: `.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: `Success ... 63 source files`。

- [ ] **Step 4: 健全性检查——5 方法齐全**

Run: `.venv/Scripts/python.exe -c "import inspect; from palworld_terminal.application.query_events import _EventSummaryQueries as E; m={n for n,_ in inspect.getmembers(E, inspect.isfunction) if not n.startswith('__')}; own=m-{'load_excluded_keys','resolve_event_subjects','name_banned'}; print(sorted(own)); assert own=={'events','_render_rule_value','rules','world_summary','today'}"`
Expected: 5 自有方法名，assert 通过。

- [ ] **Step 5: Commit**

```bash
git add palworld_terminal/application/query_events.py
git commit -m "refactor: 抽出 _EventSummaryQueries mixin（query_events.py）"
```

---

## Task 6: `query_players.py`（`_RankProfileQueries`，6 方法）— ⚠️ 与脊柱 name_banned 交错

**Files:**
- Create: `palworld_terminal/application/query_players.py`（LF）

**Interfaces:**
- Consumes: `_PrivacyBase`（`load_excluded_keys`/`name_banned`）、`query_support`（`PlayerProfileDTO`/`RankBoardsDTO`）。
- Produces: `class _RankProfileQueries(_PrivacyBase)`——含 `rank`/`player_profile`/`profile_for_key` + helper。

- [ ] **Step 1: 建文件（⚠️ 跳过夹在中间的 name_banned 664–669=脊柱）**

文件开头（spec §5；**不** import `ReadRepositoryPort`/`AppConfig`；仅构造 DTO 不定义，故无 `dataclass` import）：
```python
from __future__ import annotations

from ..domain.models import PlayerIdentity, World
from ..infrastructure.clock import Clock
from .query_privacy import _PrivacyBase
from .query_support import PlayerProfileDTO, RankBoardsDTO
from .report_service import day_bounds


class _RankProfileQueries(_PrivacyBase):
    """排行榜 / 玩家档案查询（rank、player_profile、profile_for_key）。"""

    _clock: Clock
```
从 `query_service.py` 逐字复制（**注意交错**：`rank`(606–662) 之后跳过 `name_banned`(664–669)=脊柱，直接到 `_profile_extras`(671)）：

| 方法 | 源行号 |
|---|---|
| `_converge_by_name`（保 `self` 参，虽不用 self）| 591–604 |
| `rank`（:607 `self.load_excluded_keys`=脊柱；:629/:646 `self._converge_by_name`；:662 构造 `RankBoardsDTO`）| 606–662 |
| ~~`name_banned` 664–669~~ | **跳过**（属 _PrivacyBase，T2 已搬） |
| `_profile_extras` | 671–694 |
| `_build_profile`（:701–708 构造 `PlayerProfileDTO`）| 696–708 |
| `player_profile`（:716 `self.load_excluded_keys`；:717 `self.name_banned`=脊柱）| 710–719 |
| `profile_for_key` | 721–730 |

- [ ] **Step 2: lint + 回归**

Run: `.venv/Scripts/ruff.exe check palworld_terminal/application/query_players.py && .venv/Scripts/python.exe -m pytest -q`
Expected: clean；`1198 passed, 1 skipped`。

- [ ] **Step 3: mypy**

Run: `.venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: `Success ... 64 source files`（全部 6 新模块就位）。

- [ ] **Step 4: 健全性检查——6 方法齐全，不含 name_banned**

Run: `.venv/Scripts/python.exe -c "import inspect; from palworld_terminal.application.query_players import _RankProfileQueries as R; m={n for n,_ in inspect.getmembers(R, inspect.isfunction) if not n.startswith('__')}; own=m-{'load_excluded_keys','resolve_event_subjects','name_banned'}; print(sorted(own)); assert own=={'_converge_by_name','rank','_profile_extras','_build_profile','player_profile','profile_for_key'}"`
Expected: 6 自有方法名（`name_banned` 经继承在 `m` 里但不在 `own`），assert 通过——**若 `own` 含 `name_banned` 说明误搬了交错方法**。

- [ ] **Step 5: Commit**

```bash
git add palworld_terminal/application/query_players.py
git commit -m "refactor: 抽出 _RankProfileQueries mixin（query_players.py）"
```

---

## Task 7: 升级护栏 `output_consistency_test.py`（动态发现全 query_*）— 必须先于 T8

**Files:**
- Modify: `tests/unit/output_consistency_test.py`（LF）

**Interfaces:**
- Consumes: 全部 `query_*` 模块（T1-T6 已建 + 门面）+ `report_service`。此刻（additive 态）query_service 仍是 monolith，故护栏两态皆绿（见 spec §8.1）。

- [ ] **Step 1: 替换 import 块（:10–17 区域）为动态发现**

把原 `from palworld_terminal.application import query_service, report_service`（:15）连同其后加入动态发现 helper。**保留** `import ast`/`import inspect`/`_code_string_literals`/`_WORDING_FRAGMENTS` 与第二个测试 `test_formatters_delegate_textkit...` 原样。将 import 段改为（spec §8.1）：
```python
from __future__ import annotations

import ast
import importlib
import inspect
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

- [ ] **Step 2: 替换 `test_eight_wordings...` 里的 `for mod in (query_service, report_service):` 循环（原 :63–72）**

在该测试内，把 `canonical = ...`（event_wording 八指纹 present 检查，原 :57–59）**保留不动**；把其后的 `for mod in (query_service, report_service):` 循环（原 :63–72）替换为量词分治版（spec §8.1），第 :74 行 `assert "render_event(" in inspect.getsource(formatters_module)` **保留**：
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

- [ ] **Step 3: 跑升级后护栏——additive 态应绿**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/output_consistency_test.py -v`
Expected: 2 passed。此刻 query_service 仍 monolith（含 `event_view(`、无 `event_wording`），6 新模块皆 clean 副本，`query_support` 的 `_RULES_SECTIONS` 中文串与 8 措辞指纹无交集 → ∀ 全过、∃ 由 query_service/query_guild/query_events 满足。

- [ ] **Step 4: 全库回归 + ruff**

Run: `.venv/Scripts/ruff.exe check tests/unit/output_consistency_test.py && .venv/Scripts/python.exe -m pytest -q`
Expected: clean；`1198 passed, 1 skipped`（测试函数数不变，仍 2 个）。

- [ ] **Step 5: Commit**

```bash
git add tests/unit/output_consistency_test.py
git commit -m "test: 护栏升级为动态发现全 query_* 模块（拆分前置，量词分治保隐私强度）"
```

---

## Task 8: 原子切换门面 `query_service.py`（删 30 方法 + 8 符号、组合 4 mixin、re-export）

**Files:**
- Modify: `palworld_terminal/application/query_service.py`（LF）

**Interfaces:**
- Consumes: `query_support`（T1）、4 查询 mixin（T3-T6）、`_PrivacyBase`（T2，经 mixin 传递继承）。
- Produces: `class QueryService(_StatusQueries, _GuildBaseQueries, _EventSummaryQueries, _RankProfileQueries)`——仍暴露全 30 方法（经继承）；保留 `__init__`、3 TTL 常量；re-export 4 符号。类名/模块/构造签名不变（`from ...query_service import QueryService/metric_stale/PlayerProfileDTO/RankBoardsDTO/_STATUS_RULE_FIELDS` 全站有效）。

- [ ] **Step 1: 用 Edit 删除已迁走的 30 方法 + 8 模块符号定义**

从 `query_service.py` **删除**：8 模块级符号（31–126，即 `_STATUS_TTL`…`RankBoardsDTO` 及其注释块）+ 30 个方法（148–730，即 `_smoothness_label`…`profile_for_key`，含 `_GUILD_BASE_EVENTS` 常量 358–361）。**保留**：模块 docstring 区（Step 3 重写）、部分 imports（Step 3 收缩）、`class QueryService:` 行 + 3 TTL 常量（130–132）+ `__init__`（134–146）。

- [ ] **Step 2: 改类继承 4 查询 mixin**

`class QueryService:` 改为（spec §3.1；**只列四查询 mixin，_PrivacyBase 经它们传递继承，不再单列**）：
```python
class QueryService(
    _StatusQueries,
    _GuildBaseQueries,
    _EventSummaryQueries,
    _RankProfileQueries,
):
```

- [ ] **Step 3: 收缩 import 到最终态 + 重写模块/类 docstring + 加 re-export**

模块顶部最终形态（**替换**原 1–29 行的 imports；旧 module docstring 若有则丢弃）——即 spec §3.1 门面 import 块：
```python
from __future__ import annotations

from ..config import AppConfig
from ..infrastructure.cache import TTLCache
from ..infrastructure.clock import Clock
from .ports import ReadRepositoryPort
from .query_events import _EventSummaryQueries
from .query_guild import _GuildBaseQueries
from .query_players import _RankProfileQueries
from .query_status import _StatusQueries
from .query_support import PlayerProfileDTO as PlayerProfileDTO
from .query_support import RankBoardsDTO as RankBoardsDTO
from .query_support import _STATUS_RULE_FIELDS as _STATUS_RULE_FIELDS
from .query_support import metric_stale as metric_stale
```
类 docstring 改为 spec §3.1 门面 docstring（读查询门面 / 四 mixin 继承 _PrivacyBase / 模块级迁 query_support）。`__init__` 与 3 TTL 常量逐字保留、不调 `super().__init__()`。

- [ ] **Step 4: 全库回归——等价性总验证（最关键）**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `1198 passed, 1 skipped`。此步接上继承后，任何 mixin 副本的字节漂移都会在此暴露。升级后护栏（T7）在此也跑：query_service 变薄无 `event_view(`，∃ 由 query_guild/query_events 满足 → 仍绿。若红 → 逐字对照该方法的 mixin 副本与本任务前的 query_service.py。

- [ ] **Step 5: ruff + mypy 全绿**

Run: `.venv/Scripts/ruff.exe check . && .venv/Scripts/python.exe -m mypy palworld_terminal/`
Expected: `All checks passed!`；`Success: no issues found in 64 source files`。若 ruff 报门面 F401（收缩漏删的 import），删之；re-export 4 行的冗余别名（`X as X`）**不**报 F401（ruff 0.15.21 实测）。

- [ ] **Step 6: 确认门面塌缩 + 类名/构造/re-export 不变**

Run: `.venv/Scripts/python.exe -c "from palworld_terminal.application.query_service import QueryService, metric_stale, PlayerProfileDTO, RankBoardsDTO, _STATUS_RULE_FIELDS; import inspect; print('ctor', list(inspect.signature(QueryService.__init__).parameters)); m={n for n,_ in inspect.getmembers(QueryService, inspect.isfunction) if not n.startswith('__')}; print('methods', len(m))" && wc -l palworld_terminal/application/query_service.py`
Expected: 构造参数 `['self','repo','cache','cfg','meta','clock','settings_cache','world_cache','report','info_cache']`；`methods 30`；门面文件 ~40 行；4 re-export 符号可 import。

- [ ] **Step 7: Commit**

```bash
git add palworld_terminal/application/query_service.py
git commit -m "refactor: QueryService 门面切换为 4 mixin 组合 + 隐私脊柱继承（拆分收尾）"
```

---

## Task 9: 结构守卫 `query_service_split_guard_test.py`

**Files:**
- Create: `tests/unit/query_service_split_guard_test.py`（LF）

**Interfaces:**
- Consumes: `QueryService`（T8）、5 query_* mixin 模块。

- [ ] **Step 1: 写守卫测试（3 断言，spec §8.2 配方）**

```python
"""QueryService 拆分结构守卫：方法集完整性 + 脊柱唯一跨切点 + 构造契约不变。"""
from __future__ import annotations

import ast
import inspect
import pathlib

from palworld_terminal.application.query_service import QueryService

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "palworld_terminal" / "application"

SPINE = {"load_excluded_keys", "name_banned", "resolve_event_subjects"}

# §4 全 30 方法完整清单（唯一真相源；含全部单下划线 helper）
EXPECTED_METHODS = {
    # privacy 脊柱 (3)
    "load_excluded_keys", "resolve_event_subjects", "name_banned",
    # status (8)
    "_smoothness_label", "_online_rows", "status", "_server_address",
    "_config_server_name", "_status_rules", "_build_status_detail", "online",
    # guild (8)
    "_health_score", "_base_counts_by_guild", "guilds", "guild",
    "_guild_recent_events", "_bases_indexed", "bases", "base",
    # events (5)
    "events", "_render_rule_value", "rules", "world_summary", "today",
    # players (6)
    "_converge_by_name", "rank", "_profile_extras", "_build_profile",
    "player_profile", "profile_for_key",
}


def test_query_service_exposes_exactly_30_methods():
    # 类级内省：int 类常量 _GUILDS_TTL/_BASES_TTL/_EVENTS_TTL 与 tuple _GUILD_BASE_EVENTS
    # 非 function、天然不在其中；async/sync/staticmethod 全纳。仅排除 dunder __init__。
    actual = {
        n for n, _ in inspect.getmembers(QueryService, inspect.isfunction)
        if not n.startswith("__")
    }
    assert actual == EXPECTED_METHODS
    assert len(EXPECTED_METHODS) == 30


def _self_call_names(class_node: ast.ClassDef) -> set[str]:
    calls: set[str] = set()
    for node in ast.walk(class_node):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            calls.add(node.func.attr)
    return calls


def _own_method_names(class_node: ast.ClassDef) -> set[str]:
    return {
        n.name for n in class_node.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_spine_is_only_cross_cut():
    # 每个 query_* mixin：self.NAME() 直接调用 ⊆ (自身方法 ∪ 脊柱三方法)。
    # 锁死「跨组只经脊柱（继承而来），绝无 leaf-to-leaf」。self._X.foo() 这类不计入
    # （func.value 是 Attribute 非 Name('self')）；self._BASES_TTL 是属性访问非 Call。
    mixin_files = sorted(APP_DIR.glob("query_*.py"))
    mixin_files = [p for p in mixin_files if p.name not in ("query_service.py", "query_support.py")]
    assert len(mixin_files) == 5, f"应有 5 个 mixin 模块，实为 {[p.name for p in mixin_files]}"
    for py in mixin_files:
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                own = _own_method_names(node)
                calls = _self_call_names(node)
                leak = calls - own - SPINE
                assert not leak, f"{py.name}:{node.name} 跨组调用越出脊柱：{leak}"


def test_facade_ctor_signature_unchanged():
    params = list(inspect.signature(QueryService.__init__).parameters)
    assert params == [
        "self", "repo", "cache", "cfg", "meta", "clock",
        "settings_cache", "world_cache", "report", "info_cache",
    ]
```

- [ ] **Step 2: 跑守卫——应通过（拆分已在 T8 完成）**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/query_service_split_guard_test.py -v`
Expected: 3 passed。

- [ ] **Step 3: 验证守卫有效性（临时反证，推荐）**

(a) 临时在 `query_players.py` 注释掉 `profile_for_key` 一个方法 → 跑 `test_query_service_exposes_exactly_30_methods` 应 FAIL（`actual != EXPECTED`）。**还原**。
(b) 临时在 `query_events.py` 的 `events` 里加一句 `_ = self._converge_by_name` 调用（`self._converge_by_name()`，players 的方法）→ 跑 `test_spine_is_only_cross_cut` 应 FAIL（leak 含 `_converge_by_name`）。**还原**。
确认守卫真能抓「搬漏」与「leaf-to-leaf 越界」。

- [ ] **Step 4: 全套验收 + ruff/mypy**

Run: `.venv/Scripts/ruff.exe check . && .venv/Scripts/python.exe -m mypy palworld_terminal/ && .venv/Scripts/python.exe -m pytest -q`
Expected: `All checks passed!`；`Success ... 64 source files`；`1201 passed, 1 skipped`（1198 + 3 守卫）。

- [ ] **Step 5: Commit**

```bash
git add tests/unit/query_service_split_guard_test.py
git commit -m "test: QueryService 拆分结构守卫（30 方法完整性 + 脊柱唯一跨切点 + 构造契约）"
```

---

## 完成标准

- `application/query_service.py` 从 730 行 god 类塌缩为 ~40 行组合门面。
- 5 个 mixin（`query_privacy` 脊柱 + `query_status`/`query_guild`/`query_events`/`query_players` 各继承脊柱）+ 中立 `query_support.py`。
- `QueryService` 仍暴露全 30 方法（经继承）、类名/模块/构造签名不变、外部 import 路径经 re-export 全保留、全站零改动。
- 隐私护栏升级为动态发现全 query_*（∀ event_wording 缺 + ∃ event_view 用），强度不减。
- `ruff check .` + `mypy(64)` + `pytest`（1201 passed/1 skipped）全绿。
- 全程零行为变化（现有 1198 测试不变）、方法体逐字搬（LF）、不 bump 版本。
