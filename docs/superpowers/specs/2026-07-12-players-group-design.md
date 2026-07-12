# players 组（玩家个体功能）设计

> 状态：设计已定稿，待三视角对抗复核。范围为「功能全景盘点」中的 **Batch 3**（玩家个体），从全景蓝图中单独切出、独立交付。

## 1. 背景与定位

PalChronicle 是只读的 Palworld 世界纪事 AstrBot 插件（六边形/分层架构，隐私优先，功能按 `features` 组可插拔）。现有命令覆盖世界级聚合（status/online/world/rules/today/events）与公会据点（默认关，依赖上游 game-data）。本设计新增一个**默认关闭**的功能组 **`players`**，提供**玩家个体维度**的查询：排行榜、逐人档案、我的档案与自助绑定。

玩家个体数据天然比世界聚合更敏感（「逐人查上线历史 ≈ 监视」），故整组默认关、字段精简、strict 更保守、并提供 opt-out。设计遵循一条硬红线：**只读**，绝不写游戏服务器；所有「写」仅落本插件 DB（绑定/隐藏）与配置。

## 2. 目标与非目标

**目标**
- 新增 `players` 组（默认关），含 4 条命令：`rank` / `player` / `me` / `bind`。
- 复用 `core` 端点已采集的数据，**不新增 REST 端点、不改轮询**。
- 隐私默认收敛：精简字段、strict 更保守、管理员排除名单 + 玩家自助隐藏。

**非目标（明确排除）**
- 不做历史/全时段时长榜（`daily_aggregates` 表存在但无写入器、是空表 —— 时长榜只能实时算今日）。属未来 Batch 2。
- 不做建筑榜（`building_count` 可靠性/含义未验证）。
- 不做推送/订阅（Batch «未来附录»，需 scheduler→bot 新基建）。
- 不改 core 的 `/pal online`、`/pal status` 行为：**玩家隐藏仅在 `players` 组内生效**。
- `bind` 不做游戏内归属校验（只读 REST 收不到游戏内聊天，无法验证；见 §9 风险 4）。

## 3. 架构与数据底座

`players` 组是**命令层能力**，不引入新端点。所依赖数据全部由 `core` 的 PLAYERS 端点持续采集，落在既有三张表：

| 表 | 关键字段 | 用途 |
|---|---|---|
| `players` PK`(player_key, world_id)` | `latest_name`, `latest_level`, `first_seen_at` | 显示名、等级榜、逐人查身份 |
| `player_sessions` | `player_key`, `joined_at`, `left_at`, `observed_seconds`, `status` | 是否在线、本次时长、时长今日聚合 |
| `player_observations` | `player_key`, `level`, `ping_bucket`, `observed_at` | 最新等级/ping（`latest_observation`） |

**现成 repo / 服务入口（勘探核准，签名逐字）：**
- `Repository.list_open_sessions(world_id) -> list[PlayerSession]` —— 当前全部在线会话（`status IN('active','uncertain')`），含 `observed_seconds`、`player_key`。
- `Repository.get_open_session(world_id, player_key) -> PlayerSession | None` —— 单人是否在线 + 本次 `observed_seconds`。
- `Repository.sessions_in_day(world_id, start_ts, end_ts) -> list[PlayerSession]` —— 时间窗内交叠会话；时长今日榜的唯一聚合源。
- `Repository.get_player_by_name(world_id, name) -> PlayerIdentity | None` —— 按 `latest_name` 精确反查；逐人查与「名字→key」映射的唯一路径。
- `Repository.get_player(world_id, player_key) -> PlayerIdentity | None`、`Repository.latest_observation(world_id, player_key) -> PlayerObservation | None`。
- 现成组装范式：`QueryService._online_rows`（`query_service.py:58`）示范 `list_open_sessions → latest_observation → get_player(取 latest_name)`；`ReportService.daily`（`report_service.py:128`）示范按 `player_key` 对 `observed_seconds` 求和。
- 时长展示：`formatters._fmt_duration(seconds)`（`>=1h → "H小时M分"`，否则 `"M分"`）—— 正合「粗粒度时长」。

**粒度声明**：`observed_seconds` 由 `apply_players` 按 `min(delta, cap)` 累加（`cap = players_seconds*1.5`），跨午夜会话不切分而全额计入交叠当日。故「本次在线时长」「今日时长」均为近似值，输出以粗粒度呈现，不宣称精确。

## 4. 命令逐条设计

