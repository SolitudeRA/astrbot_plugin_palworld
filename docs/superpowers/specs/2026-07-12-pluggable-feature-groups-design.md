# 特性分组可插拔架构 — 设计规格

日期：2026-07-12
状态：已对抗式复核（三视角）并修订
关联：`docs/superpowers/specs/2026-07-10-palchronicle-v0.1.md`（主规格）

## 0. 背景与目标

**触发**：Palworld 1.0 上游限制——Pocketpair 提供了 `/v1/api/game-data` 端点，
但未对专用服务器开放任何启用 `PalGameDataBridge` 的 INI 字段或启动参数（实测
该端点稳定返回 404）。依赖 game-data 的功能（公会、据点、PalBox、世界 Actor
细分）在当前 Palworld 上**永远拿不到真实数据**，服务端无从修复。

**现状问题**：这些功能的接线（端点轮询、服务装配、命令注册、配置节）硬编码
耦合在 `container.py` / `scheduler.py` / `commands.py` 里，无法整组开关。

**目标**：
1. 引入「特性分组（feature group）」概念，功能按组组织，可经**配置页**整组开关。
2. 现在默认**关闭 `guilds_bases` 组**（代码与测试**全部保留**，以后 Palworld 开放
   game-data，用户改配置即整组恢复）。
3. **降低耦合**：把「端点→组」「命令→组」两张映射集中声明，命令 gating 与 help
   **物理读同一张表**，消除散落判定。

> **诚实边界（复核 I2）**：本设计**不**承诺「服务→组集中声明」。`SnapshotService`
> 是跨组单例（同时持 players/guilds/bases/events 引用），服务的**构造**受组布尔
> 控制（`x = X(...) if feat.x else None`），但装配顺序仍在 `container.start()` 内
> 表达。`FeatureGroup` 抽象只承载它真能集中的**端点集合**与**命令集合**。

**非目标**：不删除任何 game-data/公会/据点/PalBox 的领域模型、服务、normalizer、
query、formatter 或测试；不改动 game-data 之外功能的运行时数据级降级（已优雅）；
不做无关重构。

## 1. 关键实证（复核已逐行核对代码）

