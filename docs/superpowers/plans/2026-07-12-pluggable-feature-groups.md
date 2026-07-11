# 特性分组可插拔架构 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把功能按「特性分组」组织，可经配置页整组开关；默认关闭依赖 `/game-data` 的 guilds_bases 组（代码全保留），并降低接线/命令/配置层耦合。

**Architecture:** 新增 `FeaturesConfig`（配置页 `features` 节）+ `feature_groups.py`（端点→组、active_endpoints）+ `command_registry.py`（命令→组唯一真相源）。容器按启用组**条件构造服务**（禁用即 None，靠既有守卫短路）；Scheduler 只轮询启用组端点；命令 gating 用单一 `@_gated` 装饰器、help 从注册表生成。规格：`docs/superpowers/specs/2026-07-12-pluggable-feature-groups-design.md`（已三视角对抗式复核，遇歧义以规格为准）。

**Tech Stack:** Python 3.11 dataclass(slots)、asyncio、pytest（asyncio auto）

## Global Constraints

- 测试命令用 `.venv/Scripts/python.exe -m pytest`（裸 `python` 不可用）；收尾三绿：`pytest -q` + `ruff check .` + `mypy`
- **commit message 不含任何 AI/Claude 署名、提及或 Co-Authored-By 尾行**（用户硬性要求）
- **events 禁用 = `None` 通路**（`events = EventService(...) if features.events else None`），既有 6 处 `if events is not None` 守卫天然短路——**严禁引入 no-op 对象**（会绕过守卫、扩大 NPE 面）
- **guilds_bases 禁用 = guilds/bases 为 None** + `ingest_game_data` 首行守卫 `if self._guilds is None or self._bases is None: return`（对称于 events）
- **gating 与 help 物理读同一张 `COMMANDS` 表**；gating 用单一 `@_gated(组)` 装饰器（逻辑只写一份），不在每个方法体首行散落 if
- **`AppConfig.features` 必须加在 `skipped_headers` 之后**、`field(default_factory=...)`（多处测试用位置参数构造 AppConfig）
- **Scheduler core 端点不变式**：`{INFO, METRICS, PLAYERS, SETTINGS}` 恒在轮询集合内
- **默认**：report=true、events=true、guilds_bases=false
- 代码全保留：禁用只是不接线，不删任何 game-data/guild/base 代码

## 现有签名速览（实现者据此接线，勿臆造）

- `config.py`：`AppConfig` 末字段现为 `skipped_headers: list[SkippedHeader] = field(default_factory=list)`（:127）；`parse_config` 结尾 `return AppConfig(...)`（:260-307）；`_obj(raw, key)` 取 object 节（缺省 `{}`）
- `container.py` 装配段（`start()` 内约 85-114）：
  ```python
  events = EventService(repo, self._clock)
  players = PlayerService(repo, salt, self._cfg, self._clock)
  guilds = GuildService(repo, salt, self._clock)
  bases = BaseService(repo, self._cfg.bases, self._clock, salt)
  players.events = events
  guilds.events = events
  self._snapshot = SnapshotService(repo, _normalizer_mod, _privacy_mod, meta, salt,
      self._cfg, self._clock, players, guilds, bases, events,
      shared_settings=self._settings_cache, shared_world=self._world_cache)
  ...
  self._scheduler = self._scheduler_factory(
      servers=[s for s in self._cfg.servers if s.ready], polling=self._cfg.polling,
      locks=locks, clock=self._clock, on_response=self._on_response,
      rng_seed=None, fetcher=self._fetch)
  ```
- `scheduler.py`：`Scheduler.__init__(servers, polling, locks, clock, on_response, rng_seed=None, *, fetcher, sleep=asyncio.sleep)`；`start()` 里 `for endpoint in EndpointName`（:67）；`_base_interval` 全枚举字典（:50-57）
- `snapshot_service.py`：`ingest_game_data(self, world, resp)`（:226），首行现为 `if not resp.ok or resp.data is None: return`；`self._guilds`/`self._bases`/`self._events` 为构造入参
- `commands.py`：`Commands.__init__(routing, query, repo, cfg, clock)`（self._cfg）；`help(message_str, is_admin)` → `format_help(arg.name or None, is_admin)`（:155-157）；命令方法 `async def x(self, umo, message_str, is_group) -> str`
- `formatters.py`：`format_help(topic, is_admin)`（:138）用硬编码 `_HELP_GUEST`（:123）+ `_HELP_ADMIN_EXTRA`（:131）
- `locale.py`：`MESSAGES` dict + `L(key, **kwargs)`（现无 `feature_disabled`）
- `tests/integration/conftest.py`：`make_config()`（:22-38）返回配置 dict（现无 features 节），`harness/harness_strict/harness_two` 夹具用之
- `tests/unit/commands_test.py`：多处 `Commands(..., cfg=None, clock=None)`（:65,77,86...），`test_help_role_separation`（:117）调 `cmds.help(...)`

