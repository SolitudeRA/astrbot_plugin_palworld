# Spec A：presentation 解耦（消除 application → presentation 反向依赖）

> 状态：设计定稿（经三视角对抗复核 + 三棱镜 spec 复核硬化）｜日期：2026-07-21｜分支：待定
> 系列：架构解耦三部曲之 A。Spec B = 拆 commands.py（presentation）；Spec C = 适配器解耦（RepositoryPort + RestResponse/privacy_filter/normalizer 迁移 + 杀 _ADMIN_PATH）。本 spec 只做 A。

## 1. 目标与非目标

### 目标
彻底消除 `application` 层对 `presentation` 层的反向依赖（依赖倒置违规）。当前 application 有 **5 处** `from ..presentation.*` import，全部清零，使 application 只依赖 `domain` + `infrastructure`（+ 新增中立 `shared`）+ adapters（adapters 解耦属 Spec C）。

**硬约束：零运行时行为变化、零用户可见输出字节变化。** 这是一次纯结构重构——所有面向用户的中文文案逐字不变，全部 golden `.txt` 输出测试字节不动。

### 非目标（明确排除）
- RepositoryPort / 适配器解耦（`application → adapters` 方向）——归 **Spec C**。本 spec 不动 application 对具体 adapter 的任何 import。
- 拆分 `commands.py`（939 行）——归 **Spec B**。
- 任何行为、语义、输出字节的改变。任何新功能。

## 2. 背景与现状：5 处反向依赖

复核逐条确认，application 层现存正好 5 处 `from ..presentation.*` import（无漏网）：

| # | 位置 | 违规 import | 本质 |
|---|---|---|---|
| 1 | `application/query_service.py:11` | `from ..presentation.dtos import (13 个名字)` | DTO 是 query_service **生产**的输出契约，却定义在消费方 presentation |
| 2 | `application/query_service.py:26` | `from ..presentation.event_wording import event_wording` | application 在生产中文措辞 |
| 3 | `application/report_service.py:12` | `from ..presentation.event_wording import event_wording` | 同上 |
| 4 | `application/routing_service.py:9` | `from ..presentation.locale import L` | routing 返回已渲染的中文错误串 |
| 5 | `application/command_permissions.py:11` | `from ..presentation.command_registry import ...` | command_registry 实为共享内核，错位在 presentation |

> #1 的 13 个名字：`BaseDetailDTO, BaseDTO, EventDTO, GuildDetailDTO, GuildDTO, OnlineDTO, OnlinePlayerRow, RulesDTO, RuleSection, StatusDetailDTO, StatusDTO, WildTopRow, WorldSummaryDTO`（10 个 *DTO + 3 个 Row/Section）。其中 `EventDTO` 在组件③被 `EventView` 取代。

**对抗复核关键结论（供实现者信任本设计）：**
- **导入环攻击失败**：本设计不制造任何环，反而移除 3 处倒置。`event_wording` docstring 担心的 `report_service→formatters→query_service` 环，那条 `report_service→formatters` 边**今天就不存在、本设计也不创造**。`command_registry.py` 当前**唯一 import 是 `from __future__ import annotations`**（零运行时依赖），移到 `shared/` 后 `shared` 对 `domain` 是「**允许的依赖方向**」（可依赖、绝不反向），非当前实际 import——今天 shared 无任何运行时依赖。
- **wording 无损**：`event_wording.py` 8 类分支只消费 `event.payload`（经 `p.get`）+ `name`，dispatch on `event_type`，不碰 `subject_type/subject_key/world_id/occurred_at` 等任何其它 `WorldEvent` 字段。故 `render_event(view: EventView)` 信息充分。
- **`presentation.dtos` 不被 web API 契约消费**（`web_api.py`/`config_view.py` 不 import dtos），故 `EventDTO→EventView` 不是 web 契约变更。

## 3. 架构：解耦后的依赖方向

箭头 = **允许的依赖方向**（可依赖，绝不反向），非「当前必有 import」：

```
domain  ← infrastructure
  ↑            ↑
  │            │
shared  ───────┤          (command_registry: 今日零运行时依赖)
  ↑            │
application ───┘ ── adapters   (adapters 耦合留待 Spec C)
  ↑
presentation                 (formatters/commands import application.{dtos,routing_service} —— 方向正确)
```