命令惯例（全组遵守）：单前缀 `/pal <sub>`，`sub` 名 = `Commands` 方法名 = `command_registry.COMMANDS` 的命令名 = `HELP_LINE` 键，**四者逐字一致**（`@_gated` 用 `fn.__name__` 反查 `COMMAND_GROUP`，漂移即 `KeyError`）；末尾 `@服务器名` 经 `parse_arg` 解析；含空格的位置参数（玩家名）用 `arg.name`；只读查询复用 `_resolve_world`。四条命令方法均挂 `@_gated`（归 `players` 组）。

### 4.1 `/pal rank [time|level] [@s]`
- **无参**：同时输出**两榜**（时长今日 Top-N + 等级 Top-N）。
- **`time` / `level`**：只出对应一榜。
- **Top-N**：默认 5，由 `players.rank_top_n` 配置。
- **时长今日榜**：`sessions_in_day(world, 今日起, 今日止)` → 按 `player_key` 求和 `observed_seconds` → 过滤 `excluded_keys` → 降序取前 N → `get_player` 解析 `latest_name`。行：`· {名} {时长}`（`_fmt_duration`）。当日边界用 `ReportService._day_bounds` / `QueryService._server_day_start`（服务器时区）。
- **等级榜**：对**全体已观测玩家**（`players` 表 `latest_level`）降序 → 过滤 `excluded_keys` → 取前 N，经新增 `Repository.list_players_by_level(world_id) -> list[PlayerIdentity]`（按 `latest_level` DESC 枚举；`players` 表当前无任何列表查询方法，须新写）。行：`· {名} Lv{n}`。榜含离线玩家（语义为「服务器最高等级」，非「当前在线最高」）。
- **strict 模式**：只出**等级榜**，时长榜停用（时长≈作息）；`/pal rank time` 在 strict 回 `L("rank_time_strict")`（「时长榜在 strict 隐私模式下停用」）。
- **空态**：无数据 → `L("rank_empty")`（如「今日暂无上线记录。」）。

### 4.2 `/pal player <玩家名> [@s]`
- 逐人查（照 `guild` 命令的「手写 `arg.name` + not-found」范式，`commands.py:102`）。
- **输出（精简）**：等级 + 是否在线 + 本次在线时长（粗）。在线判定 = 目标 `player_key` 存在 open session（`get_open_session` 非空）。
- **strict**：砍到 等级 + 是否在线。
- **未找到 / 被排除 / 被隐藏**：**一律回 `L("player_not_found", name=...)`**（被隐藏者不泄露其存在）。
- 名字→key 经 `get_player_by_name`；若该名从未被观测则 identity 为 `None` → not_found。

### 4.3 `/pal me [hide|show] [@s]`
- 与 `player` 同组同开关（「me 依附 player」= 同一 `players` 开关 + 字段 ⊆ player）。
- **无参**：看自己 —— 取当前平台账号绑定的 `player_key`；未绑定 → `L("me_unbound")`（「你还没绑定，用 /pal bind <玩家名>」）。已绑定 → 输出同 `player`（字段 ⊆ player，strict 同样砍）。
- **`hide`**：`set_hidden(world, 自身 key)`，回 `L("me_hidden")`。
- **`show`**：`unset_hidden(world, 自身 key)`，回 `L("me_shown")`。
- **所有 `me` 子命令（含 hide/show）均需先绑定**；未绑定一律回 `L("me_unbound")`（hide/show 操作的是「自身绑定的 key」）。需平台用户 id（`_sender_id`，见 §8 接线点 10 与 §9 风险 2）。

### 4.4 `/pal bind <玩家名> [@s]`
- **自助**命令（普通用户，非管理员）：绑定「本平台账号 ↔ 玩家名」。
- 经 `get_player_by_name(world, name)` 解析 `player_key`；找不到（从未上线）→ `L("bind_not_found", name=...)`。
- 成功 → `upsert_binding(platform_user_id, world, player_key)`（`ON CONFLICT` 覆盖，一账号一世界一绑定），回 `L("bind_ok", name=...)`。
- 无归属校验：可绑他人名；但 `me` 字段 ⊆ `player`（后者本就可查），故不产生新增泄露（见 §9 风险 4）。

## 5. 隐私模型

1. **默认关**：整组 `features.players` 默认 false。关闭时 `@_gated` 回 `L("feature_disabled")`、help 自动隐藏该组命令（照 `guilds_bases` OFF 现成范式）。
2. **精简字段 + strict 收敛**：player/me 默认 等级+在线+本次时长，strict 砍到 等级+在线；rank 在 strict 只出等级榜。strict 判定散落各 service，无集中 helper，本组在 `players` 服务/formatter 内自行 `if cfg.privacy.mode == "strict"` 裁字段（照 `privacy_filter.py:73` 的 `== "strict"` 范式）。
3. **opt-out = 排除名单 ∪ 自助隐藏**，读侧统一过滤 `excluded_keys`：
   - **管理员排除名单**：配置 `players.exclude_names`（逗号分隔字符串）；查询时逐名经 `get_player_by_name` 解析成 key 集。
   - **自助隐藏**：`/pal me hide` 落 `hidden_players` 表；`get_hidden_keys(world)` 返回 key 集。
   - `excluded_keys = 排除名单解析集 ∪ get_hidden_keys(world)`，在 rank（两榜）与 player 查询处统一过滤。`player` 命中被排除者按 not_found 处理。
