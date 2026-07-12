# players 组（玩家个体功能）设计

> 状态：三视角对抗复核已完成，findings 全部裁定并整合入本稿（详见 §12 复核裁定表）。范围为「功能全景盘点」中的 **Batch 3**（玩家个体），从全景蓝图中单独切出、独立交付。

## 1. 背景与定位

PalChronicle 是只读的 Palworld 世界纪事 AstrBot 插件（六边形/分层架构，隐私优先，功能按 `features` 组可插拔）。现有命令覆盖世界级聚合（status/online/world/rules/today/events）与公会据点（默认关，依赖上游 game-data）。本设计新增一个**默认关闭**的功能组 **`players`**，提供**玩家个体维度**的查询：排行榜、逐人档案、我的档案与自助绑定。

玩家个体数据天然比世界聚合更敏感（「逐人查上线历史 ≈ 监视」），故整组默认关、字段精简、strict 更保守、并提供 opt-out。设计遵循一条硬红线：**只读**，绝不写游戏服务器；所有「写」仅落本插件 DB（绑定/隐藏）与配置。

## 2. 目标与非目标

**目标**
- 新增 `players` 组（默认关），含 4 条命令：`rank` / `player` / `me` / `bind`。
- 复用 `core` 端点已采集的数据，**不新增 REST 端点、不改轮询**。
- 隐私默认收敛：精简字段、strict 更保守、管理员排除名单 + 玩家自助隐藏，且 opt-out 无静默失效。

**非目标（明确排除）**
- 不做历史/全时段时长榜（`daily_aggregates` 表存在但无写入器、是空表 —— 时长榜只能实时算今日）。属未来 Batch 2。
- 不做建筑榜（`building_count` 可靠性/含义未验证）。
- 不做推送/订阅（Batch «未来附录»，需 scheduler→bot 新基建）。
- 不改 core 的 `/pal online`、`/pal status` 行为：**玩家隐藏仅在 `players` 组内生效**。
- `bind` 不做游戏内归属校验（只读 REST 收不到游戏内聊天，无法验证；缓解与残余风险见 §5.5、§9 风险 4）。
- 不做管理员「清除某玩家自助隐藏」命令（自助隐藏由被隐藏者自救 + hidden_by 审计兜底，见 §5.5）。可为后续。

## 3. 架构与数据底座

`players` 组是**命令层能力**，不引入新端点。所依赖数据全部由 `core` 的 PLAYERS 端点持续采集，落在既有三张表：

| 表 | 关键字段 | 用途 |
|---|---|---|
| `players` PK`(player_key, world_id)` | `latest_name`, `latest_level`, `last_seen_at` | 显示名、等级榜、逐人查身份 |
| `player_sessions` | `player_key`, `joined_at`, `left_at`, `observed_seconds`, `status` | 是否在线、本次时长、时长今日聚合 |
| `player_observations` | `player_key`, `level`, `ping_bucket`, `observed_at` | 最新等级/ping（`latest_observation`） |

**现成 repo / 服务入口（勘探核准，签名逐字）：**
- `Repository.list_open_sessions(world_id) -> list[PlayerSession]` —— 当前全部在线会话（`status IN('active','uncertain')`），含 `observed_seconds`、`player_key`。
- `Repository.get_open_session(world_id, player_key) -> PlayerSession | None` —— 单人是否在线 + 本次 `observed_seconds`。
- `Repository.sessions_in_day(world_id, start_ts, end_ts) -> list[PlayerSession]` —— 时间窗内交叠会话；时长今日榜的唯一聚合源。
- `Repository.get_player_by_name(world_id, name) -> PlayerIdentity | None` —— 按 `latest_name` 精确反查，取 `last_seen_at DESC LIMIT 1`（**只返回一条**，见 §5.3 为何不足以做排除）。
- `Repository.get_player(world_id, player_key) -> PlayerIdentity | None`、`Repository.latest_observation(world_id, player_key) -> PlayerObservation | None`。
- 现成组装范式：`QueryService._online_rows`（`query_service.py:58`）示范 `list_open_sessions → latest_observation → get_player(取 latest_name)`；`ReportService.daily`（`report_service.py:128`）示范按 `player_key` 对 `observed_seconds` 求和。
- 时长展示：`formatters._fmt_duration(seconds)`（`>=1h → "H小时M分"`，否则 `"M分"`）—— 正合「粗粒度时长」。