本 spec 后 application 对 presentation 的箭头 **全部消失**（5 处清零）。presentation → application（消费 DTO、消费 RoutingError）是正确方向，保留/新增。

## 4. 组件①：`shared/` 新包（command_registry 迁移）

**动作**：
- 新建 `palworld_terminal/shared/__init__.py`（**空文件**）。
- `palworld_terminal/presentation/command_registry.py` → `palworld_terminal/shared/command_registry.py`（**内容原样搬**，零逻辑改动）。
- 重指 5 个源消费者的 import 路径：
  - `application/command_permissions.py:11`
  - `presentation/formatters.py:7`
  - `presentation/commands.py:16`
  - `presentation/config_view.py:15`
  - `config.py:342-350`（见下「延迟 import 退役」）
- 重指 6 个测试文件：`formatters_hierarchy_test`、`setup_gate_test`、`command_registry_hierarchy_test`、`command_names_test`、`formatters_admin_help_test`、`command_permissions_meta_test`。

**config.py 延迟 import 退役（精确范围）**：`config.py:342-350` 是一整块函数体内延迟 import，含**两条**：`.application.command_permissions` 的多个名字（342-349）+ `.presentation.command_registry` 的 `DISPATCH`（350）。目的原是避 config↔presentation 环。
- command_registry 迁 shared 后，那条 import 变 `from .shared.command_registry import DISPATCH`，**可上提模块顶层**。
- command_permissions 那几行**也可一并上提**——`config.py:8` 已在顶层 `from .application.command_permissions import CommandOverride`，证明 config→application.command_permissions 顶层导入本就安全无环。
- **结论**：整块函数体延迟 import 退役、全部上提顶层。§10 验收即指此。

**AstrBot 命名空间安全**（项目历史踩过「包内绝对自导入在命名空间加载下运行时炸」）：
- `shared/__init__.py` 保持空。
- 所有消费者用**相对 import**（`from ..shared.command_registry import ...` / `from .shared...`），绝不用绝对自导入。
- 已有静态防回归测试守绝对自导入；迁移后该测试须覆盖 `shared/`。

**锚定不变**：`PAL_COMMAND_STRINGS`、`LOCKABLE_COMMANDS`、`_NON_LOCKABLE`、`HELP_TEXT`、`DISPATCH`、`METHOD_PATH` 等常量**值不变**，只改 import 路径。`command_names_test` 等锚定断言的**值**存活，只需改 import 行。

## 5. 组件②：`dtos` 移到 application

**动作**：
- `palworld_terminal/presentation/dtos.py` → `palworld_terminal/application/dtos.py`（内容搬迁；`EventDTO` 在组件③被 `EventView` 取代，其余 DTO 原样）。
- 重指源消费者：
  - `presentation/formatters.py:13`（→ `from ..application.dtos import ...`）
  - `presentation/commands.py:18`（→ `from ..application.dtos import ...`）
  - `application/query_service.py:11`（→ `from .dtos import ...`，同层相对）
- 重指测试（**实现期以 `grep -rl 'presentation.dtos\|from .dtos'` 全量核对为准**；已知机械改路径者）：`formatters_test`、`dtos_test`、`status_detail_shape_test`、`config_view_status_test`。
  - **例外（须重写数据/类型，非改路径）**：`formatters_golden_test`（fixture）、`commands_guild_test`——它们构造 `EventDTO(summary=)` / `GuildDetailDTO(recent_events=[串])`，随组件③改 EventView 后需改数据，见 §8.4。

`dtos.py` 只 import `domain.enums`，无 event_wording 依赖（仅 docstring 提及），迁移干净、不引入新反向依赖。

## 6. 组件③：EventView + render_event（核心）

### 6.1 EventView 具名 typed 字段（隐私 + 类型双重加固）

**替换** `EventDTO{occurred_at:int, event_type:str, summary:str}` 为：

```python
# application/dtos.py
@dataclass(slots=True)
class EventView:
    occurred_at: int
    event_type: EventType          # 枚举，非 str（消灭 EventType(str) 的 ValueError 崩溃路径）
    name: str                      # resolver 已解析的显示名；世界主体事件为空串
    old: int | None = None         # PLAYER_LEVEL_UP
    new: int | None = None         # PLAYER_LEVEL_UP
    prev: int | None = None        # WORKER_DELTA
    cur: int | None = None         # WORKER_DELTA
    milestone: int | None = None   # WORLD_DAY_MILESTONE
    value: int | None = None       # ONLINE_RECORD
```

