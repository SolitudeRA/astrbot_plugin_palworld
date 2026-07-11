# 特性分组可插拔架构 — 设计规格

日期：2026-07-12
状态：待对抗式复核
关联：`docs/superpowers/specs/2026-07-10-palchronicle-v0.1.md`（主规格）

## 0. 背景与目标

**触发**：Palworld 1.0 上游限制——Pocketpair 提供了 `/v1/api/game-data` 端点，
但未对专用服务器开放任何启用 `PalGameDataBridge` 的 INI 字段或启动参数（实测
该端点稳定返回 404）。因此依赖 game-data 的功能（公会、据点、PalBox、世界
Actor 细分）在当前 Palworld 上**永远拿不到真实数据**，服务端也无从修复。

**现状问题**：这些功能的接线（端点轮询、服务装配、命令注册、配置节）硬编码
耦合在 `container.py` / `scheduler.py` / `commands.py` 里，无法整组开关。

**目标**：
1. 引入「特性分组（feature group）」抽象，把功能按组**声明式**组织，可经**配置页**
   整组开关。
2. 现在默认**关闭 `guilds_bases` 组**（代码与测试**全部保留**，以后 Palworld
   开放 game-data，用户改配置即整组恢复）。
3. 顺带**降低耦合**：把「某组拥有哪些端点/命令/服务/配置」集中声明，消除散落
   各处的隐式依赖，为其他组的可插拔铺路。

**非目标**：
- 不删除任何 game-data / 公会 / 据点 / PalBox 的领域模型、服务、normalizer、
  query、formatter 或测试——禁用只是「不接线」。
- 不改动 game-data 之外功能的**运行时数据级降级**（现已优雅，见 §4）。
- 不做与本目标无关的重构。

## 1. 关键实证（已核对代码）

各命令/DTO 的真实数据依赖（决定分组切法）：

- `status`：metrics（fps/在线/basecampnum）+ info + settings。**据点数来自
  metrics.basecampnum，非 game-data**（实测 status 正常显示据点数）。
- `online`：players/会话。
- `world_summary`（`/pal world`）：**混合**——`_world_cache`（game-data）出帕鲁
  细分，`latest_metric` 出天数/在线/FPS。game-data 缺失时细分自动为 0，天数/
  在线/FPS 照常（`query_service.py:288-322` 已优雅回退）。
- `rules`：settings。
- `events`（`/pal events`）：读 `repo.list_events`。据点类事件（NEW_BASE 等）由
  game-data ingestion 产生，玩家/世界类事件由 players/metrics 产生。game-data
  缺失时只是不产生据点事件，命令照常（已优雅）。
- `guilds` / `guild` / `bases` / `base`：**纯 game-data**，缺失即空。
- `today`：report（会话聚合 + 事件），读时计算。

**结论**：数据级降级已优雅，耦合痛点在**接线/命令/配置层**——game-data 端点仍被
轮询、纯 game-data 命令仍挂着、bases 配置仍显示、Guild/BaseService 仍被装配。

## 2. 特性分组

| 组 | 独占命令 | 端点 | 服务/接线 | 配置节 | 默认 |
|---|---|---|---|---|---|
| **core** | status/online/world/rules + servers/help/use/unbind | info/metrics/players/settings | 核心采集/查询/路由 | — | 常开、**不可关** |
| **report** | today | （复用 players） | ReportService | — | 开 |
| **events** | events | （复用 players/game-data） | EventService（事件生成+读取） | — | 开 |
| **guilds_bases** | guilds/guild/bases/base | **game-data** | GuildService / BaseService / ingest_game_data | bases | **关** |

说明：
- `/pal world` 的帕鲁细分、`/pal events` 的据点事件是 `guilds_bases` 的「附加
  贡献」——组关掉时它们自动缺席（已优雅），**命令本身留在 core，不特判**。
- `servers` / `help` / `use` / `unbind` 是路由/元命令，恒属 core。

## 3. 开关机制（配置页）

`_conf_schema.json` 新增顶层 `features` object 节，用户在插件配置页勾选：

```json
"features": {
  "type": "object",
  "description": "功能分组开关（关闭的组不轮询、不装配、命令不可用；代码保留，改开即恢复）",
  "items": {
    "report":       { "type": "bool", "description": "日报/在线统计（/pal today）", "default": true },
    "events":       { "type": "bool", "description": "世界事件（/pal events）", "default": true },
    "guilds_bases": { "type": "bool", "description": "公会与据点（依赖服务器开放 /game-data；Palworld 1.0 专用服务器暂不支持，默认关）", "default": false }
  }
}
```

`config.py` 新增：

```python
@dataclass(slots=True)
class FeaturesConfig:
    report: bool
    events: bool
    guilds_bases: bool
    # core 无字段——恒启用
```

`AppConfig` 增字段 `features: FeaturesConfig`（置于末位、`field(default_factory=...)`
以兼容既有构造点；见 §8）。`parse_config` 解析 `features` 节，缺省按上表默认值。

## 4. 分组声明与装配（解耦核心）

引入集中的特性组声明（新文件 `palchronicle/application/feature_groups.py` 或
container 内的声明表），每组声明其拥有的资源与启用判定：