---

### Task 1: FeaturesConfig + 解析 + AppConfig 字段 + schema + 集成夹具全开

**Files:**
- Modify: `palchronicle/config.py`、`_conf_schema.json`、`tests/integration/conftest.py`、`tests/unit/conf_schema_test.py`
- Test: `tests/unit/config_features_test.py`（新建）

**Interfaces:**
- Produces：`FeaturesConfig(report: bool, events: bool, guilds_bases: bool)` + 方法 `enabled(name: str) -> bool`（core 恒 True）；`AppConfig.features: FeaturesConfig`（默认 report/events=True, guilds_bases=False）；`parse_config` 解析 `features` 节

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/config_features_test.py`：

```python
"""features 配置解析：默认值、显式覆盖、enabled() 助手（spec §3）。"""
from palchronicle.config import FeaturesConfig, parse_config


def _raw(features=None):
    cfg = {"servers": [], "routing": {"access_mode": "open", "default_server": ""},
           "group_bindings": [], "polling": {}, "world": {}, "bases": {},
           "privacy": {"mode": "balanced"}, "history": {}}
    if features is not None:
        cfg["features"] = features
    return cfg


def test_features_default_when_absent():
    f = parse_config(_raw(), {}).features
    assert f.report is True and f.events is True and f.guilds_bases is False


def test_features_explicit_override():
    f = parse_config(_raw({"report": False, "events": False, "guilds_bases": True}), {}).features
    assert f.report is False and f.events is False and f.guilds_bases is True


def test_enabled_helper():
    f = FeaturesConfig(report=True, events=False, guilds_bases=False)
    assert f.enabled("core") is True
    assert f.enabled("report") is True
    assert f.enabled("events") is False
    assert f.enabled("guilds_bases") is False
    assert f.enabled("nope") is False
```

在 `tests/unit/conf_schema_test.py` 末尾追加：

```python
def test_features_section():
    s = load_schema()
    assert s["features"]["type"] == "object"
    items = s["features"]["items"]
    assert items["report"]["default"] is True
    assert items["events"]["default"] is True
    assert items["guilds_bases"]["default"] is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/config_features_test.py tests/unit/conf_schema_test.py::test_features_section -q`
Expected: `ImportError: cannot import name 'FeaturesConfig'` / KeyError 'features'

- [ ] **Step 3: 实现**

`palchronicle/config.py`：在 `HistoryConfig` 之后、`AppConfig` 之前插入：

```python
@dataclass(slots=True)
class FeaturesConfig:
    report: bool
    events: bool
    guilds_bases: bool

    def enabled(self, name: str) -> bool:
        return {
            "core": True, "report": self.report,
            "events": self.events, "guilds_bases": self.guilds_bases,
        }.get(name, False)


def _default_features() -> FeaturesConfig:
    return FeaturesConfig(report=True, events=True, guilds_bases=False)
```

`AppConfig` 在 `skipped_headers` 行**之后**追加：

```python
    features: FeaturesConfig = field(default_factory=_default_features)
```

`parse_config` 内（`h = _obj(raw, "history")` 之后）加：

```python
    f = _obj(raw, "features")
    features = FeaturesConfig(
        report=bool(f.get("report", True)),
        events=bool(f.get("events", True)),
        guilds_bases=bool(f.get("guilds_bases", False)),
    )
```

`AppConfig(...)` 构造末尾（`skipped_headers=skipped_headers,` 之后）加：

```python
        features=features,
```

`_conf_schema.json`：在 `history` 节之后（顶层）追加：

```json
  "features": {
    "type": "object",
    "description": "功能分组开关（关闭的组不轮询、不装配、命令回“未开放”；代码保留，改开即恢复）",
    "items": {
      "report": { "type": "bool", "description": "日报/在线统计（/pal today）", "default": true },
      "events": { "type": "bool", "description": "世界事件记录（/pal events；关闭后不生成事件）", "default": true },
      "guilds_bases": { "type": "bool", "description": "公会与据点（依赖服务器开放 /game-data；Palworld 1.0 专用服务器暂不支持，默认关）", "default": false }
    }
  }
```

`tests/integration/conftest.py` 的 `make_config()` 返回 dict 内追加一行（集成测试默认全开以还原旧行为，spec §8）：

```python
        "features": {"report": True, "events": True, "guilds_bases": True},
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/config_features_test.py tests/unit/conf_schema_test.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿（尚无消费者，行为不变；conftest 全开无害）

- [ ] **Step 6: Commit**