**读侧落点（定死，消除命名撞车）**：所有 players 组读逻辑**扩入 `QueryService`**（已持 `repo`/`cfg`/`clock`，复用成本最低），**不新建服务**。应用层已有写侧 `PlayerService`（`player_service.py`，采集落库），职责相反，绝不与之同名；容器装配沿用现状，不新增 service（`me`/`bind`/`hide` 的 DB 读写由 `Commands` 经 `self._repo` 直连，`QueryService` 负责 rank/player 聚合）。

**粒度声明**：`observed_seconds` 由 `apply_players` 按 `min(delta, cap)` 累加（`cap = players_seconds*1.5`），跨午夜会话不切分而全额计入交叠当日。故「本次在线时长」「今日时长」均为近似值，输出以粗粒度呈现，不宣称精确。

## 4. 命令逐条设计

命令惯例（全组遵守）：单前缀 `/pal <sub>`，`sub` 名 = `Commands` 方法名 = `command_registry.COMMANDS` 的命令名 = `HELP_LINE` 键，**四者逐字一致**（`@_gated` 用 `fn.__name__` 反查 `COMMAND_GROUP`，漂移即 `KeyError`）；末尾 `@服务器名` 经 `parse_arg` 解析。**位置参数取值域**：`parse_arg` 把 `@server` 前的所有 token 拼成 `arg.name`；`rank` 的 `arg.name ∈ {"", "time", "level"}`、`me` 的 `arg.name ∈ {"", "hide", "show"}`，其余值一律回该命令默认分支（rank→双榜、me→看自己），不作报错；`player`/`bind` 的 `arg.name` 为玩家名（可含空格）。副作用：玩家恰好取名为保留词（time/level/hide/show）时，该词在 rank/me 语境不可作玩家名——记为已知边角（与 `base #序号` 同级）。四条命令方法均挂 `@_gated`（归 `players` 组）。

### 4.1 `/pal rank [time|level] [@s]`
- **无参**：同时输出**两榜**（时长今日 Top-N + 等级 Top-N）。**`time` / `level`**：只出对应一榜。**Top-N**：默认 5，由 `players.rank_top_n` 配置。
- **时长今日榜**：`sessions_in_day(world, start, end)` → 按 `player_key` 求和 `observed_seconds` → 过滤 `excluded_keys` → 降序取前 N → `get_player` 解析 `latest_name`。行：`· {名} {时长}`（`_fmt_duration`）。
  - **当日边界统一口径**：`(start, end)` 一律经与 `ReportService._day_bounds` **同一实现**取得（尊重 per-server timezone、用 `start_local + timedelta(days=1)` 而非 `+86400`，正确处理 DST 的 23/25 小时日）。实现时**抽取共享 day-bounds helper** 供 `ReportService.daily` 与 rank 共用，使 rank「今日」与 `/pal today` 日报口径完全一致。**禁止**用 `QueryService._server_day_start`（只读全局 tz、且不返回 end）作为 rank 的日界来源。
- **等级榜**：对**已观测玩家**按 `latest_level` 降序 → 过滤 `excluded_keys` → 取前 N，经新增 `Repository.list_players_by_level(world_id) -> list[PlayerIdentity]`（`SELECT ... FROM players WHERE world_id=? AND latest_level IS NOT NULL ORDER BY latest_level DESC`；`players` 表当前无任何列表查询方法，须新写）。**同名去重**：同一真人可能有 HIGH/LOW 两个 `player_key` 行（三级身份回退），榜单按 `latest_name` 去重、保留 `last_seen_at` 最新的一行，避免同名双行。行：`· {名} Lv{n}`。
  - **暴露面登记（见 §5.4）**：等级榜使离线玩家的等级可查（此前仅在线玩家经 `list_open_sessions` 可见），属 players 组相对 core 的**新增个体暴露面**，随组默认关而收敛。**按产品决策（用户 2026-07-12），等级榜含离线玩家、在所有模式下一致**（等级=成就维度、不含作息/时序信息，敏感度低于时长榜），**不做 strict 仅在线收紧**。
