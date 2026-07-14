# 分级命令架构 + 模式基础 + 命令变体设计（v0.9.5 Phase 1）

> 状态：**已过三视角对抗复核并修订**（正确性/一致性、安全/隐私、AstrBot 平台兼容；2 Blocker + 多 Major 全并入）· 目标版本 **v0.9.5** · 这是 v0.9.5 的 **Phase 1**（命令体系）；Phase 2（分级感知权限 + 设置页权限章）另立 spec，同为 v0.9.5。

## 1. 定位与目标

把扁平的 26 个 `/pal <X>` 命令重构为**分级命令架构** `/pal <组> <动作>`，让命令更好记、更不易误触（尤其高危管理类）。同时为将来的**单/多世界运行模式**打地基（本轮只做基础，完整单模式 UX 留 Phase 3）。并引入**命令变体机制**（以 `rank today|total|level` 打样）。

**破坏性变更**：全面分级、**不保留旧扁平命令**（插件 0.9.x 未到 1.0，可接受）。help/文档随之重写引导迁移。

## 2. 范围

**In（Phase 1）**：
- 命令树重构为分级 `/pal <组> <动作>`（扁平自解析首词，非 AstrBot 原生嵌套组）。
- 少量高频命令保留一级：`rank` / `online` / `me` + 元命令 `help` / `whoami` / `confirm`。
- 模式基础：`world_mode`(single/multi，嵌 `routing`) 配置 + `RoutingService.resolve` 模式感知 + `/pal link` 单模式运行时拒 + help 省略。
- 命令变体机制：`rank [today|total|level]`（`total` = 新增「留存期内累计」时长榜查询）。
- help / docs / readme 随分级重写；命令真相源与锚定测试重构。
- 版本 v0.9.5。

**Out（非目标 / 后续 Phase）**：
- **Phase 2**：分级感知的权限模型（1 级整组 / 子级逐个 enable + admin-only）+ 设置页权限章命令树 UI。**本轮功能门（feature 组）与权限门（admin_only_commands/permission_admins）语义不变**，只是命令换了打法。
- **Phase 3**：完整单世界模式 UX（设置页简化、单模式访问模型细化）。
- 不引入 AstrBot 原生嵌套命令组（PR #17 已勘探并否决，继续扁平自解析）。
- 不改审计、REST、隐私脱敏、采集轮询等既有子系统。

## 3. 命令树（定案）

### 3.1 扁平（顶层）
| 命令 | 说明 | 功能门 |
|---|---|---|
| `/pal rank [today\|total\|level]` | 排行榜（默认 today；变体见 §6） | `players` |
| `/pal online` | 在线名单 | `core` |
| `/pal me [hide\|show]` | 我的信息 | `players` |
| `/pal help` | 帮助（按启用功能 + 角色过滤） | `core` |
| `/pal whoami` | 我的账号标识 | `core` |
| `/pal confirm` | 确认待执行的高危操作 | `core`（仅管理员可见/可用） |

### 3.2 `/pal world` —— 世界观测
| 子命令 | 说明 | 功能门 |
|---|---|---|
| `status` | 世界状态 | `core` |
| `overview` | 世界概览（旧 `/pal world`） | `core` |
| `rules` | 世界规则 | `core` |
| `events` | 世界事件 | `events` |
| `today` | 今日日报 | `report` |

### 3.3 `/pal guild` —— 公会与据点 [功能门 `guilds_bases`]
| 子命令 | 说明 |
|---|---|
| `list` | 公会列表 |
| `info <名称>` | 公会详情 |
| `bases` | 据点列表 |
| `base <名称\|#序号>` | 据点详情 |

### 3.4 `/pal player` —— 玩家 [功能门 `players`]
| 子命令 | 说明 |
|---|---|
| `info <玩家名>` | 玩家查询（旧 `/pal player <名>`） |
| `bind <玩家名>` | 绑定我的玩家 |
| `unbind` | 解除绑定 |