4. **隐藏范围**：**仅 `players` 组内**。core 的 `/pal online`、`/pal status` 不引入隐藏过滤、行为不变（避免 core 依赖 players 组数据的跨组耦合，且不回归默认开命令）。

## 6. 新增持久化（`migration_0003`）

迁移机制：`migrations.py` 由 `PRAGMA user_version` 顺序驱动、幂等；新增 = 追加 `migration_0003` 函数 + SQL，`append` 到 `MIGRATIONS` 列表（照 `migration_0002` 范式）。

**建表 SQL：**
```sql
CREATE TABLE IF NOT EXISTS player_bindings (
  platform_user_id TEXT NOT NULL,
  world_id         TEXT NOT NULL,
  player_key       TEXT NOT NULL,
  created_at       INTEGER NOT NULL,
  PRIMARY KEY (platform_user_id, world_id)
);
CREATE TABLE IF NOT EXISTS hidden_players (
  world_id   TEXT NOT NULL,
  player_key TEXT NOT NULL,
  PRIMARY KEY (world_id, player_key)
);
```
（隐藏用独立表：`hidden_players` 存在即隐藏，便于按 key 集在读侧过滤；不与 `player_bindings` 耦合。）

**repo 方法（照 `group_servers` 的 UPSERT/DELETE/SELECT 范式，全走 `Database.write_tx()/execute_write`）：**
- `upsert_binding(platform_user_id, world_id, player_key) -> None`
- `get_binding(platform_user_id, world_id) -> str | None`（返回 player_key）
- `set_hidden(world_id, player_key) -> None`
- `unset_hidden(world_id, player_key) -> None`
- `get_hidden_keys(world_id) -> set[str]`

## 7. 配置

**功能开关** `features.players`（bool，**默认 false**）—— 三处默认值必须一致：
- `_conf_schema.json` `features.items.players`：`{"type":"bool","default":false,"description":"玩家个体查询（排行/档案/自助绑定；默认关，含个体隐私考量）"}`
- `config.py`：`FeaturesConfig` 加 `players: bool` 字段；`enabled()` dict 加 `"players": self.players`；`_default_features()` 加 `players=False`；`parse_config` 构造加 `players=bool(f.get("players", False))`。
- `config_view.py` 无需改：`features` 已在 `_TOP_KEYS` 且是原样透传的 object 节。

**`players` 配置节**（新增顶层 object 节，照 `bases` 节范式）：
- `rank_top_n`（int，默认 5）
- `exclude_names`（string，逗号分隔玩家名；空串=无排除）

对应改动：
- `_conf_schema.json` 加顶层 `"players"` object 节。
- `config.py` 加 `PlayersConfig` dataclass + `AppConfig.players` 字段 + `parse_config` 解析块（`rank_top_n=int(...)`，`exclude_names` split 成 `list[str]` 去空白）。
- `config_view.py`：`_TOP_KEYS` 加 `"players"`；object 节形状校验元组加 `"players"`；`_NUM_FIELDS` 加 `(("players","rank_top_n"),"int")`。`exclude_names` 为 object 节内 string 键，随节透传（不进 `_LIST_SECTIONS`）。

**存储介质边界**：`rank_top_n`/`exclude_names` 属配置（低频、管理员改，config save 触发 Container 全量重启可接受）；`bind`/`hide` 属高频用户运行时写，**必须落 DB**（`player_bindings`/`hidden_players`），不落 config。

## 8. 接线点（文件级清单，供 writing-plans 拆任务）

