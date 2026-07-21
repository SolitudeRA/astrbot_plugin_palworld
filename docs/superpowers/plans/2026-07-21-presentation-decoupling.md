# presentation 解耦 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 application 层对 presentation 层的 5 处反向依赖（依赖倒置违规），application 只依赖 domain + infrastructure + 新增中立 shared，零运行时行为/输出字节变化。

**Architecture:** ① command_registry 迁中立 shared/ 包；② dtos 迁 application；③ EventDTO 替为 typed EventView + application 单一构造入口 event_view()，措辞单一源 event_wording 重构为 presentation 的 render_event(view)；④ routing 返回 RoutingError 枚举、presentation 边界渲染。EventView 与 render_event 先与旧代码并存、各自带测试转绿，再一次性原子切换 + 删旧，全程用 golden `.txt` 字节不变作安全网。

**Tech Stack:** Python 3.13、pytest、ruff、mypy、dataclass(slots)、Enum、Protocol 无关（本 spec 不碰 adapters）。

## Global Constraints

- **零字节变化**：所有 golden `*_golden_test.py` 的 `.txt` 输出字节不变——重构正确性的最终裁判。
- **零行为/语义变化**：纯结构重构，无新功能。
- 全绿门槛：后端 pytest 全绿 + `ruff check` + `mypy`（45 文件）+ 前端 typecheck + no-drift。
- **AstrBot 命名空间安全**：新包 `shared/__init__.py` 保持空；所有消费者用相对 import（`from ..shared...`），绝不绝对自导入（历史踩坑，有静态守卫）。
- **commit 不提 Claude**：commit message 正文与尾行都不出现 Claude/Co-Authored-By（全局 attribution.commit="" 已设）。
- **版本不动**：零行为变化，不 bump 六源版本。
- 分支：`feat/presentation-decoupling`（已建，spec 已提交 @28b5b26）。

---

## File Structure

**Create:**
- `palworld_terminal/shared/__init__.py` — 空文件（新中立包）
- `palworld_terminal/shared/command_registry.py` — 从 presentation 原样迁入
- `palworld_terminal/application/dtos.py` — 从 presentation 迁入 + EventView + event_view()

**Modify:**
- `palworld_terminal/config.py` — 延迟 import 上提顶层
- `palworld_terminal/application/command_permissions.py` — command_registry import 路径
- `palworld_terminal/application/query_service.py` — dtos 路径、events/guild 产 EventView、停 import event_wording
- `palworld_terminal/application/report_service.py` — DailyReport EventView、_views、停 import event_wording
- `palworld_terminal/application/routing_service.py` — RoutingError 枚举、Resolution.error 类型、停 import locale
- `palworld_terminal/application/admin_service.py` — resolve 失败透传枚举
- `palworld_terminal/presentation/event_wording.py` — event_wording → render_event(view)
- `palworld_terminal/presentation/formatters.py` — dtos 路径、command_registry 路径、render_event 调用
- `palworld_terminal/presentation/commands.py` — dtos/command_registry 路径、render_routing_error、_render_result
- `palworld_terminal/presentation/config_view.py` — command_registry import 路径
- 测试文件若干（各 Task 内列明）

**Delete（Task 5 内）:** `palworld_terminal/presentation/dtos.py`（迁走后）、`EventDTO`、旧 `event_wording` 函数体。

---

## Task 1: command_registry → shared/ 包 + 退役 config.py 延迟 import

**Files:**
- Create: `palworld_terminal/shared/__init__.py`（空）、`palworld_terminal/shared/command_registry.py`
- Delete: `palworld_terminal/presentation/command_registry.py`
- Modify: `application/command_permissions.py:11`、`presentation/formatters.py:7`、`presentation/commands.py:16`、`presentation/config_view.py:15`、`config.py:342-350`
- Test: `tests/unit/command_names_test.py`、`command_registry_hierarchy_test.py`、`formatters_hierarchy_test.py`、`setup_gate_test.py`、`formatters_admin_help_test.py`、`command_permissions_meta_test.py`（改 import 路径）；新增/扩展绝对自导入守卫覆盖 shared/

**Interfaces:**
- Produces: `palworld_terminal.shared.command_registry`（导出与原 presentation.command_registry 全同：`DISPATCH, FLAT_ACTIONS, METHOD_PATH, PAL_REGISTERED, PAL_COMMAND_STRINGS, _NON_LOCKABLE, LOCKABLE_COMMANDS, HELP_TEXT, ActionSpec`）

- [ ] **Step 1: 移动文件（内容零改动）**