### 3.5 `/pal server` —— 服务器管理（单/多模式都用）
| 子命令 | 说明 | 门 |
|---|---|---|
| `announce <消息>` | 全服广播 | `server_admin_basic` + 管理员 |
| `save` | 存档 | `server_admin_basic` + 管理员 |
| `kick <目标> [理由]` | 踢人 | `server_admin_basic` + 管理员 |
| `unban <userid>` | 解封 | `server_admin_basic` + 管理员 |
| `ban <目标> [理由]` | 封禁（高危） | `server_admin_danger` + 管理员 |
| `shutdown <秒> [公告]` | 倒计时关服（高危） | `server_admin_danger` + 管理员 |
| `stop` | 立即停服（不存档、丢档，高危） | `server_admin_danger` + 管理员 |

### 3.6 `/pal link` —— 服务器选择/绑定（仅多世界模式；单模式注册但运行时拒 + help 省略，见 §5）
| 子命令 | 说明 | 门 |
|---|---|---|
| `list` | 服务器列表与本群绑定状态 | —（群内可见） |
| `add <名称>` | 本群绑定该服务器 | 管理员 |
| `remove <名称>` | 撤销本群绑定 | 管理员 |

### 3.7 命令树通则
- **子动作一律显式关键词**，杜绝「裸名字=某操作」歧义（不做 `/pal link <名>` 直接绑定）。
- **裸 group（`/pal world`/`/pal guild`/`/pal player`/`/pal server`/`/pal link`）= 该组迷你帮助**（列出可用子动作 + 一句说明），只提示不执行。**必须复用 `format_help` 同一角色/功能谓词真相源（复核视角2 M3，红线）**——不得另写一份过滤：admin-write 动作须 `is_admin AND features.enabled(组)` 才现身（`/pal server` 裸帮助对 guest **绝不**出现 kick/ban/stop）；未开放功能组的子动作不列（guilds_bases 关时 `/pal guild` 空）；confirm 仅管理员见。
- **命令树位置独立于功能门**：`today` 仍受 `report`、`rank` 仍受 `players`——命令换打法，功能门语义不变。
- 未知子动作（`/pal world foo`）→ 回该组用法提示（列出合法子动作）。

## 4. 路由与解析

推广现有「一个 group handler + Commands 层自解析首词分发」模式（`/pal server add/remove` 即此形）。

- **main.py 注册**：每个 group 一个 `@pal.command("<组>")`（world/guild/player/server/link）+ 每个扁平命令一个 `@pal.command("<名>")`（rank/online/me/help/whoami/confirm）。共 **11 个 `@pal.command`**（5 组 + 6 扁平），取代现 26 个扁平注册。
- **解析（防御式，复核视角3 M3）**：扩展 `server_arg` —— 新增「剥 `/pal <组>` 前缀 + 取子动作首词 + 剩余为参数」。**组词必须 strip-if-present**（不可假定 `message_str.split()[1]` 位置——AstrBot 各版本可能留 `pal world status`/`world status`/`status`，须沿用现 `_strip_prefix` 的逐一 strip 收敛）。保留尾 @override 剥离（多模式）+ 空白折叠 + ArgError（多 @token）。须覆盖三段式 `/pal guild info 战狼帮 @alpha`（sub=info、name=战狼帮、override=alpha）。**不得照搬 `server()` 现有 `override or name` 混淆**（`commands.py` 把 @token 当 name 的写法，推广到各组会错）。
- **子动作分发表**：数据结构 `{组: {动作: (实现方法名, 功能门组, 是否管理员写)}}`，作为路由 + help 生成 + 锚定的**单一真相源**（取代/重构现 `command_registry.COMMANDS`/`HELP_LINE`）。

### 4.1 门控落点重构（三视角互证 Blocker，必须规格化）
现有三条门在扁平模型下各就其位，分级后**都要迁移**——spec 原文「复用 `_gated`/`admin_write`」不足，漏了 `admin_denied` 锁与 `_gated` 的机制不兼容：