1. `_conf_schema.json`：`features.items.players`（bool default false）+ 顶层 `players` 节（rank_top_n / exclude_names）。
2. `palchronicle/config.py`：`FeaturesConfig` 4 处 + `PlayersConfig` + `AppConfig.players` + `parse_config`。
3. `palchronicle/presentation/command_registry.py`：`COMMANDS` +4 项 `(rank/player/me/bind, "players")`；`HELP_LINE` +4 键。
4. `palchronicle/infrastructure/migrations.py`：`migration_0003`（建两表）+ `MIGRATIONS` 追加。
5. `palchronicle/adapters/sqlite_repository.py`：5 个 binding/hidden 方法 + `list_players_by_level(world_id)`（等级榜枚举，`players` 表按 `latest_level` DESC，新写）。
6. `palchronicle/application/`（`query_service.py` 扩或新 `players_service.py`）：rank（两榜聚合 + `excluded_keys` 过滤）、player（逐人查 + 排除→not_found）、me 取绑定 key 后同 player。
7. `palchronicle/presentation/commands.py`：`Commands` 加 `rank/player/me/bind`，各 `@_gated`；`me`/`bind` 方法签名扩 `sender_id`（`bind` 自助、非 admin）。
8. `palchronicle/presentation/formatters.py`：`format_rank` / `format_player` / `format_me`（多行 + `· ` 前缀 + `_fmt_duration` + 空态走 `L()`）。
9. `palchronicle/presentation/locale.py`：新增 `player_not_found` / `me_unbound` / `me_hidden` / `me_shown` / `bind_ok` / `bind_not_found` / `rank_empty` / `rank_time_strict` 等键。
10. `main.py`：4 个 `@pal.command` 薄壳（照 `status:257`）+ **新增 `@staticmethod _sender_id(event)`**（取平台用户 id，透传给 `me`/`bind`）。
11. `palchronicle/container.py`：若设专属 `players` service，照 `events` 模式按 `features.players` 门控实例化；`active_endpoints`/`ENDPOINT_GROUP` **不改**。

## 9. 已知约束与风险（须在实现/plan 中处置）

1. **时长榜仅今日**：`daily_aggregates` 空表无写入器，无历史每日聚合源。文档明示，不做历史/全时段榜。
2. **`_sender_id` 属性未验证**（最高风险）：`main.py` 现无取平台用户 id 的 helper，仓库从未在 event 上取过 sender id；`event.get_sender_id()` / `event.message_obj.sender.user_id` 为待证候选。**plan 首个任务 = 实测确认真实属性**，未确认前 `me`/`bind` 不可靠。
3. **名字→key 依赖曾被观测**：排除名单/绑定的名字必须此前上线过才能经 `get_player_by_name` 映射；从未上线的名字对排除无效、绑定报 not_found。高置信玩家 key = HMAC(userId)，无法从名字直接反算，故必须走 `get_player_by_name`，不能对名字直接 `hash_user_id`。
4. **自助 `bind` 无归属校验**：可绑他人名。缓解 = `me` 字段 ⊆ `player`（该数据本就可查），无新增泄露；`bind`→`me hide` 可为他人开启隐藏（只增隐私、低危 griefing），记为已知接受项。
5. **features 默认值双写**：schema default 与 `config.py` 硬编码须一致，否则「页面显示关但代码默认开」。`conf_schema_test` 锁 schema 侧，`config.py` 侧补默认值断言。
6. **读侧双过滤面**：`excluded_keys` 需在 rank（两榜）与 player 三处一致过滤，易漏 —— 收敛到单一 `_load_excluded_keys(world)` helper 供三处共用。

## 10. 测试策略

- **组 OFF 语义端到端**（照 `guilds_bases` OFF 现成范式）：`features.players=false` 时 `rank/player/me/bind` 均回 `feature_disabled`，help 不列这四条；`ON` 时恢复。
- **schema**：`conf_schema_test` 加 `features.items.players.default is False` 断言 + `players` 节结构断言。
- **config_view**：`players` 节 passthrough 不剥离；`rank_top_n` 非法值走 `invalid_field`。
- **命令单测**：rank 两榜排序/Top-N 截断/空态；player 命中/未找到/被排除→not_found；me 未绑定/已绑定/hide/show；bind 成功/未找到。
- **隐私三态**：strict（player/me 砍字段、rank 砍时长榜）、exclude 名单过滤、self-hide 过滤，各自断言目标 key 不出现在 rank/player 输出。
- **迁移**：`migration_0003` 幂等、`user_version` 递增、两表可读写。

## 11. 实施顺序（writing-plans 细化，此处给骨架）

0. **Spike**：实测确认 `_sender_id` 真实属性（阻断 me/bind）。
1. 配置层：`features.players` + `PlayersConfig`（schema + config.py + config_view + 测试）。
2. 持久化：`migration_0003` 两表 + 5 个 repo 方法 + 迁移测试。
3. 命令注册与 gating：`COMMANDS`/`HELP_LINE` +4、`@_gated`、OFF 语义端到端测试。
4. 查询/格式化：rank（两榜 + 排除过滤 + strict）、player（逐人 + not_found + strict）。
5. 绑定与自我：`_sender_id` 接入、`bind`、`me`（含 hide/show）。
6. 隐私收敛复核：`_load_excluded_keys` 单一过滤面、strict 三态、README 命令表与功能组矩阵补 `players` 行。