- **strict 模式**：只出**等级榜**（仍含离线全体），时长榜停用（时长≈作息）；`/pal rank time` 在 strict 回 `L("rank_time_strict")`（「时长榜在 strict 隐私模式下停用」）。
- **空态**：无数据 → `L("rank_empty")`（如「今日暂无上线记录。」）。

### 4.2 `/pal player <玩家名> [@s]`
- 逐人查（照 `guild` 命令的「手写 `arg.name` + not-found」范式，`commands.py:102`）。
- **输出（精简）**：等级 + 是否在线 + 本次在线时长（粗）。在线判定 = 目标 `player_key` 存在 open session（`get_open_session` 非空）。字段裁剪走 §5.2 的共享 `_apply_strict`。
- **strict**：砍到 等级 + 是否在线。
- **未找到 / 被排除 / 被隐藏**：**一律回 `L("player_not_found", name=...)`**（被隐藏者不泄露其存在）。判定：`get_player_by_name` 得候选 key；若为 `None` 或候选 key ∈ `excluded_keys` → not_found。

### 4.3 `/pal me [hide|show] [@s]`
- 与 `player` 同组同开关（「me 依附 player」= 同一 `players` 开关 + 字段 ⊆ player，物理复用 §5.2 的同一段裁剪代码）。
- 需平台用户复合身份（`_sender_id`，见 §6/§8 接线点 10 与 §9 风险 2）。
- **所有 `me` 子命令（含 hide/show）均需先绑定**；未绑定一律回 `L("me_unbound")`（「你还没绑定，用 /pal bind <玩家名>」）。
- **无参**：取当前平台身份绑定的 `player_key` → 输出同 `player`（字段 ⊆ player，strict 同样砍）。
- **`hide`**：`set_hidden(world, 自身 key, hidden_by=平台哈希)`，回 `L("me_hidden")`。
- **`show`**：`unset_hidden(world, 自身 key)`，回 `L("me_shown")`。

### 4.4 `/pal bind <玩家名> [@s]`
- **自助**命令（普通用户，非管理员）：绑定「本平台复合身份 ↔ 玩家名」。
- 经 `get_player_by_name(world, name)` 解析 `player_key`。**存在性收敛**：若找不到（从未上线），**或**解析出的 key ∈ `excluded_keys`（被排除/被隐藏），一律回 `L("bind_not_found", name=...)`（与 `player` 一致，杜绝 bind 的差异化回包被用作存在性枚举）。
- 成功 → `upsert_binding(平台哈希, world, player_key)`（`ON CONFLICT` 覆盖，一身份一世界一绑定，last-writer-wins），回 `L("bind_ok", name=...)`。
- 无归属校验：可绑他人名；缓解、残余 griefing 与自救路径见 §5.5。

## 5. 隐私模型

### 5.1 默认关与 gating
整组 `features.players` 默认 false。关闭时 `@_gated` 回 `L("feature_disabled")`、help 自动隐藏该组命令（照 `guilds_bases` OFF 现成范式）。

### 5.2 精简字段 + strict 单点收敛
player/me 默认 等级+在线+本次时长，strict 砍到 等级+在线；rank 在 strict 只出等级榜且仅在线。strict 判定在本仓散落各 service、无集中开关（`privacy_filter.py:73` 等），players 组有 player/me/rank 三条出口易漏 —— 故**收敛为单一函数** `_apply_strict(view, mode)` 供 player 与 me **物理共用**同一段裁剪；rank 的「strict 只出等级榜/仅在线」也走单点判定。§10 对 player 与 me **各自**断言 strict 下无时长字段，锁死 me 不走旁路。