- **特征门 `_gated`（功能组门）无法复用装饰器**：现 `_gated` 按 `fn.__name__` 查 `COMMAND_GROUP` 取**单一组**。但一个 `Commands.world` handler 要分发 `status/overview/rules`(core) + `events`(events) + `today`(report) **三个不同功能组**的子动作——单方法名映射单组彻底失效。**改为**：废弃查询命令上的 `_gated` 装饰器，在**组分发循环内**按分发表的**每子动作功能门**判 `features.enabled(该动作组)`，未启用回 `feature_disabled`。
- **权限锁 `admin_denied`（`admin_only_commands`）执行点必须下沉**：现锁在 `main._guarded_cmd` 解析前用**扁平串**判（`admin_denied("status", sender)`）。group handler 在 main 层**拿不到完整路径** `world status`。**改为**：`admin_denied` 执行点**下沉进 Commands 组分发**，在解析出子动作后按**完整路径**判（`admin_denied("world status", sender)`）。扁平查询（rank/online/me）保留在 `_guarded_cmd` 按各自完整路径判。
- **busy/inflight 门闩须单独保留**：`_guarded_cmd` 现把 busy/inflight 门闩与 admin_denied 锁**一体**。下沉 admin_denied 后，group handler 仍须走一个**只做 busy/inflight**的门（拆出 `_guarded` 或复用），锁判在 Commands 内——门闩不能随之丢。
- **group handler 须传 `sender_id`**：现 world/guild/player 类 handler 只传 umo/msg/is_group；下沉锁判需要 sender——补传 sender_id（me/bind 已传，作范式）。
- **写命令（server 组）继续走 `admin_write`**：门序 admin 硬门先于 feature 不变；分发表每个写子动作映射**正确功能组**（kick/unban/announce/save→basic，ban/shutdown/stop→danger）。**任一写动作误接到查询路径而非 `admin_write` = 无鉴权关服**——§11 逐子动作锚定「走 admin_write + 正确组」。**server 组分发器绝不套方法级 `_gated`**（它跨 basic/danger 两组，`_gated` 只认单组会误判）。

## 5. 模式基础（Phase 1 打地基）

- **配置（落点见复核视角3 M1）**：`world_mode: "single" | "multi"`（默认 **"multi"** 保持现状）。**嵌进 `routing` object**（`routing.world_mode`），**不做裸顶层标量**——顶层标量会被 `config_view._TOP_KEYS` 白名单整包拒保存、且自建设置页无裸标量渲染件。落法：`_conf_schema.json` 放 `routing.items.world_mode`（`type:string, options:["multi","single"]`，AstrBot 原生页免费渲染，access_mode/privacy.mode 有先例）；`config.py` 从 `routing` 读；`config_view._ENUMS` 加 `"routing.world_mode"`；前端 routing 的 `ObjectSection.fields` 加该 enum 字段（复用现有 enum 渲染）。
- **`RoutingService.resolve(umo, override, is_group)` 模式感知**：
  - `single` 分支须置于 `resolve` **最顶端**（复核视角2 minor）——**早于**现有 RESTRICTED+私聊早退（`routing_service.py:43`），否则单模式私聊读会被不一致地拦。
  - `single`：**恒解析到唯一配置服务器**，忽略 @override 与群绑定；`_authorized` 放宽为 true（单世界=共享那一台，读命令全上下文可用）。**写命令仍受管理员硬门**（`admin_write` 内 admin 判定源自 permissions.admins，先于任何 resolve/feature，与 `_authorized` 完全独立——复核视角2 已确认安全不回退）。单模式私聊 admin 可执行写，**等价于今天 OPEN 模式**（非新增提权面，文档注明）。
  - `multi`（现状不变）：显式 @override → 群绑定 → 默认 → 唯一就绪 → 提示。
  - 边界：单模式 0 台 → 明确「未配置服务器」错误；>1 台 → 用列表首台 + 记一次告警（完整多台→单切换校验属 Phase 3）。