**为何具名字段而非 `payload: dict`**（对抗复核隐私 Major 1）：原始 `WorldEvent.payload`（唯一写入方 `event_service.py`）含 `event_wording` 从不渲染的键——`NEW_BASE.payload` 有 `guild_key`（内部公会 DB key，§6#7 明令封堵的丑键类）+ `worker_count` + `confidence`、`WORLD_DAY_MILESTONE.payload` 有 `day`（真实世界天数）、`BASE_VANISHED.payload` 有 `first_missing_day`。透原始 dict 给渲染层 = 重开已决策封堵的泄漏类。具名字段从**类型上**消灭「渲染层拿到未审数据」这一整类风险。

**EventView 坚决不携带 `subject_key` / `subject_type`**（内部 key，渲染层不需要，携带即泄漏风险）。

**8 类事件 → EventView 字段映射**（构造时按 event_type 只填对应字段，其余留 None）：

| EventType | 填充字段 | 说明 |
|---|---|---|
| PLAYER_LEVEL_UP | `old, new` | |
| NEW_PLAYER | （仅 name） | |
| NEW_GUILD | （仅 name） | |
| NEW_BASE | （仅 name） | **不填 guild_key/worker_count/confidence** |
| BASE_VANISHED | （仅 name） | **不填 first_missing_day** |
| WORKER_DELTA | `prev, cur` | |
| WORLD_DAY_MILESTONE | `milestone` | **不填 day** |
| ONLINE_RECORD | `value` | |

### 6.1a EventView 单一构造入口（防三处抽取漂移）

「按 event_type 从 payload 抽取具名字段」这套映射（§6.1 表）**收敛为 application 单一 helper**——否则三个构造点各写一份会无声漂移（复核 major）：

```python
# application/dtos.py（或 application/event_view.py）
def event_view(e: WorldEvent, name: str) -> EventView: ...
```

三个构造点全部调它，**不各自抽字段**：`query_service.events()`、`report_service` 三节视图函数、`query_service._guild_recent_events()`。这是与「render_event 是渲染单一源」对称的「event_view 是构造单一源」。§8.2 反漂移守卫扩到覆盖此 helper 为 EventView 唯一构造入口。

### 6.2 隐私护栏留在 application（回归护栏，非可选）

对抗复核隐私 Major 2：现有「隐藏/查无玩家整条跳过」逻辑活在渲染循环内。下移 wording 后，**跳过与 strict 过滤必须在 application 构造 EventView 时完成**（在调用 `event_view()` 之前 `continue`）：

- **跳过**：`if e.subject_type == "player" and e.subject_key not in names: continue`——覆盖：
  - `query_service.events()` 的**单一构造循环**（`today_only` 两种调用共用同一跳过点，query_service.py:468 附近；`today_only` 只改查询窗口、不产生第二条分支）。
  - `report_service.daily()` 的 `_wording`→改 `_views` 后，**三节 records/growth/base_changes 全覆盖**（三节均经同一跳过 helper）。
  - `query_service._guild_recent_events()`（query_service.py:362-377）。
- **strict 世界主体过滤**：`keep_world_subject_under_strict(events, mode=="strict")` 在 events 与 today 两路径都保留（现已在，勿丢）。strict 下只剩 WORLD_DAY_MILESTONE/ONLINE_RECORD 能进 EventView，故透 `event_type` 不泄漏「有隐藏玩家在活动」。
- **guild 近期动态 strict**：`_guild_recent_events` 现不施 `keep_world_subject_under_strict`，仅靠 `formatters.py:129` 的 `if not strict` 遮整节。改具名字段后原始内部键已不进 EventView（6.1 已封），此脆弱点顺带关闭，无需额外改动。

### 6.3 render_event 落 presentation（**定死签名**）

- `presentation/event_wording.py` 的 `event_wording(event: WorldEvent, name: str) -> str` → **`render_event(view: EventView) -> str`**（**定死吃 EventView，不留散参备选**——与 §6.4 调用、§8.4 测试写法对齐）。
- dispatch on `view.event_type`，读具名字段，**f-string 逐字不变**（下表逐字复制自现 `event_wording.py:29-46`）：