### 5.3 opt-out：排除名单 ∪ 自助隐藏（无静默失效）
读侧统一过滤 `excluded_keys`，经**单一** helper `QueryService._load_excluded_keys(world) -> set[str]` 计算，供 **rank 两榜 + player + bind 四处**共用（缺一即泄露）：
- **管理员排除名单**：配置 `players.exclude_names`（逗号分隔字符串）。每个名字必须解析为**该 world 下所有 `latest_name==name` 的 `player_key` 全集**，经新增 `Repository.list_players_by_name(world_id, name) -> list[str]`（返回全部匹配 key）——**不可**用 `get_player_by_name` 的单条结果，否则同名/改名（HIGH/LOW 双 key、离线后他人重名）会让排除**静默失效并误导管理员**。
- **自助隐藏**：`/pal me hide` 落 `hidden_players` 表；`get_hidden_keys(world)` 返回 key 集。
- `excluded_keys = (∪ 各 exclude_name 的全部匹配 key) ∪ get_hidden_keys(world)`。`player`/`bind` 命中即按 not_found 收敛；rank 两榜聚合前先剔除。

### 5.4 隐藏范围与等级榜暴露登记
- **隐藏范围**：**仅 `players` 组内**。core 的 `/pal online`、`/pal status` 不引入隐藏过滤、行为不变（避免 core 依赖 players 组数据的跨组耦合，且不回归默认开命令）。
- **等级榜暴露**：登记为 players 组相对 core 的新增个体暴露面（离线玩家等级变可查）。**按产品决策（用户 2026-07-12）保留离线玩家、所有模式一致**（见 §4.1）；由「组默认关」这一道收敛——等级是成就维度、不含作息，接受此暴露。

### 5.5 bind 无归属校验的残余风险（诚实登记，非「低危」轻描淡写）
`bind` 无法在只读 REST 下验证归属，故 A 可绑 B 的名字。影响与缓解：
- **读侧无新增泄露**：`me` 字段 ⊆ `player`，A 经伪绑定看到的 B 数据，`player` 本就可查。
- **写副作用 = 可为他人开启隐藏（griefing）**：A 伪绑 B 后 `/pal me hide` 可令 B（可能是榜首）从 rank/player 消失。**这是无需权限、对任意玩家、结果对受害者初始不可见的持久化写**——不轻描淡写。
- **缓解三重**：① `hidden_players.hidden_by` 记录发起者平台哈希，供审计与未来管理面；② **自救路径**：`bind` 为 last-writer-wins，B 亲自 `/pal bind <己名>` 覆盖绑定后 `/pal me show` 即可解除隐藏（隐藏标志挂在 key 上，任何绑该 key 者可翻转）；③ **管理员排除名单是权威 opt-out**（不经 bind、不可被普通用户翻转），真正需要「确保某人隐藏」时用它。
- **残余**：B 在被隐藏后无主动通知（需自己发现）；A/B 反复 hide/show 的拉锯可能，但只增隐私、危害有限。接受为已知项。
- **产品决策（用户 2026-07-12）**：本轮**明确暂不处理冒充/归属校验**（只读 REST 无可靠验证手段，成本高收益低）。保留自助隐藏；冒充与 griefing 作为已知接受项，`hidden_by` 审计字段照建、留待未来管理面复用，本轮不消费。

### 5.6 PII 处置：平台身份哈希落库
`player_bindings` 的平台身份**不明文落库**（与全库「玩家标识一律 HMAC」红线一致）：`_sender_id(event)` 产出复合明文 `f"{platform_name}:{sender_id}"`（跨平台唯一，见 §9 风险 2），落库前经 `hash_user_id(salt, world_id, 复合明文)` 得 `platform_hash`（与 `player_key` 同规格 HMAC、world 加盐）。`bind`/`get_binding` 两侧对称哈希，等值匹配语义不变。`hidden_players.hidden_by` 同样存 `platform_hash`，非明文。

## 6. 新增持久化（`migration_0003`）

迁移机制：`migrations.py` 由 `PRAGMA user_version` 顺序驱动、幂等；新增 = 追加 `migration_0003` 函数 + SQL，`append` 到 `MIGRATIONS` 列表（照 `migration_0002` 范式）。