```bash
git add palchronicle/config.py _conf_schema.json tests/integration/conftest.py tests/unit/config_features_test.py tests/unit/conf_schema_test.py
git commit -m "feat(config): FeaturesConfig + features 配置节 + 集成夹具默认全开"
```

---

### Task 2: feature_groups.py — 端点→组 / active_endpoints

**Files:**
- Create: `palchronicle/application/feature_groups.py`
- Test: `tests/unit/feature_groups_test.py`

**Interfaces:**
- Consumes: `FeaturesConfig`（Task 1）
- Produces: `ENDPOINT_GROUP: dict[EndpointName, str]`；`active_endpoints(features: FeaturesConfig) -> frozenset[EndpointName]`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/feature_groups_test.py`：

```python
"""端点→组映射与 active_endpoints（spec §4）。"""
from palchronicle.application.feature_groups import active_endpoints
from palchronicle.config import FeaturesConfig
from palchronicle.domain.enums import EndpointName

_CORE = {EndpointName.INFO, EndpointName.METRICS, EndpointName.PLAYERS, EndpointName.SETTINGS}


def test_guilds_bases_off_excludes_game_data():
    eps = active_endpoints(FeaturesConfig(True, True, False))
    assert EndpointName.GAME_DATA not in eps
    assert _CORE <= eps


def test_guilds_bases_on_includes_game_data():
    assert EndpointName.GAME_DATA in active_endpoints(FeaturesConfig(True, True, True))


def test_core_endpoints_always_present_even_all_off():
    assert _CORE <= active_endpoints(FeaturesConfig(False, False, False))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/feature_groups_test.py -q`
Expected: `ModuleNotFoundError: ...feature_groups`

- [ ] **Step 3: 实现**

创建 `palchronicle/application/feature_groups.py`：

```python
"""特性分组：端点→所属组映射与启用端点计算（spec §4）。core 端点恒启用。"""
from __future__ import annotations

from ..config import FeaturesConfig
from ..domain.enums import EndpointName

ENDPOINT_GROUP: dict[EndpointName, str] = {
    EndpointName.INFO: "core",
    EndpointName.METRICS: "core",
    EndpointName.PLAYERS: "core",
    EndpointName.SETTINGS: "core",
    EndpointName.GAME_DATA: "guilds_bases",
}