| EventType | 渲染串（逐字保真） |
|---|---|
| PLAYER_LEVEL_UP | `{name} 升级 Lv{old}→Lv{new}`（缺省 `?`）|
| NEW_PLAYER | `新玩家 {name} 加入世界` |
| NEW_GUILD | `新公会「{name}」出现` |
| NEW_BASE | `新据点「{name}」确认` |
| BASE_VANISHED | `据点「{name}」疑似消失（连续多次未观察到）` |
| WORKER_DELTA | `据点「{name}」工作帕鲁 {prev}→{cur}`（缺省 `?`）|
| WORLD_DAY_MILESTONE | `世界迎来第 {milestone} 天`（缺省 `?`）|
| ONLINE_RECORD | `在线人数新纪录 {value} 人`（缺省 `?`）|
| 未知兜底 | `event_type.value`（保留现有 fallback，不冒异常）|

- **单一真相源不变**：render_event 仍是八类措辞的唯一来源，只是消费者收窄为 `formatters`（presentation→presentation）。events/today/guild-info 三处仍共用它，不另写措辞。

### 6.4 消费方改动（presentation + application 返回类型）

- `presentation/formatters.py`：`format_events`（233,238,248,250）、`format_today`（495）、guild-info 据点动态渲染——从「读 `e.summary` / 直接用字符串项」改为「逐条 `render_event(view)`」。
- `application/query_service.py`：`events()` 返回 `list[EventView]`；`_guild_recent_events()` 返回 `list[EventView]`（`GuildDetailDTO.recent_events: list[EventView]`）。停止 import event_wording。
- `application/report_service.py`：`_wording` → `_views` 返回 `list[EventView]`；`DailyReport.records/growth/base_changes: list[EventView]`。停止 import event_wording。`DailyReport.summary`（一行头部摘要）与本组件无关，保持 str 不变。

## 7. 组件④：routing ErrorCode

### 7.1 枚举与 Resolution 契约（**定死归宿**）

`RoutingError` 枚举与 `Resolution` **同放 `application/routing_service.py`**（Resolution 已在此、零新模块、无环）。presentation 侧以 `from ..application.routing_service import RoutingError` 消费。

```python
# application/routing_service.py
class RoutingError(Enum):
    NO_SERVER_CONFIGURED = "no_server_configured"
    SINGLE_NOT_AUTHORIZED = "single_not_authorized"
    PRIVATE_RESTRICTED = "private_restricted"
    SERVER_UNKNOWN = "server_unknown"          # 带参 server
    NOT_AUTHORIZED = "not_authorized"          # 带参 server
    ACTIVE_SERVER_STALE = "active_server_stale"
    NO_SERVER_RESOLVED = "no_server_resolved"

@dataclass(slots=True)
class Resolution:
    server: ServerConfig | None
    error: RoutingError | None
    error_params: dict = field(default_factory=dict)   # 仅 server_unknown/not_authorized 用 {server: ...}
```

`routing_service.py:9` 的 `from ..presentation.locale import L` **删除**（L 仅在 resolve() 用，删调用即净删 import——routing 达到 0 处 presentation import）。

### 7.2 8 处调用点 → 7 个枚举码（字节保真锚点）

routing_service.resolve() 内共 **8 处 L() 调用**映射到 **7 个枚举码**（74 与 89 共用同码）：

| routing_service.py 行 | 现 `L(...)` | 改为 |
|---|---|---|
| 74, 89 | `L("no_server_configured")` | `Resolution(None, RoutingError.NO_SERVER_CONFIGURED)` |
| 78 | `L("single_not_authorized")` | `RoutingError.SINGLE_NOT_AUTHORIZED` |
| 93 | `L("private_restricted")` | `RoutingError.PRIVATE_RESTRICTED` |
| 99 | `L("server_unknown", server=override)` | `RoutingError.SERVER_UNKNOWN`, params `{"server": override}` |
| 101 | `L("not_authorized", server=srv.server_id)` | `RoutingError.NOT_AUTHORIZED`, params `{"server": srv.server_id}` |
| 110 | `L("active_server_stale")` | `RoutingError.ACTIVE_SERVER_STALE` |
| 127 | `L("no_server_resolved")` | `RoutingError.NO_SERVER_RESOLVED` |

### 7.3 Resolution.error 消费点全貌（**复核 Blocker：含 application 两处**）

presentation 新增单点 helper `render_routing_error(err: RoutingError, params: dict) -> str`（内部 `L(err.value, **params)`，逐字复现原输出）。`err` 为 None 时返回 `""`。消费点共 **6 处，分两类**：