**建表 SQL：**
```sql
CREATE TABLE IF NOT EXISTS player_bindings (
  platform_hash TEXT NOT NULL,   -- HMAC(salt, world_id, "{platform_name}:{sender_id}")
  world_id      TEXT NOT NULL,
  player_key    TEXT NOT NULL,
  created_at    INTEGER NOT NULL,
  PRIMARY KEY (platform_hash, world_id)
);
CREATE TABLE IF NOT EXISTS hidden_players (
  world_id   TEXT NOT NULL,
  player_key TEXT NOT NULL,
  hidden_by  TEXT NOT NULL,       -- 发起者 platform_hash，供审计
  created_at INTEGER NOT NULL,
  PRIMARY KEY (world_id, player_key)
);
```
**world 维度与世界重置**：两表随 `world_id` 分区。`player_key = HMAC(salt, world_id, userId)` 本就 world-scoped，`world_id` 含 `worldguid`（`snapshot_service.py:89`，世界重置即换 `world_id`）。故绑定/隐藏**天然 world-scoped**：世界重置后旧行成为孤儿、`me` 回 `me_unbound`、隐藏失效，用户需**重新 bind/hide**。这是低频事件（持久服务器罕见重置），登记为已知限制（§9 风险 5）；`migration_0003` 之外**在既有 prune 路径追加清理孤儿 binding/hidden 行**（照 `group_servers.cleanup_orphan_bindings` 范式），避免旧行永久悬留。

**repo 方法（照 `group_servers` 的 UPSERT/DELETE/SELECT 范式，全走 `Database.write_tx()/execute_write`）：**
- `upsert_binding(platform_hash, world_id, player_key) -> None`
- `get_binding(platform_hash, world_id) -> str | None`（返回 player_key）
- `set_hidden(world_id, player_key, hidden_by) -> None`
- `unset_hidden(world_id, player_key) -> None`
- `get_hidden_keys(world_id) -> set[str]`
- `list_players_by_name(world_id, name) -> list[str]`（全部匹配 key，供排除名单，见 §5.3）
- `list_players_by_level(world_id) -> list[PlayerIdentity]`（等级榜枚举，滤 NULL、按 level DESC，见 §4.1）
- 孤儿清理方法（并入既有 prune），照 `cleanup_orphan_bindings` 范式。

## 7. 配置

**功能开关** `features.players`（bool，**默认 false**）—— 三处默认值必须一致：
- `_conf_schema.json` `features.items.players`：`{"type":"bool","default":false,"description":"玩家个体查询（排行/档案/自助绑定；默认关，含个体隐私考量）"}`
- `config.py`：`FeaturesConfig` 加 **`players: bool = False`**（**必须带 dataclass 默认值**，否则现存 positional 构造如 `config_features_test.py:25` `FeaturesConfig(report=..., events=..., guilds_bases=...)` 缺参 `TypeError`）；`enabled()` dict 加 `"players": self.players`；`_default_features()` 加 `players=False`；`parse_config` 构造加 `players=bool(f.get("players", False))`。
- `config_view.py` 的顶层白名单 `_TOP_KEYS` 已含 `features`，此键无需动。

**`players` 配置节**（新增顶层 object 节，照 `bases` 节范式）：
- `rank_top_n`（int，默认 5）
- `exclude_names`（string，逗号分隔玩家名；空串=无排除）。仅受 `config_view` 的 `_MAX_BODY`(256KB) 整体约束、无 per-field 上限（object 节不过 `_MAX_STR`）——名单场景可接受，记为已知。

对应改动（后端）：
- `_conf_schema.json` 加顶层 `"players"` object 节（每字段带 `default`，确保 AstrBot 种入默认值，规避首存 `rank_top_n=undefined→NaN→invalid_field`，见 §9 风险 7）。
- `config.py` 加 `PlayersConfig` dataclass + `AppConfig.players` 字段 + `parse_config` 解析块（`rank_top_n=int(...)`，`exclude_names` split 成 `list[str]` 去空白）。
- `config_view.py` **两处都改**：`_TOP_KEYS`（`:27`）加 `"players"`；object 节形状校验元组（`:142` 硬编码 `("routing",...,"features")`，与 `_TOP_KEYS` 是**两处独立**表，漏改则 players 非 Mapping 时不报 `invalid_shape` 而透传脏数据）加 `"players"`。`_NUM_FIELDS` 加 `(("players","rank_top_n"), "int")`。`exclude_names` 随 object 节透传（不进 `_LIST_SECTIONS`）。