def active_endpoints(features: FeaturesConfig) -> frozenset[EndpointName]:
    return frozenset(
        ep for ep, group in ENDPOINT_GROUP.items()
        if group == "core" or features.enabled(group)
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/feature_groups_test.py -q`
Expected: 3 passed

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add palchronicle/application/feature_groups.py tests/unit/feature_groups_test.py
git commit -m "feat(features): 端点→组映射与 active_endpoints"
```

---

### Task 3: 命令注册表 + format_help 按启用组过滤 + feature_disabled 文案

**Files:**
- Create: `palchronicle/presentation/command_registry.py`
- Modify: `palchronicle/presentation/formatters.py`（format_help）、`palchronicle/presentation/locale.py`、`palchronicle/presentation/commands.py`（help 调用）、`tests/unit/formatters_test.py`、`tests/unit/commands_test.py`
- Test: 上述 + 新增 help 过滤用例

**Interfaces:**
- Consumes: `FeaturesConfig.enabled`（Task 1）
- Produces: `command_registry.COMMANDS: list[tuple[str,str,str]]`、`COMMAND_GROUP: dict[str,str]`、`HELP_LINE: dict[str,str]`；`format_help(topic, is_admin, features) -> str`（**签名新增 features**）；locale key `feature_disabled`

- [ ] **Step 1: 写失败测试**

`tests/unit/formatters_test.py`：把现有 `test_format_help_role_separation`（:113）替换为下面两个：

```python
def test_format_help_role_separation():
    from palchronicle.config import FeaturesConfig
    feats = FeaturesConfig(report=True, events=True, guilds_bases=True)
    admin = format_help(None, is_admin=True, features=feats)
    assert "use" in admin
    guest = format_help(None, is_admin=False, features=feats)
    assert "use" not in guest and "status" in guest


def test_format_help_filters_disabled_groups():
    from palchronicle.config import FeaturesConfig
    off = format_help(None, is_admin=False, features=FeaturesConfig(True, True, False))
    assert "guilds" not in off and "bases" not in off
    assert "status" in off and "world" in off
    on = format_help(None, is_admin=False, features=FeaturesConfig(True, True, True))
    assert "guilds" in on and "bases" in on
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/formatters_test.py::test_format_help_filters_disabled_groups -q`
Expected: FAIL（format_help 不接受 features / 未过滤）

- [ ] **Step 3: 实现**

创建 `palchronicle/presentation/command_registry.py`：

```python
"""命令注册表：gating 与 help 的唯一真相源（spec §5）。"""
from __future__ import annotations

# (name, 组)——命令 → 所属组
COMMANDS: list[tuple[str, str]] = [
    ("status", "core"), ("online", "core"), ("world", "core"), ("rules", "core"),
    ("guilds", "guilds_bases"), ("guild", "guilds_bases"),
    ("bases", "guilds_bases"), ("base", "guilds_bases"),
    ("events", "events"), ("today", "report"),
    ("servers", "core"), ("help", "core"),
]
COMMAND_GROUP: dict[str, str] = {name: group for name, group in COMMANDS}

# help 展示文案（带参数提示），保持与旧 _HELP_GUEST 一致的措辞
HELP_LINE: dict[str, str] = {
    "status": "/pal status  世界状态", "online": "/pal online  当前在线",
    "world": "/pal world  世界概览", "rules": "/pal rules  世界规则",
    "guilds": "/pal guilds  公会列表", "guild": "/pal guild <名称>  公会详情",
    "bases": "/pal bases  据点列表", "base": "/pal base <名称|#序号>  据点详情",
    "events": "/pal events  世界事件", "today": "/pal today  今日日报",
    "servers": "/pal servers  服务器列表", "help": "/pal help  帮助",
}
```

`palchronicle/presentation/locale.py`：`MESSAGES` dict 内追加：

```python
    "feature_disabled": "该功能未开放：当前配置或服务器不支持。",
```

`palchronicle/presentation/formatters.py`：删除 `_HELP_GUEST` 定义（:123-130），保留 `_HELP_ADMIN_EXTRA`；顶部加 `from .command_registry import COMMANDS, HELP_LINE`；`format_help` 改为：

```python
def format_help(topic: str | None, is_admin: bool, features) -> str:
    lines = ["PalChronicle 命令："]
    for name, group in COMMANDS:
        if group == "core" or features.enabled(group):
            lines.append(HELP_LINE[name])
    lines.append("提示：命令末尾可加 @服务器名 指定服务器。")
    if is_admin:
        lines.append("")
        lines.extend(_HELP_ADMIN_EXTRA)
    return "\n".join(lines)
```

`palchronicle/presentation/commands.py` 的 `help`（:155-157）改为传 features：

```python
    def help(self, message_str, is_admin) -> str:
        arg = parse_arg(message_str, "help")
        return format_help(arg.name or None, is_admin, self._cfg.features)
```

`tests/unit/commands_test.py`：`test_help_role_separation`（:117-120）现用 `cfg=None`——因 help 现读 `self._cfg.features` 会 NPE。改为传一个带 features 的 cfg。在文件顶部加助手：

```python
from palchronicle.config import parse_config

def _cfg_all_on():
    return parse_config({
        "servers": [], "routing": {"access_mode": "open", "default_server": ""},
        "group_bindings": [], "polling": {}, "world": {}, "bases": {},
        "privacy": {"mode": "balanced"}, "history": {},
        "features": {"report": True, "events": True, "guilds_bases": True},
    }, {})
```

并把 `test_help_role_separation` 里的 `Commands(..., None, None)` 改为 `Commands(_FakeRouting(Resolution(_server(), None)), _FakeQuery(), _FakeRepo(), _cfg_all_on(), None)`。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/formatters_test.py tests/unit/commands_test.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add palchronicle/presentation/command_registry.py palchronicle/presentation/formatters.py palchronicle/presentation/locale.py palchronicle/presentation/commands.py tests/unit/formatters_test.py tests/unit/commands_test.py
git commit -m "feat(commands): 命令注册表 + help 按启用组过滤 + feature_disabled 文案"
```

---

### Task 4: @_gated 装饰器 + Commands 命令 gating

**Files:**
- Modify: `palchronicle/presentation/commands.py`
- Test: `tests/unit/commands_gating_test.py`（新建）

**Interfaces:**
- Consumes: `command_registry`（Task 3）、`FeaturesConfig.enabled`（Task 1）、`L("feature_disabled")`（Task 3）
- Produces: 装饰器 `_gated(group)` 套于受控命令；禁用组命令返回 `L("feature_disabled")`，不触达 query/repo

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/commands_gating_test.py`：

```python
"""命令 gating：禁用组命令回 feature_disabled、不触达底层（spec §5/§6）。"""
from palchronicle.config import parse_config
from palchronicle.presentation.commands import Commands
from palchronicle.presentation.locale import L


def _cfg(guilds_bases: bool, events: bool = True, report: bool = True):
    return parse_config({
        "servers": [], "routing": {"access_mode": "open", "default_server": ""},
        "group_bindings": [], "polling": {}, "world": {}, "bases": {},
        "privacy": {"mode": "balanced"}, "history": {},
        "features": {"report": report, "events": events, "guilds_bases": guilds_bases},
    }, {})


class _BoomQuery:
    """任何被调用的 query 方法都抛错——用于证明禁用命令根本没触达 query。"""
    def __getattr__(self, _name):
        async def _boom(*a, **k):
            raise AssertionError("query 不应被触达")
        return _boom


class _Repo:
    async def get_current_world(self, sid):
        raise AssertionError("repo 不应被触达")


async def test_guilds_disabled_returns_feature_disabled():
    cmds = Commands(routing=None, query=_BoomQuery(), repo=_Repo(),
                    cfg=_cfg(guilds_bases=False), clock=None)
    assert await cmds.guilds("u", "", True) == L("feature_disabled")
    assert await cmds.bases("u", "", True) == L("feature_disabled")
    assert await cmds.guild("u", "x", True) == L("feature_disabled")
    assert await cmds.base("u", "x", True) == L("feature_disabled")


async def test_events_and_today_gated():
    cmds = Commands(None, _BoomQuery(), _Repo(),
                    cfg=_cfg(guilds_bases=False, events=False, report=False), clock=None)
    assert await cmds.events("u", "", True) == L("feature_disabled")
    assert await cmds.today("u", "", True) == L("feature_disabled")


async def test_enabled_group_not_gated():
    # guilds_bases 开启 → gate 放行 → 进入路由解析 → 返回路由错误文案（证明未被 gating 拦截）
    from palchronicle.application.routing_service import Resolution

    class _Routing:
        async def resolve(self, umo, override, is_group):
            return Resolution(None, "ROUTING_ERR")

    cmds = Commands(_Routing(), _BoomQuery(), _Repo(), cfg=_cfg(guilds_bases=True), clock=None)
    assert await cmds.guilds("u", "", True) == "ROUTING_ERR"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/commands_gating_test.py -q`
Expected: FAIL（无 gating → guilds 触达 _BoomQuery 抛 AssertionError 而非返回 feature_disabled）

- [ ] **Step 3: 实现**

`palchronicle/presentation/commands.py`：顶部加 `import functools`；类外（`import` 之后、`class Commands` 之前）加装饰器：

```python
def _gated(group: str):
    """命令组 gating：所属组未启用则回 feature_disabled，不触达底层（spec §5）。"""
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(self, *args, **kwargs):
            if not self._cfg.features.enabled(group):
                return L("feature_disabled")
            return await fn(self, *args, **kwargs)
        return wrapper
    return deco
```

给以下方法加装饰器（紧贴 `async def` 上一行）：

```python
    @_gated("guilds_bases")
    async def guilds(self, umo, message_str, is_group) -> str:
        ...

    @_gated("guilds_bases")
    async def guild(self, umo, message_str, is_group) -> str:
        ...

    @_gated("guilds_bases")
    async def bases(self, umo, message_str, is_group) -> str:
        ...

    @_gated("guilds_bases")
    async def base(self, umo, message_str, is_group) -> str:
        ...

    @_gated("events")
    async def events(self, umo, message_str, is_group) -> str:
        ...

    @_gated("report")
    async def today(self, umo, message_str, is_group) -> str:
        ...
```

（只加装饰器行，方法体不动。status/online/world/rules/servers/help/use/unbind **不加**。）

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/commands_gating_test.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿（commands_test 不直测 guilds/bases/events/today，不受影响）

- [ ] **Step 6: Commit**

```bash
git add palchronicle/presentation/commands.py tests/unit/commands_gating_test.py
git commit -m "feat(commands): @_gated 单点装饰器对禁用组命令回 feature_disabled"
```

---

### Task 5: Scheduler 按注入端点集合轮询

**Files:**
- Modify: `palchronicle/infrastructure/scheduler.py`
- Test: `tests/unit/scheduler_basic_test.py`（追加一个用例）

**Interfaces:**
- Produces: `Scheduler.__init__` 新增关键字参数 `endpoints: frozenset[EndpointName] | None = None`（None → 全端点，保持旧行为）；`start()` 只为 `self._endpoints` 建循环

- [ ] **Step 1: 写失败测试**

`tests/unit/scheduler_basic_test.py` 末尾追加：

```python
async def test_scheduler_only_fires_injected_endpoints():
    fetched = []

    async def fetcher(server_id, endpoint):
        fetched.append(endpoint)
        return _ok_resp()

    async def on_response(server_id, endpoint, resp):
        return None

    sched = Scheduler(
        servers=[_server()], polling=_polling(),
        locks=EndpointLocks(max_concurrency=6), clock=FakeClock(start=0),
        on_response=on_response, rng_seed=42, fetcher=fetcher, sleep=GatedSleep(),
        endpoints=frozenset({EndpointName.INFO, EndpointName.METRICS}),
    )
    await sched.start()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await sched.stop()

    assert set(fetched) == {EndpointName.INFO, EndpointName.METRICS}
    assert EndpointName.GAME_DATA not in fetched
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/scheduler_basic_test.py::test_scheduler_only_fires_injected_endpoints -q`
Expected: `TypeError: __init__() got an unexpected keyword argument 'endpoints'`

- [ ] **Step 3: 实现**

`palchronicle/infrastructure/scheduler.py`：`__init__` 签名末尾（`sleep: Sleeper = asyncio.sleep,` 之后）加参数：

```python
        endpoints: frozenset[EndpointName] | None = None,
```

`__init__` 体内（`self._sleep = sleep` 之后）加：

```python
        self._endpoints = endpoints if endpoints is not None else frozenset(EndpointName)
```

`start()` 内循环由 `for endpoint in EndpointName:`（:67）改为：

```python
            for endpoint in self._endpoints:
```

（`_base_interval` 全枚举字典保留不动——按 key 查安全。）

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/scheduler_basic_test.py -q`
Expected: 全部 PASS（既有「全 5 端点」用例因默认 None→全端点仍通过）

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add palchronicle/infrastructure/scheduler.py tests/unit/scheduler_basic_test.py
git commit -m "feat(scheduler): 支持按注入端点集合轮询（默认全端点保持旧行为）"
```

---

### Task 6: Container 条件装配 + ingest_game_data 守卫（接线核心）

**Files:**
- Modify: `palchronicle/container.py`（`start()` 装配段）、`palchronicle/application/snapshot_service.py`（`ingest_game_data` 首行守卫）
- Test: `tests/unit/container_features_test.py`（新建）、`tests/unit/snapshot_game_data_guard_test.py`（新建）

**Interfaces:**
- Consumes: `active_endpoints`（Task 2）、`FeaturesConfig`（Task 1）
- Produces: 禁用组时 `events`/`guilds`/`bases` 为 None；scheduler 收到 `endpoints=active_endpoints(cfg.features)`；`ingest_game_data` 在 guilds/bases 为 None 时首行短路

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/snapshot_game_data_guard_test.py`：

```python
"""guilds_bases 禁用时 guilds/bases 为 None → ingest_game_data 首行短路（spec §4.2）。"""
from palchronicle.application.snapshot_service import SnapshotService
from palchronicle.adapters.palworld_rest import RestResponse
from palchronicle.adapters import normalizer as _norm
from palchronicle.adapters import privacy_filter as _priv
from palchronicle.domain.models import World
from palchronicle.infrastructure.clock import FakeClock


def _snap(guilds, bases, events, shared_world):
    class _Cfg:  # 最小 cfg 占位（ingest_game_data 短路前不触 cfg）
        pass
    return SnapshotService(
        None, _norm, _priv, None, b"salt", _Cfg(), FakeClock(0),
        players=None, guilds=guilds, bases=bases, events=events,
        shared_settings={}, shared_world=shared_world,
    )


async def test_ingest_game_data_noop_when_guilds_none():
    shared = {}
    snap = _snap(guilds=None, bases=None, events=None, shared_world=shared)
    resp = RestResponse(ok=True, status=200, data={"characters": []},
                        duration_ms=1, payload_bytes=2, error=None)
    world = World("alpha:g:0", "alpha", "g", 0, "alpha", "0.3", 900, 1200, 42)
    await snap.ingest_game_data(world, resp)   # 不得抛
    assert shared == {}                        # 短路在 _world_cache 写入之前
```

创建 `tests/unit/container_features_test.py`：

```python
"""容器按 features 条件装配：禁用组不构造服务、scheduler 端点排除 game-data。"""
from pathlib import Path

from palchronicle.config import parse_config
from palchronicle.container import Container
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.clock import FakeClock


def _cfg(guilds_bases: bool, events: bool = True):
    return parse_config({
        "servers": [{"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
                     "username": "admin", "password": "pw"}],
        "routing": {"access_mode": "open", "default_server": ""}, "group_bindings": [],
        "polling": {}, "world": {}, "bases": {"enabled": True},
        "privacy": {"mode": "balanced"}, "history": {},
        "features": {"report": True, "events": events, "guilds_bases": guilds_bases},
    }, {})


class _FakeRest:
    async def close(self): ...


class _FakeSched:
    def __init__(self): self.started = False
    async def start(self): self.started = True
    async def stop(self): ...


async def _build(cfg, tmp_path, captured):
    def sched_factory(**kw):
        captured["endpoints"] = kw.get("endpoints")
        return _FakeSched()
    c = Container(cfg, tmp_path, FakeClock(1000),
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=sched_factory)
    await c.start()
    return c


async def test_guilds_bases_off_excludes_game_data_and_nulls_services(tmp_path: Path):
    captured = {}
    c = await _build(_cfg(guilds_bases=False), tmp_path, captured)
    try:
        assert EndpointName.GAME_DATA not in captured["endpoints"]
        assert {EndpointName.INFO, EndpointName.METRICS,
                EndpointName.PLAYERS, EndpointName.SETTINGS} <= captured["endpoints"]
        assert c._snapshot._guilds is None and c._snapshot._bases is None
    finally:
        await c.stop()


async def test_guilds_bases_on_wires_game_data(tmp_path: Path):
    captured = {}
    c = await _build(_cfg(guilds_bases=True), tmp_path, captured)
    try:
        assert EndpointName.GAME_DATA in captured["endpoints"]
        assert c._snapshot._guilds is not None and c._snapshot._bases is not None
    finally:
        await c.stop()


async def test_events_off_nulls_event_service(tmp_path: Path):
    c = await _build(_cfg(guilds_bases=False, events=False), tmp_path, {})
    try:
        assert c._snapshot._events is None
    finally:
        await c.stop()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/snapshot_game_data_guard_test.py tests/unit/container_features_test.py -q`
Expected: FAIL（ingest_game_data 无守卫→写了 shared_world 或抛；container 未条件装配、未传 endpoints）

- [ ] **Step 3: 实现**

`palchronicle/application/snapshot_service.py` 的 `ingest_game_data`（:226-228）首行加守卫：

```python
    async def ingest_game_data(self, world: World, resp: RestResponse) -> None:
        if self._guilds is None or self._bases is None:
            return                       # guilds_bases 组禁用：整体短路（含 _world_cache 写入）
        if not resp.ok or resp.data is None:
            return
        ...
```

`palchronicle/container.py`：顶部加 `from .application.feature_groups import active_endpoints`。装配段（`events = EventService(...)` 起）改为条件构造：

```python
        events = EventService(repo, self._clock) if self._cfg.features.events else None
        players = PlayerService(repo, salt, self._cfg, self._clock)
        guilds = GuildService(repo, salt, self._clock) if self._cfg.features.guilds_bases else None
        bases = (BaseService(repo, self._cfg.bases, self._clock, salt)
                 if self._cfg.features.guilds_bases else None)
        players.events = events
        if guilds is not None:
            guilds.events = events
        self._snapshot = SnapshotService(
            repo, _normalizer_mod, _privacy_mod, meta, salt, self._cfg, self._clock,
            players, guilds, bases, events,
            shared_settings=self._settings_cache, shared_world=self._world_cache,
        )
```

scheduler 构造（`self._scheduler = self._scheduler_factory(...)`）加 `endpoints=`：

```python
        self._scheduler = self._scheduler_factory(
            servers=[s for s in self._cfg.servers if s.ready],
            polling=self._cfg.polling, locks=locks, clock=self._clock,
            on_response=self._on_response, rng_seed=None, fetcher=self._fetch,
            endpoints=active_endpoints(self._cfg.features),
        )
```

（`_on_response` 的 GAME_DATA 分支**无需改**：guilds_bases 关时 game-data 不被轮询，且 `ingest_game_data` 已自守卫，双保险。）

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/snapshot_game_data_guard_test.py tests/unit/container_features_test.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿（集成测试经 conftest 全开；单元 container_test/其它默认 features 不测 game-data，不受影响）

- [ ] **Step 6: Commit**

```bash
git add palchronicle/container.py palchronicle/application/snapshot_service.py tests/unit/snapshot_game_data_guard_test.py tests/unit/container_features_test.py
git commit -m "feat(container): 按 features 条件装配服务与端点；ingest_game_data 首行守卫"
```

---

### Task 7: OFF 语义端到端 + 分层 + 收敛回归

**Files:**
- Test: `tests/integration/feature_groups_off_test.py`（新建）

**Interfaces:**
- Consumes: 前序全部（Container 条件装配、gating、active_endpoints）

- [ ] **Step 1: 写失败测试**

创建 `tests/integration/feature_groups_off_test.py`：

```python
"""OFF 语义端到端：命令 gating、M1 分层、核心收敛不依赖 game-data/events（spec §6/§9）。"""
from pathlib import Path

from palchronicle.config import parse_config
from palchronicle.container import Container
from palchronicle.domain.enums import EndpointName
from palchronicle.infrastructure.clock import FakeClock
from palchronicle.presentation.locale import L


def _cfg(guilds_bases=False, events=True, bases_enabled=True):
    return parse_config({
        "servers": [{"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
                     "username": "admin", "password": "pw"}],
        "routing": {"access_mode": "open", "default_server": ""}, "group_bindings": [],
        "polling": {}, "world": {}, "bases": {"enabled": bases_enabled},
        "privacy": {"mode": "balanced"}, "history": {},
        "features": {"report": True, "events": events, "guilds_bases": guilds_bases},
    }, {})


class _FakeRest:
    async def close(self): ...


class _FakeSched:
    async def start(self): ...
    async def stop(self): ...


async def _container(cfg, tmp_path):
    c = Container(cfg, tmp_path, FakeClock(1000),
                  rest_factory=lambda s, clk: _FakeRest(),
                  scheduler_factory=lambda **k: _FakeSched())
    await c.start()
    return c


async def test_guilds_command_disabled_end_to_end(tmp_path: Path):
    c = await _container(_cfg(guilds_bases=False), tmp_path)
    try:
        out = await c.commands.guilds("umo", "@alpha", True)
        assert out == L("feature_disabled")
    finally:
        await c.stop()


async def test_m1_layering_master_switch_beats_bases_enabled(tmp_path: Path):
    # features.guilds_bases 关 → 无论 bases.enabled 真假，BaseService 不被构造
    c = await _container(_cfg(guilds_bases=False, bases_enabled=True), tmp_path)
    try:
        assert c._snapshot._bases is None
    finally:
        await c.stop()


async def test_help_omits_disabled_groups(tmp_path: Path):
    c = await _container(_cfg(guilds_bases=False, events=False), tmp_path)
    try:
        text = c.commands.help("/pal help", is_admin=False)
        assert "guilds" not in text and "events" not in text
        assert "status" in text and "world" in text
    finally:
        await c.stop()
```

- [ ] **Step 2: 跑测试确认失败或通过**

Run: `.venv/Scripts/python.exe -m pytest tests/integration/feature_groups_off_test.py -q`
Expected: 全部 PASS（前序任务已实现全部行为——本任务是端到端锁定；若某条失败即暴露前序缺口）

- [ ] **Step 3: 补齐（若有失败）**

若某断言失败，回到对应前序任务修正（如 help 过滤、gating、条件装配）。全绿即可，无需新增实现代码。

- [ ] **Step 4: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿（含既有 523 测试；集成经 conftest 全开还原旧行为）

- [ ] **Step 5: Commit**

```bash
git add tests/integration/feature_groups_off_test.py
git commit -m "test(features): OFF 语义端到端 + M1 分层 + help 过滤锁定"
```

---

### Task 8: README + schema 描述同步

**Files:**
- Modify: `README.md`、`_conf_schema.json`（game_data_seconds / bases 描述追加失效说明）
- Test: `tests/unit/readme_test.py`

**Interfaces:**
- Consumes: 无（纯文档/描述）

- [ ] **Step 1: 写失败测试**

`tests/unit/readme_test.py` 末尾追加：

```python
def test_readme_documents_feature_groups():
    for phrase in ("功能分组", "features", "guilds_bases", "默认关", "game-data"):
        assert phrase in README, f"README 特性分组文档缺少: {phrase}"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py::test_readme_documents_feature_groups -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`README.md` 的 `### 插件页面` 小节之后追加：

```markdown
### features（功能分组开关）

功能按组可插拔，在插件配置页勾选。关闭的组不轮询其端点、不装配其服务、命令回「未开放」；代码保留，改开即恢复。

| 组 | 默认 | 命令 | 说明 |
|------|------|------|------|
| `report` | 开 | `/pal today` | 日报/在线统计 |
| `events` | 开 | `/pal events` | 世界事件记录（关闭后不生成事件） |
| `guilds_bases` | **关** | `/pal guilds` `/pal bases` 等 | 公会与据点，依赖服务器开放 `/game-data` |

**关于 `guilds_bases` 默认关闭**：Palworld 1.0 的专用服务器虽提供 `/v1/api/game-data` 端点，但未开放启用 `PalGameDataBridge` 的任何 INI 字段或启动参数（上游限制），该端点无真实数据。故公会/据点/PalBox 功能默认关闭。待 Palworld 开放后，在配置页把 `features.guilds_bases` 设为开即整组恢复。`bases.*` 与 `game_data_seconds` 仅在该组开启时生效。
```

`_conf_schema.json`：`game_data_seconds` 的 `description` 末尾追加「（仅在 features.guilds_bases 开启时生效）」；`bases` 节 `description` 同样追加该提示。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 全量验证**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m mypy`
Expected: 全绿

- [ ] **Step 6: Commit**

```bash
git add README.md _conf_schema.json tests/unit/readme_test.py
git commit -m "docs(readme): 特性分组开关说明 + schema 描述标注 guilds_bases 依赖"
```