- **单模式架空 restricted 读控须显式告警（复核视角2 M1，隐私红线）**：`world_mode=single` 与 `access_mode=restricted` 并存时，`_authorized` 放宽 = **任意私聊/未授权群都能读该服务器全部数据**。须在**启动/保存配置时产生一条显式告警**「单模式下访问控制不生效，读命令对所有上下文开放」（经状态页/日志暴露）；文档/发布说明**粗体**标注此交互——让「翻单模式=对全网开放读」是有意识选择而非静默副作用。
- **命令面（措辞对齐平台现实，复核视角3 m1）**：AstrBot 类定义期**静态注册**，无法运行时按配置隐藏命令。故 `/pal link` 在单模式是「**注册但运行时按模式拒 + help 省略 + @尾缀忽略**」，非「隐藏」：`link` handler 顶部判单模式回「单世界模式无需选择服务器」；help 省略 link 组；`@server` 尾缀单模式被忽略。**守卫须置于调用 `routing.use`/`revoke` 之前**（复核视角2 minor）——直接键入 `/pal link add`（`link` 首词已注册）仍可达，handler 顶部守卫是唯一防线，否则残留绑定态会在切回 multi 时生效。
- **confirm 单模式语义**：单模式 resolve 恒成功，`confirm` 的 resolve 复检退化为「仅验服务器存在 + danger 组仍启用」；单模式无群授权可撤（link 拒），故「撤授权 stale」本不适用——**非安全回退**，文档一句注明。

## 6. 命令变体机制

以 `rank` 打样：`/pal rank [today|total|level]`，首词为 mode（缺省 today）。

**mode 串重命名是破坏性改动（复核视角1 M2）**：现 mode 串是 `time/level`（`commands.py` 判 `which not in ("time","level")`）。改为 `today/total/level` 须同步改：`commands.rank` 的 mode 分支、`commands_rank_test`（现断言 `rank("u","time",...)`）、`HELP_LINE`（现 `[time|level]`）、locale 键（`rank_time_strict` 等）。

- `today`（默认）：今日时长榜（现状）。
- `total`：**留存期内累计时长榜**（**非**「全时段」——`player_sessions` 受 prune 按 `session_days` 默认 365 天裁剪，`sqlite_repository.py:290`；文案须说明「留存期内」）。需**新增一个无日窗聚合 repo 方法**（现仅 `sessions_in_day` 带 start/end，无全量聚合）。
  - **语义与 today 不同套（复核视角1 M3）**：total 直接 `Σ observed_seconds`（无墙钟 overlap 封顶——today 的 overlap 逻辑是当日窗口特有），不可当作「today 逻辑无窗复用」。
  - **隐私必须复用 today 的名字级收敛剔除（复核视角2 M2，红线）**：total **不得**用只按 player_key 过滤的裸 SQL 聚合；须复用 `load_excluded_keys`（exclude_names + `get_hidden_keys`）**+ 与 today 同一套名字级收敛**（`query_service.rank` 里「同名任一 key 被排除/隐藏→整组名字剔除」`banned_names` 逻辑）。否则 `me hide`/改名/多 key 玩家的历史时长会重现在 total 榜。
- `level`：等级榜（现状，含离线全体）。
- **strict 隐私模式须双砍 today + total（复核视角1 M2 / 视角2 M2）**：strict 现只砍 `time`（今日时长）；`total` 同为时长榜，strict 下**today 与 total 都回 notice**——`commands.rank` 的 `if which=="time" and strict` 改为 `which in ("today","total")`，`format_rank` 的 `not strict` 守卫同步覆盖 total 块。`level` 不受 strict 影响。
- **QueryService.rank 加 mode 参数**；`total` 走新无窗聚合查询。`me` 的 `[hide|show]` 沿用现有子词解析（同属变体机制的既有形态）。
- 变体是「命令后缀子词」，与分级子动作解析同套机制；未来加变体 = 给某命令加 mode 分支。
- §11 加测试：隐藏一个有历史时长的玩家，断言其在 total 榜**整组名字消失**（不因另一同名 key 补位）；strict 下 total 回 notice。

## 7. 迁移（无向后兼容）