- `status`：metrics（fps/在线/**basecampnum**）+ info + settings。**据点数来自
  `metric.basecamp_count`（`query_service.py:96`），非 game-data**，OFF 下正常。
- `online`：players/会话（repo）。
- `world_summary`（`/pal world`）：**混合**——`_world_cache`（game-data）出帕鲁细分，
  `latest_metric` 出天数/在线/FPS。game-data 缺失时细分自动 0，天数/在线/FPS 回退
  metric（`query_service.py:288-322`，已优雅；注意 `online` 仅在 metric 缺失时才归 0）。
- `rules`：settings。`events`：读 `repo.list_events`（历史仍可读，只是不产据点事件）。
- `guilds`/`guild`/`bases`/`base`：**纯 game-data**，缺失即空。
- `today`：report（会话聚合 + 事件），读时计算。

**结论**：core 四路径（status/online/rules/today）不触碰 game-data / `_world_cache` /
Guild/BaseService，guilds_bases OFF 不崩（复核三源反向确认）。耦合痛点在**接线/
命令/配置层**。

> **同名异源（复核 M3）**：`/pal status` 的「据点数」来自 metrics.basecampnum（OFF
> 下正常），`/pal world` 的「工作帕鲁 BaseCampPal」来自 game-data（OFF 下显 0）。
> 二者中文都含「据点/工作帕鲁」，OFF 下一正常一显 0，属预期，非 bug。

## 2. 特性分组

| 组 | 独占命令 | 端点 | 受控服务/接线 | 配置节 | 默认 |
|---|---|---|---|---|---|
| **core** | status/online/world/rules + servers/help/use/unbind | info/metrics/players/settings | 核心采集/查询/路由 | — | 常开、**不可关** |
| **report** | today | （复用 players，无独占端点） | ReportService（读时聚合，采集不变） | — | 开 |
| **events** | events | （复用 players/game-data，无独占端点） | EventService（事件生成，禁用即 None） | — | 开 |
| **guilds_bases** | guilds/guild/bases/base | **game-data** | GuildService/BaseService/ingest_game_data | bases | **关** |

说明：
- 只有 **guilds_bases 独占端点**（game-data）。report/events 无独占端点，它们的
  「可插拔」体现在**命令 gating**（report/events）与**采集副作用开关**（events 关→
  不生成事件）。三者都是用户可见的 `features` 开关（满足「按分组可插拔」）。
- `/pal world` 帕鲁细分、`/pal events` 据点事件是 guilds_bases 的「附加贡献」，组关
  时自动缺席（已优雅），命令留在各自组，不特判。

## 3. 开关机制（配置页）

`_conf_schema.json` 新增顶层 `features` object 节：

```json
"features": {
  "type": "object",
  "description": "功能分组开关（关闭的组不轮询、不装配、命令回“未开放”；代码保留，改开即恢复）",
  "items": {
    "report":       { "type": "bool", "description": "日报/在线统计（/pal today）", "default": true },
    "events":       { "type": "bool", "description": "世界事件记录（/pal events；关闭后不生成事件）", "default": true },
    "guilds_bases": { "type": "bool", "description": "公会与据点（依赖服务器开放 /game-data；Palworld 1.0 专用服务器暂不支持，默认关）", "default": false }
  }
}
```

`config.py`：

```python
@dataclass(slots=True)
class FeaturesConfig:
    report: bool
    events: bool
    guilds_bases: bool
    def enabled(self, name: str) -> bool:   # core 恒 True
        return {"report": self.report, "events": self.events,
                "guilds_bases": self.guilds_bases, "core": True}.get(name, False)
```

**字段顺序（复核 I3）**：`AppConfig` 新增 `features: FeaturesConfig`，**必须加在现有
末字段 `skipped_headers` 之后**，且用 `field(default_factory=...)`——因为多处测试用
**位置参数**构造 `AppConfig`（`phase3_smoke_test.py:36`、`event_pipeline_test.py:27`、
`pipeline_test.py:59` 等），加在 `skipped_headers` 之前会整体错位。`parse_config`
解析 `features` 节，缺省按上表默认值。

**与既有 `bases.enabled` 的分层（复核 M1）**：仓库已有 `bases.enabled`（组内算法开关，
`base_service.py:43` 首行 `if not self._cfg.enabled: return []`）。分层定义：
- `features.guilds_bases` 是**总开关**——OFF 时无论 `bases.enabled` 真假，公会/据点整组
  不接线（服务为 None、不轮询、命令 gating）。
- `bases.enabled` 降级为**组内细粒度开关**——仅在 `guilds_bases=true` 时才有意义
  （控制据点推导算法是否运行）。
- `_conf_schema.json` 的 `game_data_seconds` 与 `bases.*` 描述追加「仅在
  features.guilds_bases 开启时生效」。

## 4. 分组声明与装配（解耦核心）

新增 `palchronicle/application/feature_groups.py`（或 container 内声明），承载两张
可集中的映射：

```python
class EndpointGroups:
    # 端点 → 所属组；core 端点恒启用
    ENDPOINT_GROUP: dict[EndpointName, str] = {
        EndpointName.INFO: "core", EndpointName.METRICS: "core",
        EndpointName.PLAYERS: "core", EndpointName.SETTINGS: "core",
        EndpointName.GAME_DATA: "guilds_bases",
    }

def active_endpoints(feat: FeaturesConfig) -> frozenset[EndpointName]:
    return frozenset(ep for ep, g in ENDPOINT_GROUP.items()
                     if g == "core" or feat.enabled(g))
```

`container.start()` 依启用组装配（复核 I2：条件构造，不假装「集中声明服务」）：

```python
# 服务构造受组布尔控制（禁用即 None）
events  = EventService(repo, clock) if cfg.features.events else None
guilds  = GuildService(repo, salt, clock) if cfg.features.guilds_bases else None
bases   = BaseService(repo, cfg.bases, clock, salt) if cfg.features.guilds_bases else None
players = PlayerService(repo, salt, cfg, clock)
players.events = events            # None → 既有守卫天然短路
if guilds is not None:
    guilds.events = events
snapshot = SnapshotService(repo, ..., players, guilds, bases, events, ...)
# Scheduler 只收到启用组端点并集
scheduler = self._scheduler_factory(servers=..., endpoints=active_endpoints(cfg.features), ...)
```

### 4.1 events 禁用 = None 通路（复核 C1，三源一致否决 no-op 对象）

events 关时 `events = None`。既有代码在 6 处以 `if events is not None` 守卫事件发射
（`snapshot_service.py:140,245`、`player_service.py:86,98`、`guild_service.py:60`），
`None` 令全部守卫**天然短路**，不生成/不落库事件，零新类、零 NPE 面。
**不引入 no-op 对象**（非 None 对象会绕过守卫、要求覆盖全部 6 个 async 方法、且
`world_day`/`online_record` 在 core 端点 `ingest_metrics`（恒采集）里调用，一旦
no-op 有 bug 直接打断 core 采集链）。

### 4.2 guilds_bases 禁用 = None + 对称守卫（复核 C2）

guilds_bases 关时 `guilds = bases = None`。为与 events 守卫对称、并防集成测试直调，
在 `snapshot_service.ingest_game_data` **首行**加结构性短路：

```python
async def ingest_game_data(self, world, resp) -> None:
    if self._guilds is None or self._bases is None:
        return                      # guilds_bases 组禁用：整体短路（含 _world_cache 写入）
    if not resp.ok or resp.data is None:
        return
    ...
```

短路置于 `_world_cache` 写入**之前**：组禁用时 `_world_cache` 保持空 → `/pal world`
帕鲁细分显 0（符合预期）。双保险：guilds_bases 关时 game-data 不被轮询
（§4 endpoints）+ `container._on_response` 的 GAME_DATA 分支短路（`if snapshot 无 guilds`）
+ 本首行守卫。

### 4.3 Scheduler 端点集合化（复核 I4）

`Scheduler.__init__` 新增 `endpoints: frozenset[EndpointName]`；`start()` 由
`for endpoint in EndpointName` 改为 `for endpoint in self._endpoints`。
- `_base_interval` 保留全枚举字典（按 key 查安全，不因端点集合收窄而 KeyError）。
- 背压 `_effective`/`_low_streak` 惰性 `setdefault`，自动只为实际端点建键。
- `stop()`/info 立即拉/背压不受影响（复核反向确认）。
- **不变式**：core 端点 `{INFO, METRICS, PLAYERS, SETTINGS}` 恒在集合内（换世界/
  重启收敛全程只依赖 INFO/PLAYERS，复核已核对不涉 game-data/events）——由测试钉死。

## 5. 命令 gating + help（单一映射，复核 C3+C4）

**废弃 `_HELP_GUEST` 硬编码**，改为单张命令注册表，gating 与 help 物理读同一表：

```python
# presentation/commands.py（或 command_registry.py）
_COMMANDS: list[tuple[str, str, str]] = [   # (name, 简述, 组)
    ("status", "服务器状态", "core"), ("online", "在线名单", "core"),
    ("world", "世界概览", "core"),   ("rules", "世界规则", "core"),
    ("today", "今日日报", "report"), ("events", "世界事件", "events"),
    ("guilds", "公会列表", "guilds_bases"), ("guild", "公会详情", "guilds_bases"),
    ("bases", "据点列表", "guilds_bases"), ("base", "据点详情", "guilds_bases"),
    ("servers", "服务器列表", "core"), ("help", "帮助", "core"),
    ("use", "授权本群", "core"), ("unbind", "撤销授权", "core"),
]
_COMMAND_GROUP = {name: grp for name, _desc, grp in _COMMANDS}
```

- **gating（单点逻辑）**：`Commands` 持有 `FeaturesConfig`；一个 `@gated` 装饰器（逻辑
  只写一份）套在受控命令方法上——`@gated("guilds_bases")` 于 guilds/guild/bases/base、
  `@gated("events")` 于 events、`@gated("report")` 于 today。装饰器判 `self._features
  .enabled(group)`，False → 返回 `L("feature_disabled")`，方法体不动。core 命令不套。
- **help**：`format_help(topic, is_admin, features)`（新增 `features` 入参）从 `_COMMANDS`
  生成，过滤 `组=="core" or features.enabled(组)`。gating 与 help 读同一表，杜绝漂移。
- 新增 locale key `feature_disabled`（如「该功能未开放：当前配置或服务器不支持」）
  与 `L("feature_disabled")`（`locale.py` 现无此键）。

## 6. 各组禁用语义（精确）

- **guilds_bases OFF（默认）**：`guilds=bases=None`；game-data 不在 active_endpoints →
  不轮询；`ingest_game_data` 首行短路；guilds/guild/bases/base 命令回 `feature_disabled`
  且不进 help；`/pal world` 帕鲁细分显 0、`/pal events` 无据点事件（已优雅）；bases
  配置节保留但描述标注失效（静态 schema 无法动态隐藏，仅描述提示）。
- **events OFF**：`events=None` → 6 处守卫短路、不生成/不落库事件；events 命令回
  `feature_disabled` 且不进 help；`/pal today` 事件相关部分自然空。
- **report OFF**：today 命令回 `feature_disabled` 且不进 help（报表读时聚合，采集不变）。
- **core**：恒启用，无开关、无 gating。

## 7. 保留代码（可复原性）

game-data/guild/base/PalBox 的领域模型、服务、normalizer、query、formatter 及其
单元/集成测试全部保留。禁用 = 不接线；`features.guilds_bases=true`（及 events）即
整组恢复原行为。本规格不删除任何现有功能代码。

## 8. 兼容与迁移（复核 I1/I3）

- **字段顺序**：`AppConfig.features` 加在 `skipped_headers` 之后，`field(default_factory
  =lambda: FeaturesConfig(True, True, False))`；`FeaturesConfig` 亦须可默认构造。
- **集成测试夹具**：`tests/integration/conftest.py` 的 `make_config()`（约 :22-38）
  新增 `"features": {"report": true, "events": true, "guilds_bases": true}`——集成测试
  **默认全开以还原旧行为**，个别专测 OFF 语义的用例再局部覆盖。
- **受影响测试精确清单**（默认 OFF 会断言失败，需经上面夹具全开）：
  - 依赖 guilds_bases：`privacy_test.py`（strict 无 base/position_cell NULL/降级不泄漏）、
    `pipeline_series_test.py:129-176`（palbox jitter / new_base / base_vanished）、
    `cache_wiring_test.py:81-94`（world_summary 读 shared_world 缓存）。
  - 依赖 events：`pipeline_series_test.py`（level_up / world_day_milestone / online_record /
    two_servers 断 a_events>=2）。
  - 不受影响：`base_confirmation_test.py`（直建 BaseService，不经 Container）。
- **单元测试位置参数构造点**：`phase3_smoke_test.py:36`、`event_pipeline_test.py:27`、
  `pipeline_test.py:59` 等以位置参数构造 AppConfig——features 置末位 + 默认值保证兼容。
- **默认行为变化**：全新安装默认 `guilds_bases=false` → 公会/据点命令默认回「未开放」。
  README 说明如何开启。

## 9. 测试计划

| 层 | 用例 |
|---|---|
| FeaturesConfig | 缺 features 节→默认(report/events on, guilds_bases off)；显式覆盖；`enabled()` |
| schema（M4） | `s["features"]["type"]=="object"`；三子项 default（report/events=true、guilds_bases=false） |
| active_endpoints | guilds_bases 关→并集不含 GAME_DATA、含 {INFO,METRICS,PLAYERS,SETTINGS}；开→含 GAME_DATA |
| Scheduler（I4） | 注入端点集合→只为该集合建循环；`scheduler_basic_test` 断言由「全 5 端点」改为「==传入集合」；core 端点不变式测试 |
| 装配-events | events 关→`events is None`、ingestion 后 repo 无事件、core 采集不抛；开→有事件 |
| 装配-guilds_bases | 关→guilds/bases 为 None、fetcher 从不被请求 GAME_DATA、`ingest_game_data` 直调即 no-op 不抛；开→正常 |
| 分层（M1） | features.guilds_bases 关→无论 bases.enabled 真假，BaseService 不被装配/调用 |
| 命令 gating | `@gated` 禁用组命令回 `feature_disabled`、不在 help；启用组正常；core 恒可用 |
| help 生成 | format_help 依 features 过滤：guilds_bases 关→help 不含 guilds/bases/guild/base；开→含 |
| 混合降级 | guilds_bases 关下 /pal world 显核心+帕鲁 0、/pal status 据点数仍来自 metrics |
| 收敛回归（I4/M5） | guilds_bases=off 且 events=off 下：换世界 + `_apply_and_restart` 重启后 uncertain 收敛仍闭合（core INFO/PLAYERS 恒轮询） |
| README | guilds_bases 默认关、开启方法 关键词断言 |
| 全量回归 | 夹具全开后既有 523 测试全绿 |

## 10. 风险（复核后更新）

- **回归面**：改 container 装配 + Scheduler 端点选择 + Commands gating/help + config +
  schema。523 测试护航，逐步 TDD。
- **C1 已消解**：events 用 None 通路（非 no-op 对象），既有守卫天然短路，无 null-sink
  NPE 风险，§复核 M5 的「重启+events on→off+null sink」交叉风险随之消失。
- **集成测试迁移量**：一次性在 conftest `make_config` 全开可覆盖大部分，专测 OFF 的
  少数用例局部覆盖。
- **命令 gating 位置**：在 Commands 层（`@gated` 运行时），非 main.py 静态装饰器。

## 11. 复核记录

2026-07-12 三视角对抗式复核（依赖正确性/耦合、架构解耦、调度器与回归），发现
4 Critical + 4 Important + 5 Minor，多为多源独立命中。本版修订：

- C1：events 禁用由「注入 no-op 对象」改为 **None 通路**（既有 6 处 `is not None` 守卫
  天然短路，消 NPE 面与 §10 风险）。
- C2：guilds_bases 禁用 → guilds/bases 为 None + `ingest_game_data` 首行对称守卫 +
  不轮询 + `_on_response` 短路 三重保险；明确短路置 `_world_cache` 写入之前。
- C3+C4：废弃 `_HELP_GUEST` 硬编码，改单张 `_COMMANDS` 表；gating 用 `@gated` 单点
  装饰器、help 从表生成，物理共享；新增 `feature_disabled` locale key。
- I1：conftest `make_config` 默认全开 + 受影响测试精确清单 + 短路位置指定。
- I2：收窄 §0 目标 3（不承诺「服务集中声明」，改「服务构造受组布尔控制」）。
- I3：`AppConfig.features` 钉在 `skipped_headers` 之后 + default_factory。
- I4：Scheduler 端点集合注入 + core 端点不变式 + 收敛回归测试。
- M1：`features.guilds_bases`（总开关）与 `bases.enabled`（组内开关）分层。
- M3/M4：status vs world basecamp 同名异源文档注记；features schema 测试。
- M2：report/events 保留为用户开关（满足「按分组可插拔」），但规格诚实说明只有
  guilds_bases 独占端点、report/events 是命令/采集 gating（非过度抽象）。