**A. presentation 侧（直接调 render_routing_error）—— 4 处：**
| 位置 | 现状 | 改为 |
|---|---|---|
| `commands.py:136` | `_resolve_world` 元组返回 `res.error` | `render_routing_error(res.error, res.error_params)` |
| `commands.py:698` | kick/ban 内联 `L("admin_resolve_failed", reason=resolution.error or "")` | `reason=render_routing_error(resolution.error, resolution.error_params)` |
| `commands.py:754` | shutdown(require) 内联，同上 | 同上 |
| `commands.py:767` | stop(require) 内联，同上 | 同上 |

**B. application 侧（admin_service，绝不在 app 层渲染）—— 2 处：**
| 位置 | 现状 | 改为 |
|---|---|---|
| `admin_service.py:75` | `_execute` resolve 失败 `params={"reason": resolution.error or ""}` | **透传枚举**：`params={"error": resolution.error, "error_params": resolution.error_params}` |
| `admin_service.py:234` | `execute_target` resolve 失败，同上 | 同上 |

这两处产 `AdminResult(message_key="admin_resolve_failed", ...)`，由 **presentation 边界 `_render_result` 渲染**：
- `commands.py:878-879`：`if key == "admin_resolve_failed": return L("admin_resolve_failed", reason=render_routing_error(params.get("error"), params.get("error_params", {})))`。

> **为何必须这样**（复核 Blocker）：admin_service 在 application 层，**不能**调 presentation 的 render_routing_error（否则重开本 spec 要删的依赖）。故 app 层只**透传枚举**，渲染在 `_render_result`（presentation）边界完成。若照原 spec 只改 commands.py、漏 admin_service，enum 会被 `L(reason=<枚举>)` 字面渲染 → admin 写失败文案字节炸。

**零改动确认**：`commands.py:821-823`（confirm 的 resolve 失败）返回**静态** `L("admin_confirm_stale")`，**不读 `resolution.error`** → `Resolution.error` 由 str→枚举对它零影响、字节不变，无需改动。

> **字节陷阱（复核 #1 最易破处）**：`admin_resolve_failed` 把 resolution 错误**嵌套**在 `❌ 无法执行：{reason}`（locale.py:130）里。`render_routing_error` 必须逐字复现原 `L(key, **params)` 输出。commands 级测试（断言最终渲染串）+ golden 是兜底护栏。

## 8. 测试策略与防回归

### 8.1 验收前提
- 全部 `*_golden_test.py` 的 `.txt` 输出**字节不变**（`today.txt` 等）。这是重构正确性的最终裁判。
- `ruff` + `mypy`（45 文件）+ 前端 typecheck + no-drift 全绿。

### 8.2 新增/重写的架构守卫（锁死本轮的赢）
- **重写** `output_consistency_test.py:64`：现断言「`event_wording(` 出现在 query_service+report_service 源码」将变红（相 3 恰好移走这些调用）——改为：断言 `render_event` 是 presentation 单一措辞源（formatters 委托它），且 query/report **不再** import event_wording。**此重写必须落在相 3**（与移除 event_wording 同相），非相 5。
- **扩展** 反漂移守卫覆盖 `event_view()` 为 EventView 唯一构造入口（三构造点不各自抽字段）。
- **新增** `application/*.py` 无 `from ..presentation` 静态守卫（AST 或源码扫描），锚定 5 处清零、防未来回潮——落**相 5**。
- **迁移** 绝对自导入静态守卫覆盖 `shared/`。

### 8.3 隐私防回归测试（对抗复核硬要求）
- EventView 构造点跳隐藏/查无玩家：events 单循环 + today 三节 + guild 近期动态，逐路径覆盖。
- strict 下 events/today 只留世界主体（WORLD_DAY_MILESTONE/ONLINE_RECORD）。
- EventView 不含 `subject_key/subject_type`；内部键（guild_key/day/worker_count/confidence/first_missing_day）不可从 EventView 到达。
- **`gamedata_output_suppression_test.py`（隐私相邻护栏，见 §8.4）**：其 game-data 屏蔽断言（line 131）改为对 `EventType` 成员判定，**保持护栏咬合**——否则枚举化会让它假绿、静默架空 game-data 事件屏蔽。