- 删除全部旧扁平命令注册（status/world/rules/guilds/guild/bases/base/events/today/player/bind/unbind/server/announce/save/kick/unban/ban/shutdown/stop 等），改为分级。
- `rank`/`online`/`me`/`whoami`/`help`/`confirm` 保留为扁平（`rank`/`me` 带变体）。
- help 全面重写为分级视图（组 + 子动作，按功能门 + 角色过滤）。
- docs/commands.md、docs/configuration.md、README、readme_test 锚点随分级重写（命令串锚点从 `/pal status` 等改为 `/pal world status` 等；readme_test 中文/命令锚点同步）。
- **`admin_only_commands` 格式迁移必须防静默失锁（复核视角2 B2，红线）**：旧配置 `["player"]` 升级后不匹配新路径 `player info` → 锁静默 no-op = fail-open。须：(a) `config._parse_permissions` 对每条**校验是否属 `LOCKABLE_COMMANDS`（完整路径集）**，未知条目**保留但产生告警**（`skipped_headers` 同款机制，经状态页/日志暴露给管理员），**绝不静默吞**；(b) 发布说明**列出 flat→full-path 迁移映射表**（`player`→`player info`、`status`→`world status`…）并强调「不迁移=失锁」；(c) §11 加测试：给旧扁平值断言产生 unknown-lock 告警而非静默。
- **`events` 的 `today_only` 子过滤废弃（复核视角1 m5）**：现 `commands.py` 支持 `/pal events today` 过滤当日事件；分级后 `/pal world events` 与 `/pal world today` 分家，该过滤无处安放——本轮**废弃**（记一笔；如需保留可作 events 变体，属额外范围）。

## 8. 命令真相源与锚定

**两种粒度须分清（关键，防歧义）**：
- **注册身份**（`@pal.command` / command_names 锚定）= **11 个首词**（5 组 + 6 扁平）。AstrBot 只认首词；子动作是 Commands 层自解析的。
- **门控/help 身份**（子动作分发表 / `admin_only_commands` 锁 / `LOCKABLE` / help 行）= **完整路径**（`world status`、`server kick`、`rank`、`me`）。功能门/管理员门/可锁性都按完整路径判定。

- **重构 `command_registry`**：`COMMANDS`（含子动作）/`HELP_LINE`/`PAL_COMMAND_STRINGS`（=完整路径集）/`LOCKABLE_COMMANDS`/`_NON_LOCKABLE` 全面改造为分级模型。`admin_only_commands` 配置值格式随之从扁平（`player`）变完整路径（`world status`、`rank`）——**破坏性、可接受**（无向后兼容，迁移防失锁见 §7），Phase 2 重做成树模型。
- **锚定常量必须分家（复核视角3 m2 / 视角1 M4）**：引入**新常量 `PAL_REGISTERED`（11 个首词：5 组 + 6 扁平）**供**注册锚定**；`PAL_COMMAND_STRINGS`/`LOCKABLE_COMMANDS`/`admin_only_commands` 走**完整路径**。`command_names_test::test_pal_command_strings_match_main_registrations` 改比对 `@pal.command` 正则 == `PAL_REGISTERED`（11），**不再**== `PAL_COMMAND_STRINGS`（否则 `LOCKABLE = PAL_COMMAND_STRINGS − _NON_LOCKABLE` 关系错乱）。
- **子动作分发表锚定用 introspection（不可自指，复核视角1 M4）**：不写「表 == handler 能分发的」（`table[group][sub]` 查表分发时此断言恒真、抓不到东西）。改为断言**分发表每个 target 方法名都能 `getattr(Commands, m)` 解析到可调用绑定方法**——抓 typo 方法名（如 `unbind_self` 方法 vs `player unbind` 串的映射错位）→ 防运行时 AttributeError。
- **`_NON_LOCKABLE` 有两处内联副本须同步（复核视角1 M1）**：`config.py` 的 `_NON_LOCKABLE`（`_parse_permissions` 用）+ `command_registry.py` 的 `_NON_LOCKABLE` 都从扁平名改**完整路径集**（server 各动作路径 + link 各动作路径 + 元命令）；`command_names_test::test_non_lockable_matches_registry_complement` 跨源全等锚定 + `config_permissions_test` 随之更新。
- **跨端锚定（完整路径）**：`LOCKABLE_COMMANDS`、前端 `PAL_COMMANDS`（Phase 2 才重做权限 UI；Phase 1 前端命令锁 chip 值 = 完整路径，与后端 LOCKABLE 跨端全等）。命令串扁平→分级，前端 `PAL_COMMANDS`/`frontend_pal_commands_test` 锚定值 + `SettingsPanel.vue` chip 直接入 `admin_only_commands` 的值 + 测试里硬编码扁平样例（`commands_permissions_test`/`main_permission_gate_test`/`config_view_permissions_test`/`_conf_schema.json` 描述示例）**全部同步**，否则跨端/单测红。
- 命名空间加载冒烟（`namespace_runtime_smoke_test`）改跑分级命令（group handler + 子动作），calls 清单改分组形（`(plugin.world, "world status")` 等，组词按现 server 约定保留在 message_str 内）；命令数更新。**注**：该测试直接调 handler + 手设 message_str、不经 AstrBot 真实路由——只验 handler 体 + 分发无 lazy-import 炸弹，多词路由由 PR #17 生产经验背书（§11 注明此限）。