**存储介质边界**：`rank_top_n`/`exclude_names` 属配置（低频、管理员改，config save 触发 Container 全量重启可接受）；`bind`/`hide` 属高频用户运行时写，**必须落 DB**（`player_bindings`/`hidden_players`），不落 config。

## 8. 接线点（文件级清单，供 writing-plans 拆任务）

**后端**
1. `_conf_schema.json`：`features.items.players`（bool default false）+ 顶层 `players` 节（rank_top_n / exclude_names，均带 default）。
2. `palchronicle/config.py`：`FeaturesConfig` 4 处（字段带默认值）+ `PlayersConfig` + `AppConfig.players` + `parse_config`。
3. `palchronicle/presentation/command_registry.py`：`COMMANDS` +4 项 `(rank/player/me/bind, "players")`；`HELP_LINE` +4 键。
4. `palchronicle/infrastructure/migrations.py`：`migration_0003`（建两表）+ `MIGRATIONS` 追加。
5. `palchronicle/adapters/sqlite_repository.py`：`upsert_binding`/`get_binding`/`set_hidden`/`unset_hidden`/`get_hidden_keys`/`list_players_by_name`/`list_players_by_level` + 孤儿清理并入 prune。
6. `palchronicle/application/query_service.py`：**扩** `QueryService`（不新建服务）—— rank（两榜聚合，日界走共享 `_day_bounds` helper，`_load_excluded_keys` 过滤，strict 分支）、player（逐人查 + 排除→not_found + `_apply_strict`）、`_load_excluded_keys`、`_apply_strict`。共享 day-bounds helper 抽取（`ReportService.daily` 与 rank 共用）。
7. `palchronicle/presentation/commands.py`：`Commands` 加 `rank/player/me/bind`，各 `@_gated`。`me`/`bind` **经 `self._repo` 直连** binding/hidden 方法（**不新增构造参数**，避免打挂 `commands_gating_test.py` 的关键字构造）；`me`/`bind` 方法签名扩 `sender_id` 形参（由 `main.py` 透传）。
8. `palchronicle/presentation/formatters.py`：`format_rank` / `format_player` / `format_me`（多行 + `· ` 前缀 + `_fmt_duration` + 空态走 `L()`）。
9. `palchronicle/presentation/locale.py`：新增 `player_not_found` / `me_unbound` / `me_hidden` / `me_shown` / `bind_ok` / `bind_not_found` / `rank_empty` / `rank_time_strict` 等键。
10. `main.py`：4 个 `@pal.command` 薄壳（照 `status:257`）+ **新增 `@staticmethod _sender_id(event)`** —— 返回复合 `f"{event.get_platform_name()}:{event.get_sender_id()}"`（**非**裸 `get_sender_id()`，否则跨平台碰撞，见 §9 风险 2），透传给 `me`/`bind`。
11. `palchronicle/container.py`：**不新增 service**、不改 `active_endpoints`/`ENDPOINT_GROUP`（无新端点）。

**前端（对抗复核揪出的整层遗漏，缺则 players 节不渲染、不回传、且打挂前端测试）**
12. `frontend/src/lib/schema.ts`：`OBJECT_SECTIONS` 追加 `players` 节 `{key:'players', title:'玩家个体', fields:[{key:'rank_top_n', type:'int', default:5}, {key:'exclude_names', type:'string', default:''}]}`。设置页遍历该**硬编码常量**渲染与 `collectBody`，只改后端 schema 不改此处则 players 节静默丢失。

## 9. 已知约束与风险（须在实现/plan 中处置）