```bash
git mv palworld_terminal/presentation/command_registry.py palworld_terminal/shared/command_registry.py
touch palworld_terminal/shared/__init__.py
```

- [ ] **Step 2: 重指 4 个源消费者 import**

`application/command_permissions.py:11`：
```python
# before
from ..presentation.command_registry import (
# after
from ..shared.command_registry import (
```
`presentation/formatters.py:7`、`presentation/commands.py:16`、`presentation/config_view.py:15`：
```python
# before: from .command_registry import ...   /   from ..presentation.command_registry import ...
# after:  from ..shared.command_registry import ...
```
（formatters/commands/config_view 均在 presentation 包内，改为 `..shared.command_registry`。以各文件实际现有写法为准，只换模块路径段。）

- [ ] **Step 3: 上提 config.py 延迟 import（退役整块 hack）**

`config.py:342-350` 现为函数体内延迟 import 块。将其整块上提模块顶层，并与 `config.py:8` 已有的 `from .application.command_permissions import CommandOverride` 合并同源：
```python
# 顶层 import 区（替换原 config.py:8 单名字行）
from .application.command_permissions import (
    COMMAND_META,
    CommandOverride,
    admin_configurable,
    admin_forced_true,
    enable_configurable,
    upstream_unavailable,
    upstream_unavailable_group,
)
from .shared.command_registry import DISPATCH
```
然后删除函数体内 `config.py:342-350` 的延迟 import 块（及其上方 340-341 关于「函数体内相对 import 避免循环」的注释）。
（config→application.command_permissions 顶层导入已被 config.py:8 证明安全；command_registry 迁 shared 后为零依赖叶子，无环。）

- [ ] **Step 4: 重指 6 个测试文件 import 路径**

将上述 6 测试中 `from ...presentation.command_registry import` / `from palworld_terminal.presentation.command_registry import` 改为 `...shared.command_registry`。断言值不变，仅路径。