## 9. 分层实现映射

| 层 | 改动 |
|---|---|
| `config.py` | `routing.world_mode`(single/multi 默认 multi) 解析；`_NON_LOCKABLE` 内联集分级化（完整路径）；`_parse_permissions` 加 admin_only_commands 未知条目校验+告警 |
| `_conf_schema.json` | `routing.items.world_mode`(type:string, options) + admin_only_commands 描述示例改完整路径 |
| `application/routing_service.py` | `resolve` 模式感知：single 分支置**最顶端**（早于 restricted 私聊早退）→ 唯一服务器 + `_authorized` 放宽读；single+restricted 并存产生显式告警；写仍管理员门在别处 |
| `application/query_service.py` + `adapters/sqlite_repository.py` | `rank` 加 mode 参数；`total` 走**新增无日窗聚合 repo 方法**（Σobserved_seconds）+ 复用 load_excluded_keys + 名字级收敛剔除；strict 双砍 today/total |
| `presentation/server_arg.py` | 分级解析（组词 strip-if-present、子动作首词、剩余参数、尾 @override、ArgError、空白折叠；三段式覆盖） |
| `presentation/command_registry.py` | 分级真相源重构（子动作分发表 + `PAL_REGISTERED`(11) + `PAL_COMMAND_STRINGS`(完整路径) + `_NON_LOCKABLE`(完整路径) + help 源） |
| `presentation/commands.py` | 组分发方法（world/guild/player/server/link）+ **门控下沉**（分发循环内按子动作功能门 + `admin_denied` 完整路径判；写走 admin_write；server 组不套 `_gated`）；rank mode 分支(today/total/level)+strict 双砍 |
| `main.py` | 11 `@pal.command`(5 组 + 6 扁平) 取代 26；group handler 补传 sender_id；busy/inflight 门闩保留（锁判下沉后）；@register 描述改（命令数/分级）；single+restricted 启动告警 |
| `presentation/formatters.py` | help 分级视图（组 + 子动作，功能门 + 角色过滤；裸 group 迷你帮助**复用同一谓词真相源**） |
| `presentation/config_view.py` | `_ENUMS` 加 `"routing.world_mode"`；（admin_only_commands 已有形状校验，值格式无关） |
| `presentation/locale.py` | 各组/子动作用法提示（含缺必填参数用法）、单模式 link 拒绝提示、单模式访问告警、rank 变体(today/total/level)文案 |
| `tests/**` | command_names 重构（`PAL_REGISTERED`(11) 注册锚定 + 分发表 getattr 锚定）+ `_NON_LOCKABLE` 双源全等 + admin_denied 逐可锁子动作 fail-open 测 + admin_only 未知锁告警测 + rank total 隐私/strict 测 + 冒烟改分级 + frontend_pal_commands 完整路径锚点 + readme 锚点 |
| 前端 `schema.ts`/`chapters.ts`/`SettingsPanel.vue` | `routing` 章加 `world_mode` enum 字段（嵌 routing，非独立总设置）；`PAL_COMMANDS`/chip 值改完整路径 |
| docs / README / 版本四源 | 分级命令文档重写 + flat→full-path 锁迁移映射表 + 单模式访问告警粗体 + v0.9.5 |

## 10. 错误处理

- 未知 group：AstrBot 未注册的 `/pal xxx` 由框架处理（现状），无需特殊。
- 未知子动作：`/pal world foo` → 回该组用法（列出合法子动作 + 示例）。
- **子动作合法但必填参数缺失（复核视角1 m9）**：`/pal player info`（缺名字）/`/pal server kick`（缺目标）→ 回该**子动作**用法（如 `用法：/pal player info <玩家名>`）；相应 locale 用法文案从扁平（`/pal player <名>`）改分级。
- 裸 group：回该组迷你帮助（复用 format_help 谓词，功能门 + 角色过滤）。
- ArgError（多 @override）：回现有 ArgError 兜底文案。
- 单模式 `/pal link *`：handler 顶部（先于任何 DB 写）回「单世界模式无需选择服务器」提示。
- 变体非法（`/pal rank foo`）：回 rank 用法（today/total/level）。