1. **时长榜仅今日**：`daily_aggregates` 空表无写入器，无历史每日聚合源。文档明示，不做历史/全时段榜。
2. **`_sender_id` 必须复合、非裸 sender_id**：`event.get_sender_id()` 已证实存在（AstrBot 正确 API），但返回**平台内** id（QQ 号），多平台部署（QQ+Telegram 等）会跨平台碰撞同一行、绑到错误玩家。**必须**用 `f"{platform_name}:{sender_id}"` 复合。**plan Spike 同时实测** `get_platform_name()` 与 `get_sender_id()` 的存在性与稳定性。
3. **名字→key 依赖曾被观测**：排除名单/绑定的名字必须此前上线过才能映射；从未上线的名字对排除无效、绑定报 not_found。高置信玩家 key = HMAC(userId)，无法从名字直接反算，故走 `list_players_by_name`（全部匹配），不能对名字直接 `hash_user_id`。
4. **自助 `bind` 无归属校验 + 可为他人开启隐藏（griefing）**：**本轮产品决策=暂不处理冒充、接受为已知项**（用户 2026-07-12）。诚实登记，缓解=hidden_by 审计 + 本人自救（bind 己名 + me show）+ 管理员排除名单权威。详见 §5.5。
5. **世界重置使绑定/隐藏失效**：`world_id` 含 `worldguid`，重置即换、旧行成孤儿。低频、需重新 bind/hide；prune 清理孤儿。详见 §6。
6. **读侧四过滤面**：`excluded_keys` 需在 rank（两榜）、player、bind **四处**一致过滤 —— 收敛到单一 `_load_excluded_keys(world)`，禁止各处自行拼装。
7. **首存默认值**：`_conf_schema.json` 的 `players` 节须按标准 `object+items`（每字段带 default）写，让 AstrBot 种入默认值，规避 `rank_top_n` 缺值 → 前端 NaN → 后端 `invalid_field`。plan 加端到端校验：全新安装不触碰 players 节直接保存不报错。
8. **features 默认值双写**：schema default 与 `config.py` 硬编码须一致；`conf_schema_test` 锁 schema 侧，`config.py` 侧补默认值断言。

## 10. 测试策略