### 8.4 重写的既有测试（诚实预算）
| 文件 | 改动 | 量级 |
|---|---|---|
| `report_service_test.py` | 断言 `rep.growth/records/base_changes` 的 worded 串 → EventView 字段断言 | **~33 断言（最大头）** |
| `event_wording_test.py` | `event_wording(e, name)` → `render_event(view)` 签名 | ~9 |
| `query_service_bases_test.py` | `.summary` 断言 → EventView 字段；`event_type == "new_player"`（str→EventType）| ~5 |
| `gamedata_output_suppression_test.py` | **line 131** `d.event_type in {str}` → 对 `EventType` 成员判定（护栏保命）；**123/126** `"新玩家" in r` → EventView 字段/render 断言（否则 EventView 非容器抛 TypeError）；`base_changes==[]` 存活 | ~4 |
| `formatters_test.py` | `_event()` helper 建 `EventDTO(summary=)` → `EventView(...)`；4-5 test | 1 helper + ~5 |
| `formatters_golden_test.py` | `_Report` fake 的 records/growth/base_changes 串列 → EventView 列；golden 字节不变 | 1 fixture |
| `commands_guild_test.py` | `GuildDetailDTO(recent_events=[串])` → `recent_events=[EventView]`（类型改，非改路径）| 1 fixture |
| `dtos_test.py` | `EventDTO(summary=)`、`GuildDetailDTO(recent_events=[串])` → EventView | ~3 |
| `routing_service_resolve_test.py` | `Resolution.error` 子串断言 → RoutingError 枚举断言 | ~4 |
| `routing_world_mode_test.py` | 同上 | ~2 |
| dtos/command_registry import 路径清扫 | 机械改路径（以 grep 全量为准）| ~8+6 文件 |

**受影响测试文件 ~12–14（改写）+ ~14（纯路径清扫）**。绝大多数 commands 级测试与全部 golden `.txt` **应存活**（断言最终渲染字节，本设计保其不变）——这是每相的真实验收。

## 9. 实施相位（建议，供 writing-plans 细化）

| 相 | 内容 | 带的测试改动 | 独立验收 |
|---|---|---|---|
| 1 | `command_registry → shared/`，退役 config.py:342-350 延迟 import | 6 command_registry 消费测试改路径 | 全绿；命名空间冒烟 |
| 2 | `dtos → application`（EventDTO 暂留、暂不改 EventView）| dtos 路径清扫测试 | 全绿；**中间态**：query_service 仍 import event_wording（还在 presentation），application→presentation 未清零属预期，此相不加 no-presentation 守卫 |
| 3 | `event_view()` + `EventView` + `render_event` + 隐私护栏 + 停 import event_wording | report_service_test（~33）、event_wording_test、query_service_bases_test、gamedata_output_suppression_test、formatters_test、formatters_golden_test、commands_guild_test、dtos_test；**output_consistency_test 重写（本相，非相 5）** | golden 字节对比；隐私守卫 |
| 4 | routing `RoutingError` + 6 消费点（含 admin_service 2 处透传 + _render_result 边界渲染）| routing_service_resolve_test、routing_world_mode_test；commands_admin_write_test 存活验证 | admin_resolve_failed 字节保真 |
| 5 | 新增 `application` 无 presentation-import 静态守卫 + 全分支终审 | 新增守卫测试 | 5 处清零锚定；全绿 + golden |

每相独立可跑、独立绿。相 2 的中间态（未清零）是预期，no-presentation 守卫直到相 5 才加。

## 10. 验收标准
- [ ] `application/*.py` 中 `from ..presentation` import 数 = **0**（相 5 静态守卫锚定）。
- [ ] 全部 golden `.txt` 字节不变。
- [ ] 后端全绿（含重写的 output_consistency/隐私/gamedata/routing 测试）+ ruff + mypy + no-drift。
- [ ] `config.py:342-350` 整块函数体延迟 import 退役、全部上提模块顶层（command_registry + command_permissions 两条）。
- [ ] `render_event(view: EventView)` 是八类措辞唯一源，仅 formatters 消费；`event_view()` 是 EventView 唯一构造入口，三处共用不漂移。
- [ ] EventView 无 subject_key/subject_type、无内部键可达（隐私守卫锚定）；gamedata 屏蔽护栏（test:131）改枚举判定后仍咬合。
- [ ] routing 0 处 presentation import；6 消费点（commands 4 + admin_service 2 透传）全覆盖；admin_resolve_failed 嵌套字节保真；commands.py:821 confirm 零改动。