## 11. 测试策略

- **解析**：分级解析（剥两级 + 子动作 + 参数 + @override + 空白折叠 + ArgError）。
- **组分发 + 门控（fail-open 防回归，红线）**：每组各子动作路由到正确实现 + 施加正确门；**逐可锁子动作 `admin_denied` 强制测**（锁 `player info`，非管理员调用回 `admin_required` 且不触达底层）；写子动作逐一锚定「走 admin_write + 正确功能组」（防某写动作漏门=无鉴权关服）；未知子动作/缺必填参数回用法；裸 group 迷你帮助角色过滤（guest 发 `/pal server` **不得**出现 kick/ban/stop；guilds_bases 关时 `/pal guild` 不列子动作）。
- **锁迁移**：给旧扁平锁值 `["player"]` 断言产生 **unknown-lock 告警**而非静默失锁。
- **模式基础**：multi 现状回归不变；single→resolve 唯一服务器（忽略 override/绑定，分支在顶端早于私聊早退）、_authorized 放宽读、**写仍管理员门**、single+restricted 产生访问告警、`/pal link *` 顶部拒（先于 DB 写）、0/>1 台边界。
- **rank 变体**：today/total/level 三 mode；total 留存期内聚合 + **复用名字级收敛剔除**（隐藏一个有历史时长玩家断言其整组名字消失）+ strict 双砍 today/total；非法 mode 回用法。
- **锚定**：`PAL_REGISTERED`(11) == `@pal.command` 注册；分发表 getattr introspection（方法名可解析）；`_NON_LOCKABLE` 双源全等；前端 PAL_COMMANDS 完整路径跨端锚点；readme 命令锚点；命名空间冒烟跑分级到深分支（注：不覆盖 AstrBot 真实路由层，同现状）。
- **help**：分级视图 + 角色过滤 + 裸 group 迷你帮助 + 未开放功能提示。

## 12. 版本

`v0.9.0 → v0.9.5`，四源同步（metadata.yaml / main.py @register / `__init__.py` / README 徽章）。Phase 2 同为 v0.9.5（不再抬版本）。

## 13. 风险与开放项

- **破坏性迁移**：老用户所有命令改打法 + `admin_only_commands` 锁值格式变——help/docs 清晰引导；发布说明列 flat→full-path 映射表并强调「不迁移=失锁」（未知锁条目已有告警兜底，见 §7）。
- **单模式 × restricted（隐私红线，已加告警）**：单模式 `_authorized` 放宽使读命令对所有上下文（含私聊/未授权群）开放（写仍管理员门，安全不回退）——须启动/保存告警 + 文档粗体，让其为有意识选择。单模式私聊 admin 写 = 今日 OPEN 行为，非新增提权面。
- **门控落点重构（三视角互证 Blocker，已规格化 §4.1）**：`admin_denied` 下沉 Commands 按完整路径 + `_gated` 改分发循环 per-动作 + busy/inflight 门闩保留——实现须逐子动作测 fail-open。
- **命令串锚点全面变动**：`PAL_REGISTERED`(11)/`PAL_COMMAND_STRINGS`(完整路径)/`_NON_LOCKABLE` 双源/前端 PAL_COMMANDS/frontend_pal_commands_test/SettingsPanel chip/readme/多处硬编码扁平样例全要改——迁移清单须完整（§8/§9）。
- **裸 group vs 变体默认的一致性**：裸 group=帮助（不执行），但 `rank`(扁平带变体) 裸=today（执行）——规则不同，文档说明避免困惑。
- **`total` 语义**：非「全时段」，实为「留存期内（session_days）累计」——文案须准确。
- **Phase 2 依赖**：命令树位置与功能门此轮不对齐（`world` 组含 core+events+report 三门）——Phase 2 权限「按组调」须解决命令树↔功能门映射，本轮先并存。