**后端**
- **组 OFF 语义端到端**（照 `guilds_bases` OFF 现成范式）：`features.players=false` 时 `rank/player/me/bind` 均回 `feature_disabled`，help 不列这四条；`ON` 时恢复。
- **schema**：`conf_schema_test` 加 `features.items.players.default is False` 断言 + `players` 节结构断言。
- **config_view**：`players` 节 passthrough 不剥离；`players` 非 Mapping → `invalid_shape`；`rank_top_n` 非法值 → `invalid_field`。
- **回归修复**：更新 `config_features_test.py:25` 等所有 positional 构造 `FeaturesConfig`/`AppConfig` 的用例（排查 `report_service_test.py` 等）。
- **命令单测**：rank 两榜排序/Top-N 截断/空态/DST 日界正确/等级榜滤 NULL+同名去重；player 命中/未找到/被排除→not_found；me 未绑定/已绑定/hide/show；bind 成功/未找到/**被隐藏者→bind_not_found**。
- **隐私三态**：strict（player **且** me 各自断言无时长字段、rank 砍时长榜；**等级榜含离线、不受 strict 影响**）、exclude 名单（同名多 key 全部命中、改名不旁路）、self-hide 过滤，各断言目标 key 不出现在 rank/player 且 bind 回 not_found。
- **迁移**：`migration_0003` 幂等、`user_version` 递增、两表可读写、孤儿清理。

**前端（对抗复核揪出的必改锁定测试）**
- `frontend/.../schema.test.ts`：`OBJECT_SECTIONS` 节列表 7→8 含 `players`。
- `frontend/.../collect.test.ts`：`TOP_KEYS` 加 `'players'`、`baseState().sections` 加 players 节，顶层键 ⊆ TOP_KEYS 断言通过。
- `frontend/.../SettingsPanel.test.ts`：`cfg()` mock 加 players 节，「渲染 9 节」断言 → 10 节。

## 11. 实施顺序（writing-plans 细化，此处给骨架）

0. **Spike**：实测确认 `event.get_platform_name()` + `event.get_sender_id()` 存在且组合稳定唯一（阻断 me/bind）。
1. 配置层：`features.players`（带默认值）+ `PlayersConfig`（schema + config.py + config_view 两处 + `_NUM_FIELDS` + 后端测试 + positional 回归修复）。
2. **前端配置**：`schema.ts` OBJECT_SECTIONS 加 players 节 + 3 个前端锁定测试更新（与后端 config 层平行的独立任务）。
3. 持久化：`migration_0003` 两表 + 7 个 repo 方法 + 孤儿清理并入 prune + 迁移测试。
4. 查询/格式化：`QueryService` 扩 rank（两榜 + 共享 day-bounds + `_load_excluded_keys` + strict 砍时长榜、等级榜含离线不变）、player（逐人 + not_found + `_apply_strict`）；`_load_excluded_keys`/`_apply_strict` 单点。
5. 绑定与自我：`_sender_id`（复合）接入、`bind`（存在性收敛 + 平台哈希落库）、`me`（含 hide/show + hidden_by）。
6. 隐私收敛复核 + 文档：四过滤面锁定、strict 三态、README 命令表与功能组矩阵补 `players` 行。

## 12. 三视角对抗复核裁定表

| # | 视角/严重度 | finding | 裁定 |
|---|---|---|---|
| C1 | 正确性/blocker | FeaturesConfig 必填字段打挂 positional 正测 | 采纳：字段带默认值 `= False` + 回归修复测试（§7、§10） |
| C2 | 正确性/major | rank 今日止 `+86400` DST 错 | 采纳：共享 `_day_bounds`(timedelta)（§4.1） |
| C3 | 正确性/major | `_day_bounds`(per-server) vs `_server_day_start`(全局) 口径分叉 | 采纳：统一走 `_day_bounds`，删 `_server_day_start`（§4.1） |
| C4 | 正确性/major | 新读服务与写侧 `PlayerService` 命名撞车 | 采纳：扩 `QueryService`，不新建服务（§3、§8.6） |
| C5 | 正确性/major | 绑定随 world 重置失效、无孤儿清理 | 采纳：world-scoped 明示 + prune 孤儿（§6、§9.5） |
| C6 | 正确性/minor | 等级榜同名多 key + level NULL | 采纳：滤 NULL + 按名去重（§4.1） |
| C7 | 正确性/minor | exclude_names 无长度上限 | 采纳（记为可接受）：注明仅受 `_MAX_BODY`（§7） |
| C8 | 正确性/nit | rank mode token 复用 arg.name 语义 | 采纳：取值域 + 兜底声明（§4 惯例） |
| C9 | 正确性/nit | 注入服务打挂 gating 测试 | 采纳：`me/bind` 走 `self._repo`（§8.7） |
| P1 | 隐私/major | 排除名单单条 key 静默失效 | 采纳：`list_players_by_name` 全部匹配（§5.3） |
| P2 | 隐私/major | bind griefing「替他人隐藏」 | 采纳：诚实登记 + hidden_by + 自救 + 排除名单权威（§5.5） |
| P3 | 隐私/major | 等级榜含离线全体=新暴露面 | 部分采纳：登记暴露（§5.4）；按产品决策（用户 2026-07-12）保留离线全体、所有模式一致、**不做 strict 仅在线**收敛 |
| P4 | 隐私/major | bind not_found/ok 存在性枚举旁路 | 采纳：bind 过滤 excluded_keys、回 not_found（§4.4、§5.3） |
| P5 | 隐私/major | platform_user_id 明文 PII | 采纳：`hash_user_id` 复合哈希落库（§5.6、§6） |
| P6 | 隐私/minor | strict 散落易漏 | 采纳：单一 `_apply_strict` 共用（§5.2） |
| P7 | 隐私/minor | hidden 随换世界失效 | 采纳：并入 C5 world-scoped 登记（§6、§9.5） |
| PL1 | 平台/blocker | 裸 sender_id 跨平台碰撞 | 采纳：复合 `platform:sender`（§9.2） |
| PL2 | 平台/blocker | 遗漏前端 `schema.ts` OBJECT_SECTIONS | 采纳：新增前端接线（§8.12） |
| PL3 | 平台/blocker | 打挂 3 个前端锁定测试 | 采纳：前端测试更新（§10） |
| PL4 | 平台/major | config_view 两处（_TOP_KEYS + 形状元组）须都改 | 采纳：显式两处（§7） |
| PL5 | 平台/minor | 首存 `rank_top_n` NaN→invalid_field | 采纳：schema 种默认值 + e2e 校验（§9.7） |
| PL6 | 平台/minor | rank/me 关键字 vs 玩家名歧义 | 采纳（并入 C8）（§4 惯例） |