```python
@dataclass(frozen=True)
class FeatureGroup:
    name: str
    enabled: bool
    endpoints: frozenset[EndpointName]   # 该组需要轮询的端点
    commands: frozenset[str]             # 该组独占的 /pal 子命令名
```

`container.start()` 依启用组装配（gating 集中于此，消除散落 if）：

1. **轮询（Scheduler）**：只把「启用组端点的并集」交给 Scheduler。
   core 端点恒含；`guilds_bases` 关 → `game-data` 不在列 → 不轮询。
   （Scheduler 现在按 `EndpointName` 全枚举建循环——改为按传入的端点集合建。）
2. **采集接线**：
   - `guilds_bases` 关 → 不构造 GuildService/BaseService；`_on_response` 的
     `GAME_DATA` 分支短路（且因不轮询本就不会触发）。
   - `events` 关 → 向 players/guilds ingestion 注入 **null 事件 sink**（一个
     no-op EventService），不生成/不落库事件。
   - `report` 关 → 不影响采集（report 读时聚合），仅命令 gating。
3. **命令**：见 §5（gating 在 Commands 层，非取消注册）。

## 5. 命令 gating（务实：不动 main.py 装饰器）

`main.py` 的 14 个 `@pal.command` 是**类定义期静态注册**，无法按运行时配置取消。
因此命令 gating 落在 **Commands 层**：

- `Commands` 持有启用组信息（container 传入）。
- 每个命令方法体首行判定其所属组是否启用；未启用 → 返回统一文案
  `L("feature_disabled")`（如「该功能未开放：当前配置或服务器不支持」）。
- `format_help` 只列**启用组**的命令；`servers` 列表等 core 命令恒列。
- core 命令（status/online/world/rules/servers/help/use/unbind）无 gating。

命令→组映射（用于 gating 与 help 生成）集中在一处常量，避免散落。

## 6. 各组禁用语义（精确）

- **guilds_bases OFF（默认）**：不轮询 game-data；不装配 Guild/BaseService；
  `_on_response` GAME_DATA 短路；guilds/guild/bases/base 命令回「未开放」且不进
  help；`/pal world` 帕鲁细分显 0、`/pal events` 无据点事件（已优雅）；bases
  配置节保留但描述标注「仅在 features.guilds_bases 开启时生效」。
- **events OFF**：注入 null EventService → 玩家/游戏数据 ingestion 不生成事件；
  events 命令回「未开放」且不进 help；`/pal today` 的事件相关部分自然为空。
- **report OFF**：today 命令回「未开放」且不进 help（报表读时聚合，采集不变）。
- **core**：恒启用，无开关。

## 7. 保留代码（可复原性）

game-data / guild / base / PalBox 的领域模型、服务、normalizer、query、formatter
与其单元/集成测试**全部保留**。禁用 = 不接线；`features.guilds_bases=true` 即整组
恢复原行为。本规格不删除任何现有功能代码。

## 8. 兼容与迁移

- `AppConfig` 增 `features` 字段（`field(default_factory=...)` 置末位）；既有直接
  构造 `AppConfig` 的测试因默认值不受影响。
- 依赖 game-data 的**集成测试**（公会/据点/事件/世界帕鲁细分 pipeline）需在其
  构造的 features 中**显式启用** `guilds_bases`（及 events），否则装配不接线导致
  断言失败。逐一排查并调整。
- **默认行为变化**：全新安装默认 `guilds_bases=false` → 公会/据点命令默认不可用
  （符合 Palworld 1.0 现实）。README 说明如何开启。

## 9. 测试计划

| 层 | 用例 |
|---|---|
| FeaturesConfig 解析 | 缺 features 节→默认(report/events on, guilds_bases off)；显式覆盖各值；类型 |
| 装配-端点 | guilds_bases 关→交给 Scheduler 的端点集合不含 GAME_DATA；开→含。core 端点恒含 |
| 装配-采集 | guilds_bases 关→不构造 Guild/BaseService、fetcher 从不被请求 GAME_DATA；events 关→ingestion 后 repo 无事件；开→有 |
| 命令 gating | 禁用组命令回 L("feature_disabled")、不在 help；启用组命令正常；core 命令恒可用 |
| 混合命令降级 | guilds_bases 关下 /pal world 显核心+帕鲁 0、/pal status 据点数仍来自 metrics |
| schema/README | features 节结构断言；README 说明 guilds_bases 默认关与开启方法 |
| 回归 | 默认配置下 core 全命令正确；调整后既有 523 测试全绿 |

## 10. 风险

- **高回归面**：改 container 装配 + Scheduler 端点选择 + Commands gating + config +
  schema。523 测试护航，需逐步 TDD。
- **events null-sink**：注入 no-op EventService 不得破坏 players/guilds ingestion
  的其余逻辑（它们 `.events = events`）——需确认 EventService 接口可被 no-op 安全替换。
- **集成测试迁移量**：多个集成测试依赖 game-data/events，需显式启用相应组，逐一调整。
- **命令 gating 位置**：务必在 Commands 层（运行时），非 main.py 装饰器（静态）。

## 11. 复核记录

（待对抗式复核后填写）