- [ ] **Step 5: 扩展绝对自导入静态守卫覆盖 shared/**

找到现有绝对自导入防回归测试（grep `sys.path` / `absolute` in tests，或 `tests/unit/*import*`）。确保其扫描目录包含 `palworld_terminal/shared/`。若守卫按包列表枚举，追加 `shared`。

- [ ] **Step 6: 跑测试**

Run: `python -m pytest tests/unit/command_names_test.py tests/unit/command_registry_hierarchy_test.py tests/unit/formatters_hierarchy_test.py tests/unit/setup_gate_test.py tests/unit/formatters_admin_help_test.py tests/unit/command_permissions_meta_test.py -q`
Expected: PASS（值不变，路径已更）

- [ ] **Step 7: 全量 + 静态检查**

Run: `python -m pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: 全 PASS。若 mypy 报 config.py 顶层 import 环 → 说明 command_permissions 有对 config 的顶层反向 import，退回把 command_permissions 那几行留在函数体、只上提 command_registry（并相应放宽 §10 措辞）。正常应无环。

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: command_registry 迁中立 shared 包 + 退役 config 延迟 import"
```

---

## Task 2: dtos → application（EventDTO 暂留原样）

**Files:**
- Create: `palworld_terminal/application/dtos.py`
- Delete: `palworld_terminal/presentation/dtos.py`
- Modify: `presentation/formatters.py:13`、`presentation/commands.py:18`、`application/query_service.py:11`
- Test: `dtos_test.py`、`formatters_test.py`、`status_detail_shape_test.py`、`config_view_status_test.py`（改 import 路径；以 grep 全量为准）

**Interfaces:**
- Produces: `palworld_terminal.application.dtos`（导出与原 presentation.dtos 全同，含 `EventDTO` 暂不改）

- [ ] **Step 1: 移动文件**

```bash
git mv palworld_terminal/presentation/dtos.py palworld_terminal/application/dtos.py
```

- [ ] **Step 2: 全量定位 dtos 消费者**

Run: `grep -rn "presentation.dtos\|from .dtos import\|from \.\.presentation\.dtos" palworld_terminal tests`
对每个命中改路径：
- `presentation/formatters.py:13`：`from .dtos import ...` → `from ..application.dtos import ...`
- `presentation/commands.py:18`：同上 → `from ..application.dtos import ...`
- `application/query_service.py:11`：`from ..presentation.dtos import ...` → `from .dtos import ...`
- 测试文件：`from palworld_terminal.presentation.dtos` → `from palworld_terminal.application.dtos`

- [ ] **Step 3: 跑测试**

Run: `python -m pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: 全 PASS（纯路径迁移，EventDTO 未改）。

> **中间态说明（预期）**：本相后 `query_service.py:26` 仍 `from ..presentation.event_wording import event_wording`——application→presentation 尚未清零，属预期。no-presentation 静态守卫直到 Task 7 才加，本相不加。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: dtos 迁 application 层（EventDTO 暂留）"
```

---

## Task 3: 新增 EventView + event_view()（与 EventDTO 并存）

**Files:**
- Modify: `palworld_terminal/application/dtos.py`（新增 EventView + event_view，EventDTO 暂留）
- Test: `tests/unit/event_view_test.py`（新建）

**Interfaces:**
- Produces:
  - `EventView(occurred_at:int, event_type:EventType, name:str, old/new/prev/cur/milestone/value:int|None=None)`
  - `event_view(e: WorldEvent, name: str) -> EventView` —— EventView 唯一构造入口

- [ ] **Step 1: 写失败测试**

`tests/unit/event_view_test.py`：
```python
from palworld_terminal.application.dtos import EventView, event_view
from palworld_terminal.domain.enums import EventType
from palworld_terminal.domain.models import WorldEvent


def _ev(event_type, payload, *, subject_type="world", subject_key="w", occurred_at=100):
    return WorldEvent(
        world_id="s1:w", event_type=event_type, subject_type=subject_type,
        subject_key=subject_key, payload=payload, occurred_at=occurred_at,
    )


def test_level_up_extracts_old_new_only():
    v = event_view(_ev(EventType.PLAYER_LEVEL_UP, {"old": 9, "new": 12},
                       subject_type="player", subject_key="p1"), "Neo")
    assert v.event_type is EventType.PLAYER_LEVEL_UP
    assert v.name == "Neo"
    assert (v.old, v.new) == (9, 12)
    assert v.prev is v.cur is v.milestone is v.value is None


def test_new_base_never_exposes_internal_keys():
    # NEW_BASE.payload 有 guild_key/worker_count/confidence——绝不进 EventView（§6.1 隐私）
    v = event_view(_ev(EventType.NEW_BASE,
                       {"guild_key": "G#7", "worker_count": 4, "confidence": "high"},
                       subject_type="base", subject_key="b1"), "河谷矿场")
    assert v.name == "河谷矿场"
    assert v.old is v.new is v.prev is v.cur is v.milestone is v.value is None
    # EventView 无任何字段承载 guild_key/worker_count/confidence
    assert not hasattr(v, "guild_key")


def test_milestone_extracts_milestone_not_day():
    v = event_view(_ev(EventType.WORLD_DAY_MILESTONE, {"milestone": 5, "day": 5}), "")
    assert v.milestone == 5
    assert v.value is None  # 'day' 不进任何字段


def test_online_record_extracts_value():
    v = event_view(_ev(EventType.ONLINE_RECORD, {"value": 17}), "")
    assert v.value == 17


def test_worker_delta_extracts_prev_cur():
    v = event_view(_ev(EventType.WORKER_DELTA, {"prev": 2, "cur": 5},
                       subject_type="base", subject_key="b1"), "河谷矿场")
    assert (v.prev, v.cur) == (2, 5)


def test_event_view_carries_no_subject_fields():
    v = event_view(_ev(EventType.NEW_PLAYER, {}, subject_type="player", subject_key="p1"), "Neo")
    assert not hasattr(v, "subject_key")
    assert not hasattr(v, "subject_type")
```
（`WorldEvent` 构造参数以 `domain/models.py` 实际字段为准，实现期核对。）

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/event_view_test.py -q`
Expected: FAIL（ImportError: EventView / event_view 未定义）

- [ ] **Step 3: 实现 EventView + event_view**

`application/dtos.py` 顶部 import 增补：
```python
from ..domain.enums import EventType   # 若已 import 其它 enums，合并
from ..domain.models import WorldEvent
```
新增（EventDTO 上方或下方，EventDTO 暂不删）：
```python
@dataclass(slots=True)
class EventView:
    occurred_at: int
    event_type: EventType
    name: str
    old: int | None = None
    new: int | None = None
    prev: int | None = None
    cur: int | None = None
    milestone: int | None = None
    value: int | None = None


def event_view(e: WorldEvent, name: str) -> EventView:
    """WorldEvent → EventView：EventView 唯一构造入口（spec §6.1a）。
    只抽 render_event 需要的具名字段；内部键（guild_key/day/worker_count/
    confidence/first_missing_day）不被读取、绝不进 EventView（§6.1 隐私加固）。"""
    p = e.payload or {}
    return EventView(
        occurred_at=e.occurred_at,
        event_type=e.event_type,
        name=name,
        old=p.get("old"),
        new=p.get("new"),
        prev=p.get("prev"),
        cur=p.get("cur"),
        milestone=p.get("milestone"),
        value=p.get("value"),
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/event_view_test.py -q && mypy palworld_terminal`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: 新增 EventView typed DTO + event_view 单一构造入口"
```

---

## Task 4: 新增 render_event(view)（与 event_wording 并存）

**Files:**
- Modify: `palworld_terminal/presentation/event_wording.py`（新增 render_event，event_wording 暂留）
- Test: `tests/unit/render_event_test.py`（新建）

**Interfaces:**
- Consumes: `application.dtos.EventView`
- Produces: `render_event(view: EventView) -> str` —— 八类措辞唯一渲染源

- [ ] **Step 1: 写失败测试（逐字对齐现 event_wording 输出）**

`tests/unit/render_event_test.py`：
```python
from palworld_terminal.application.dtos import EventView
from palworld_terminal.domain.enums import EventType
from palworld_terminal.presentation.event_wording import render_event


def test_level_up():
    v = EventView(occurred_at=1, event_type=EventType.PLAYER_LEVEL_UP, name="Neo", old=9, new=12)
    assert render_event(v) == "Neo 升级 Lv9→Lv12"


def test_level_up_missing_defaults_to_question():
    v = EventView(occurred_at=1, event_type=EventType.PLAYER_LEVEL_UP, name="Neo")
    assert render_event(v) == "Neo 升级 Lv?→Lv?"


def test_new_player():
    v = EventView(occurred_at=1, event_type=EventType.NEW_PLAYER, name="Neo")
    assert render_event(v) == "新玩家 Neo 加入世界"


def test_new_guild():
    v = EventView(occurred_at=1, event_type=EventType.NEW_GUILD, name="曙光")
    assert render_event(v) == "新公会「曙光」出现"


def test_new_base():
    v = EventView(occurred_at=1, event_type=EventType.NEW_BASE, name="河谷矿场")
    assert render_event(v) == "新据点「河谷矿场」确认"


def test_base_vanished():
    v = EventView(occurred_at=1, event_type=EventType.BASE_VANISHED, name="河谷矿场")
    assert render_event(v) == "据点「河谷矿场」疑似消失（连续多次未观察到）"


def test_worker_delta():
    v = EventView(occurred_at=1, event_type=EventType.WORKER_DELTA, name="河谷矿场", prev=2, cur=5)
    assert render_event(v) == "据点「河谷矿场」工作帕鲁 2→5"


def test_world_day_milestone():
    v = EventView(occurred_at=1, event_type=EventType.WORLD_DAY_MILESTONE, milestone=5, name="")
    assert render_event(v) == "世界迎来第 5 天"


def test_online_record():
    v = EventView(occurred_at=1, event_type=EventType.ONLINE_RECORD, value=17, name="")
    assert render_event(v) == "在线人数新纪录 17 人"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/unit/render_event_test.py -q`
Expected: FAIL（render_event 未定义）

- [ ] **Step 3: 实现 render_event（f-string 逐字复制 event_wording.py:29-46）**

`presentation/event_wording.py` 顶部增补 import：
```python
from ..application.dtos import EventView
```
文件尾追加（event_wording 函数暂留不删）：
```python
def _or_q(v: int | None) -> object:
    return v if v is not None else "?"


def render_event(view: EventView) -> str:
    """EventView → 面向用户措辞（spec §4.4 八类表，逐字对齐旧 event_wording）。
    八类措辞唯一渲染源；未知类型兜底返回枚举值，不冒异常。"""
    et = view.event_type
    if et is EventType.PLAYER_LEVEL_UP:
        return f"{view.name} 升级 Lv{_or_q(view.old)}→Lv{_or_q(view.new)}"
    if et is EventType.NEW_PLAYER:
        return f"新玩家 {view.name} 加入世界"
    if et is EventType.NEW_GUILD:
        return f"新公会「{view.name}」出现"
    if et is EventType.NEW_BASE:
        return f"新据点「{view.name}」确认"
    if et is EventType.BASE_VANISHED:
        return f"据点「{view.name}」疑似消失（连续多次未观察到）"
    if et is EventType.WORKER_DELTA:
        return f"据点「{view.name}」工作帕鲁 {_or_q(view.prev)}→{_or_q(view.cur)}"
    if et is EventType.WORLD_DAY_MILESTONE:
        return f"世界迎来第 {_or_q(view.milestone)} 天"
    if et is EventType.ONLINE_RECORD:
        return f"在线人数新纪录 {_or_q(view.value)} 人"
    return et.value
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/unit/render_event_test.py -q && mypy palworld_terminal`
Expected: PASS

> mypy 检查点：`presentation/event_wording.py` 现同时被 application（旧 event_wording）与自身（新 render_event import application.dtos）牵扯。render_event import application.dtos = presentation→application，方向正确，无环。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: 新增 render_event(view) 措辞渲染源（与 event_wording 并存）"
```

---

## Task 5: 原子切换——query/report/formatters 改用 EventView/render_event + 删旧 + 重写结构测试

> 这是**不可分割的原子任务**：`EventDTO.summary` 由 query/report 生产、formatters 消费，producer 与 consumer 必须同一提交切换，否则套件中途破。golden `.txt` 字节不变是本任务的安全网。

**Files:**
- Modify: `application/query_service.py`（events + _guild_recent_events + GuildDetailDTO.recent_events 类型 + 停 import event_wording）、`application/report_service.py`（DailyReport + _views + 停 import event_wording）、`application/dtos.py`（删 EventDTO、GuildDetailDTO.recent_events / EventDTO 相关类型改 EventView）、`presentation/formatters.py`（render_event 调用）、`presentation/event_wording.py`（删旧 event_wording 函数体）
- Test（重写）：`report_service_test.py`、`query_service_bases_test.py`、`gamedata_output_suppression_test.py`、`formatters_test.py`、`formatters_golden_test.py`、`dtos_test.py`、`commands_guild_test.py`、`output_consistency_test.py`

**Interfaces:**
- Consumes: `event_view`（Task 3）、`render_event`（Task 4）
- Produces: `query_service.events() -> list[EventView]`；`GuildDetailDTO.recent_events: list[EventView]`；`DailyReport.records/growth/base_changes: list[EventView]`

- [ ] **Step 1: 改 query_service（events + guild）**

`application/query_service.py`：
- import 行：删 `from ..presentation.event_wording import event_wording`；`from .dtos import ...` 增补 `EventView, event_view`（EventDTO 从导入列表移除）。
- `events()` 构造循环（约 465-473）：
```python
# before
dtos: list[EventDTO] = []
for e in events:
    if e.subject_type == "player" and e.subject_key not in names:
        continue
    dtos.append(EventDTO(
        occurred_at=e.occurred_at, event_type=e.event_type.value,
        summary=event_wording(e, names.get(e.subject_key, "")),
    ))
self._cache.set(key, dtos, self._EVENTS_TTL)
return dtos
# after
views: list[EventView] = []
for e in events:
    if e.subject_type == "player" and e.subject_key not in names:
        continue
    views.append(event_view(e, names.get(e.subject_key, "")))
self._cache.set(key, views, self._EVENTS_TTL)
return views
```
方法签名 `async def events(...) -> list[EventView]`。
- `_guild_recent_events`（362-377）：签名 `-> list[EventView]`，末行
```python
# before
return [event_wording(e, names.get(e.subject_key, "")) for e in relevant]
# after
return [event_view(e, names.get(e.subject_key, "")) for e in relevant]
```

- [ ] **Step 2: 改 dtos（GuildDetailDTO.recent_events 类型 + 删 EventDTO）**

`application/dtos.py`：
- `GuildDetailDTO.recent_events` 字段类型 `list[str]` → `list[EventView]`。
- 删除 `EventDTO` dataclass（已无生产者）。

- [ ] **Step 3: 改 report_service（DailyReport + _views）**

`application/report_service.py`：
- import：删 `from ..presentation.event_wording import event_wording`；增 `from .dtos import EventView, event_view`。
- `DailyReport.records/growth/base_changes` 字段类型 `list[str]` → `list[EventView]`。
- `_wording` 改名 `_views`、返回 `list[EventView]`：
```python
def _views(evs: list[WorldEvent]) -> list[EventView]:
    out: list[EventView] = []
    for e in evs:
        if e.subject_type == "player" and e.subject_key not in names:
            continue
        out.append(event_view(e, names.get(e.subject_key, "")))
    return out
```
- 三节构造（142-154）把 `_wording` 全改 `_views`；`new_player_lines` 改名 `new_player_views`（`_summary` 仍用 `len(new_player_views)`，计数语义不变、字节保真）。

- [ ] **Step 4: 改 formatters（render_event 调用）**

`presentation/formatters.py`：
- import：增 `from .event_wording import render_event`（若未导入）；`EventDTO` 从 dtos 导入列表移除，改导入 `EventView`（`format_events` 签名类型）。
- `format_events`（212 签名、233、238、248、250）：
```python
def format_events(events: list[EventView], server_name: str, *, ...):   # 212
tail = fold([render_event(e) for e in events], fold_limit, "条")[len(visible):]   # 233
lines.extend(f"· {time_of_day(e.occurred_at, tz)} {render_event(e)}" for e in visible)   # 238
lines.append(f"· {time_of_day(e.occurred_at, tz)} {render_event(e)}")   # 248
lines.append(f"· {render_event(e)}")   # 250
```
- `format_guild`（140）：
```python
lines.extend(fold([f"· {render_event(ev)}" for ev in dto.recent_events], fold_limit, "条"))
```
- `format_today`（495）：
```python
lines.extend(fold([f"· {render_event(x)}" for x in items], fold_limit, "条"))
```

- [ ] **Step 5: 删旧 event_wording 函数体**

`presentation/event_wording.py`：删除 `event_wording(event, name)` 函数（render_event 已取代）。保留 render_event + _or_q + imports。

- [ ] **Step 6: 跑 golden 安全网（必须字节不变）**

Run: `python -m pytest tests/unit/formatters_golden_test.py -q`
Expected: 若 fixture 未改会 FAIL（fixture 仍传 str 列）——进 Step 7 改 fixture；改完后此测试字节 PASS 是本任务核心验收。

- [ ] **Step 7: 重写结构测试（8 文件）**

**转换规则**（对每个「断言 worded 串」的点）：断言从「串内容/子串」改为「EventView 字段或 render_event(view) 结果」。

- `formatters_golden_test.py`：`_Report` fake 的 records/growth/base_changes 从字符串列改 EventView 列：
```python
# before: records=["新玩家 Neo 加入世界"]
# after:  records=[EventView(occurred_at=.., event_type=EventType.NEW_PLAYER, name="Neo")]
```
golden `today.txt` 字节不变（render_event 复现原串）。
- `commands_guild_test.py`（recent_events fixture，约 98 行）：
```python
# before: GuildDetailDTO(..., recent_events=["新据点「河谷矿场」确认"])
# after:  GuildDetailDTO(..., recent_events=[EventView(occurred_at=.., event_type=EventType.NEW_BASE, name="河谷矿场")])
```
- `formatters_test.py`（`_event()` helper 约 371 行）：
```python
# before: def _event(...): return EventDTO(occurred_at=.., event_type="new_player", summary="...")
# after:  def _event(...): return EventView(occurred_at=.., event_type=EventType.NEW_PLAYER, name="...")
```
其余 format_events 用例随 helper 自动适配；若个别断言比对 summary 串，改为断言最终 format_events 输出串（不变）。
- `report_service_test.py`（~33 断言）：转换规则——
```python
# before: assert rep.growth == ["Neo 升级 Lv9→Lv12"]
# after:  assert [render_event(v) for v in rep.growth] == ["Neo 升级 Lv9→Lv12"]
#   —— 或断言字段： assert rep.growth[0].event_type is EventType.PLAYER_LEVEL_UP and (rep.growth[0].old, rep.growth[0].new) == (9, 12)
# before: assert "新玩家 Neo 加入世界" in rep.records
# after:  assert "新玩家 Neo 加入世界" in [render_event(v) for v in rep.records]
```
对全部 ~33 处按此规则机械转换（顶部 `from palworld_terminal.presentation.event_wording import render_event`）。计数类断言（`len(rep.growth)` 等）不变。
- `query_service_bases_test.py`（~5 处，234-285）：`d.summary == "..."` → `render_event(d) == "..."`；`event_type == "new_player"`（str）→ `event_type is EventType.NEW_PLAYER`。
- `dtos_test.py`：删 `EventDTO(summary=)` 用例或改 EventView；`GuildDetailDTO(recent_events=[串])` → `[EventView(...)]`。
- `gamedata_output_suppression_test.py`（**隐私护栏，须保命**）：
```python
# line 123/126（records 断容器 in）before: assert any("新玩家" in r for r in report.records)
#                                after: assert any("新玩家" in render_event(r) for r in report.records)
# line 126 同理（新公会/新据点 → render_event(r)）
# line 130-131（game-data 屏蔽护栏）before: base_family = {t.value for t in _GAME_DATA_EVENTS}; assert not any(d.event_type in base_family for d in dtos)
#                                  after: base_family = set(_GAME_DATA_EVENTS)  # EventType 成员集，非 .value 串集
#                                         assert not any(d.event_type in base_family for d in dtos)
# base_changes == [] 存活不变
```
- `output_consistency_test.py`（约 62-64，架构守卫**本相重写**）：现断言 `event_wording(` 出现在 query_service+report_service 源码——改为：
```python
# 措辞单一源现为 presentation.render_event，query/report 不再产措辞、不 import event_wording
import inspect
from palworld_terminal.application import query_service, report_service
for mod in (query_service, report_service):
    src = inspect.getsource(mod)
    assert "event_wording" not in src, f"{mod.__name__} 仍引用已废弃的 event_wording"
    assert "event_view(" in src, f"{mod.__name__} 未经 event_view 单一构造入口"
# render_event 是 formatters 唯一措辞源
from palworld_terminal.presentation import formatters
assert "render_event(" in inspect.getsource(formatters)
```

- [ ] **Step 8: 跑全量 + golden 字节验收**

Run: `python -m pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: 全 PASS。**特别确认** `formatters_golden_test.py` 全绿（golden `.txt` 字节不变）——若任何 `.txt` diff 非空，说明 render_event 未逐字复现，回 Task 4 对表核对。

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: query/report/formatters 原子切换 EventView + render_event，删 EventDTO/event_wording"
```

---

## Task 6: routing RoutingError 枚举 + 6 消费点（含 admin_service 透传）

> 原子任务：`Resolution.error` 由 str→枚举，全部 6 消费点必须同一提交切换。commands 级 + golden 测试字节不变是安全网。

**Files:**
- Modify: `application/routing_service.py`（RoutingError + Resolution + 8 调用点 + 停 import locale）、`application/admin_service.py`（75、234 透传枚举）、`presentation/commands.py`（render_routing_error + 136/698/754/767 + _render_result 878-879）
- Test（重写）：`routing_service_resolve_test.py`、`routing_world_mode_test.py`；验证存活：`commands_admin_write_test.py`、`commands_test.py`

**Interfaces:**
- Produces: `application.routing_service.RoutingError`（枚举）；`Resolution(server, error: RoutingError|None, error_params: dict)`
- Consumes（presentation）：`_render_routing_error(err, params) -> str`

- [ ] **Step 1: 写失败测试（routing 返回枚举）**

改 `routing_service_resolve_test.py` 中比对错误串的断言（约 59/66/117/124）为枚举断言，先让其对新契约失败：
```python
# before: assert "尚未" in res.error   /   assert res.error is not None
# after:  from palworld_terminal.application.routing_service import RoutingError
#         assert res.error is RoutingError.NO_SERVER_CONFIGURED
```
`routing_world_mode_test.py`（67/105）同理。

- [ ] **Step 2: 跑确认失败**

Run: `python -m pytest tests/unit/routing_service_resolve_test.py tests/unit/routing_world_mode_test.py -q`
Expected: FAIL（RoutingError 未定义 / res.error 仍是 str）

- [ ] **Step 3: 实现 RoutingError + Resolution + 8 调用点**

`application/routing_service.py`：
- import：删 `from ..presentation.locale import L`；增 `from enum import Enum`；`from dataclasses import dataclass, field`（field 若未导入）。
- 新增枚举：
```python
class RoutingError(Enum):
    NO_SERVER_CONFIGURED = "no_server_configured"
    SINGLE_NOT_AUTHORIZED = "single_not_authorized"
    PRIVATE_RESTRICTED = "private_restricted"
    SERVER_UNKNOWN = "server_unknown"
    NOT_AUTHORIZED = "not_authorized"
    ACTIVE_SERVER_STALE = "active_server_stale"
    NO_SERVER_RESOLVED = "no_server_resolved"
```
- `Resolution`：
```python
@dataclass(slots=True)
class Resolution:
    server: ServerConfig | None
    error: RoutingError | None
    error_params: dict = field(default_factory=dict)
```
- 8 处 `return Resolution(None, L(...))` 改（对照 spec §7.2）：
```python
# 74/89
return Resolution(None, RoutingError.NO_SERVER_CONFIGURED)
# 78
return Resolution(None, RoutingError.SINGLE_NOT_AUTHORIZED)
# 93
return Resolution(None, RoutingError.PRIVATE_RESTRICTED)
# 99
return Resolution(None, RoutingError.SERVER_UNKNOWN, {"server": override})
# 101
return Resolution(None, RoutingError.NOT_AUTHORIZED, {"server": srv.server_id})
# 110
return Resolution(None, RoutingError.ACTIVE_SERVER_STALE)
# 127
return Resolution(None, RoutingError.NO_SERVER_RESOLVED)
```
成功路径 `Resolution(srv, None)` / `Resolution(ready[0], None)` 不变（error_params 取默认空 dict）。

- [ ] **Step 4: admin_service 透传枚举（不在 app 层渲染）**

`application/admin_service.py:75` 与 `:234`：
```python
# before
params={"reason": resolution.error or ""},
# after
params={"error": resolution.error, "error_params": resolution.error_params},
```

- [ ] **Step 5: presentation 渲染 helper + 4 直接消费点 + _render_result 边界**

`presentation/commands.py`：
- import 增：`from ..application.routing_service import RoutingError`（若 RoutingService 已从此导入，合并）。
- 新增模块级 helper（或 Commands 静态方法）：
```python
def _render_routing_error(err, params) -> str:
    """RoutingError → 本地化串（presentation 边界；err=None → 空串）。逐字复现原 L 输出。"""
    return L(err.value, **(params or {})) if err is not None else ""
```
- `commands.py:136`（_resolve_world 元组返回）：
```python
# before: return None, arg, res.error, ""
# after:  return None, arg, _render_routing_error(res.error, res.error_params), ""
```
- `commands.py:698 / 754 / 767`（内联）：
```python
# before: return L("admin_resolve_failed", reason=resolution.error or "")
# after:  return L("admin_resolve_failed", reason=_render_routing_error(resolution.error, resolution.error_params))
```
- `commands.py:878-879`（_render_result admin_resolve_failed 分支）：
```python
# before: return L("admin_resolve_failed", reason=params.get("reason", ""))
# after:  return L("admin_resolve_failed", reason=_render_routing_error(params.get("error"), params.get("error_params", {})))
```
- **零改动确认**：`commands.py:821-823`（confirm）返回静态 `L("admin_confirm_stale")`，不读 resolution.error，不改。

- [ ] **Step 6: 跑测试**

Run: `python -m pytest tests/unit/routing_service_resolve_test.py tests/unit/routing_world_mode_test.py tests/unit/commands_admin_write_test.py tests/unit/commands_test.py -q`
Expected: PASS。commands_admin_write_test（断言 admin 失败最终渲染串）必须字节存活——若挂，说明 admin_resolve_failed 嵌套未字节保真，核对 _render_routing_error 与原 L(key,**params) 输出。

- [ ] **Step 7: 全量 + 检查**

Run: `python -m pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: 全 PASS

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: routing 返回 RoutingError 枚举，presentation 边界渲染，routing 清零 presentation import"
```

---

## Task 7: application 无 presentation-import 静态守卫（锁死清零）

**Files:**
- Test: `tests/unit/layering_guard_test.py`（新建）

**Interfaces:**
- Consumes: 无（纯静态扫描）

- [ ] **Step 1: 写测试（应立即通过——前 6 任务已清零）**

`tests/unit/layering_guard_test.py`：
```python
import pathlib

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "palworld_terminal" / "application"


def test_application_has_no_presentation_import():
    """application 层绝不 import presentation（依赖倒置守卫，spec §10）。"""
    offenders = []
    for py in APP_DIR.glob("*.py"):
        src = py.read_text(encoding="utf-8")
        if "from ..presentation" in src or "import palworld_terminal.presentation" in src:
            offenders.append(py.name)
    assert offenders == [], f"application 层残留 presentation import：{offenders}"
```

- [ ] **Step 2: 跑测试**

Run: `python -m pytest tests/unit/layering_guard_test.py -q`
Expected: PASS（5 处已在 Task 1-6 清零）。若 FAIL 列出残留者 → 回对应任务补清。

- [ ] **Step 3: 全量终验**

Run: `python -m pytest -q && ruff check palworld_terminal && mypy palworld_terminal`
Expected: 全 PASS。
前端（若受影响，一般不）：`cd frontend && npm run build && npm test`（no-drift）。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: 新增 application 无 presentation-import 分层守卫"
```

---

## Self-Review 备忘（已核对 spec 覆盖）
- §4 组件① → Task 1；§5 组件② → Task 2；§6 组件③（EventView/event_view/render_event/隐私护栏）→ Task 3+4+5；§7 组件④（RoutingError/6 消费点）→ Task 6；§8.2 no-presentation 守卫 → Task 7；§8.2 output_consistency 重写 → Task 5 Step 7（落相 3 语义）；§8.3 隐私/gamedata → Task 3+5；§8.4 测试重写清单 → Task 5+6 分摊。
- 验收 §10 各条：清零守卫（T7）、golden 字节（T5/T6）、config hack 退役（T1）、render_event/event_view 单一源（T3/T4/T5 + output_consistency）、EventView 无内部键（T3 测试）、routing 6 消费点 + 821 零改动（T6）。
