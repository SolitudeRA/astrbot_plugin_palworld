# 分级命令架构 + 模式基础 + 命令变体设计（v0.9.5 Phase 1）

> 状态：设计定稿待对抗复核 · 目标版本 **v0.9.5** · 这是 v0.9.5 的 **Phase 1**（命令体系）；Phase 2（分级感知权限 + 设置页权限章）另立 spec，同为 v0.9.5。

## 1. 定位与目标

把扁平的 26 个 `/pal <X>` 命令重构为**分级命令架构** `/pal <组> <动作>`，让命令更好记、更不易误触（尤其高危管理类）。同时为将来的**单/多世界运行模式**打地基（本轮只做基础，完整单模式 UX 留 Phase 3）。并引入**命令变体机制**（以 `rank today|total|level` 打样）。

**破坏性变更**：全面分级、**不保留旧扁平命令**（插件 0.9.x 未到 1.0，可接受）。help/文档随之重写引导迁移。

## 2. 范围

**In（Phase 1）**：
- 命令树重构为分级 `/pal <组> <动作>`（扁平自解析首词，非 AstrBot 原生嵌套组）。
- 少量高频命令保留一级：`rank` / `online` / `me` + 元命令 `help` / `whoami` / `confirm`。
- 模式基础：`world_mode`(single/multi) 配置 + `RoutingService.resolve` 模式感知 + `/pal link` 组单模式隐藏。
- 命令变体机制：`rank [today|total|level]`（`total` = 新增全时段时长榜查询）。
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

### 3.6 `/pal link` —— 服务器选择/绑定（仅多世界模式；单模式整组隐藏）
| 子命令 | 说明 | 门 |
|---|---|---|
| `list` | 服务器列表与本群绑定状态 | —（群内可见） |
| `add <名称>` | 本群绑定该服务器 | 管理员 |
| `remove <名称>` | 撤销本群绑定 | 管理员 |

### 3.7 命令树通则
- **子动作一律显式关键词**，杜绝「裸名字=某操作」歧义（不做 `/pal link <名>` 直接绑定）。
- **裸 group（`/pal world`/`/pal guild`/`/pal player`/`/pal server`/`/pal link`）= 该组迷你帮助**（列出可用子动作 + 一句说明），只提示不执行；按功能门 + 角色过滤（如 `/pal server` 裸帮助仅管理员见管理动作）。
- **命令树位置独立于功能门**：`today` 仍受 `report`、`rank` 仍受 `players`——命令换打法，功能门语义不变。
- 未知子动作（`/pal world foo`）→ 回该组用法提示（列出合法子动作）。

## 4. 路由与解析

推广现有「一个 group handler + Commands 层自解析首词分发」模式（`/pal server add/remove` 即此形）。

- **main.py 注册**：每个 group 一个 `@pal.command("<组>")`（world/guild/player/server/link）+ 每个扁平命令一个 `@pal.command("<名>")`（rank/online/me/help/whoami/confirm）。共 **11 个 `@pal.command`**（5 组 + 6 扁平），取代现 26 个扁平注册。
- **解析**：扩展 `server_arg` —— 新增「剥 `/pal <组>` 前缀 + 取子动作首词 + 剩余为参数（尾部 @override 仍支持，多模式）」。子动作解析要保留现有 ArgError（多 @token）与空白折叠语义。
- **分发**：Commands 层新增**组分发**——`Commands.<组>(umo, message_str, is_group, sender_id, is_admin)` 解析子动作、查分发表、施加该动作的功能门 + 管理员门（复用现有 `_gated` 逻辑与 `admin_write` 中央写门），路由到对应实现方法。`server` 组的写动作继续走 `admin_write`（门序 admin 先于 feature 不变）；查询组走 `_gated`。
- **子动作分发表**：以数据结构描述 `{组: {动作: (实现方法, 功能门, 是否管理员)}}`，作为路由 + help 生成 + 锚定测试的**单一真相源**（取代/重构现 `command_registry.COMMANDS`/`HELP_LINE`）。

## 5. 模式基础（Phase 1 打地基）

- **配置**：新增顶层 `world_mode: "single" | "multi"`（默认 **"multi"** 保持现状）。config.py + `_conf_schema.json` + 前端 schema 同步。
- **`RoutingService.resolve(umo, override, is_group)` 模式感知**：
  - `multi`（现状不变）：显式 @override → 群绑定 → 默认 → 唯一就绪 → 提示。
  - `single`：**恒解析到唯一配置服务器**，忽略 @override 与群绑定；`_authorized` 在单模式放宽为 true（单世界=共享那一台，读命令全员可用）。**写命令仍受管理员硬门**（与路由授权独立，安全不回退）。
  - 边界：单模式下配置了 0 台 → 明确「未配置服务器」错误；配置 >1 台 → 用列表首台 + 记一次告警（完整多台→单切换校验属 Phase 3）。
- **命令面**：单模式下 `/pal link` 整组隐藏——handler 回「单世界模式无需选择服务器」提示；help 省略该组；`@server` 尾缀在单模式被忽略（文档说明）。
- **访问模式**：单模式 `_authorized` 放宽如上；`access_mode`(open/restricted) 保留但其「restricted 需群绑定」在单模式无意义（无 link）——Phase 1 即以「单模式=那台对所有上下文可读、写仍管理员」落地，完整访问模型细化留 Phase 3。

## 6. 命令变体机制

以 `rank` 打样：`/pal rank [today|total|level]`，首词为 mode（缺省 today）。
- `today`（默认）：今日时长榜（现状）。
- `total`：**全时段累计时长榜**（新增查询）——聚合 `player_sessions` 全部时长/玩家；受同一排除名单/隐私过滤；strict 隐私模式砍时长榜（与 today 一致）。
- `level`：等级榜（现状，含离线全体）。
- **QueryService.rank 加 mode 参数**；`total` 走新聚合查询。`me` 的 `[hide|show]` 沿用现有子词解析（同属变体机制的既有形态）。
- 变体是「命令后缀子词」，与分级子动作解析同套机制；未来加变体 = 给某命令加 mode 分支。

## 7. 迁移（无向后兼容）

- 删除全部旧扁平命令注册（status/world/rules/guilds/guild/bases/base/events/today/player/bind/unbind/server/announce/save/kick/unban/ban/shutdown/stop 等），改为分级。
- `rank`/`online`/`me`/`whoami`/`help`/`confirm` 保留为扁平（`rank`/`me` 带变体）。
- help 全面重写为分级视图（组 + 子动作，按功能门 + 角色过滤）。
- docs/commands.md、docs/configuration.md、README、readme_test 锚点随分级重写（命令串锚点从 `/pal status` 等改为 `/pal world status` 等；readme_test 中文/命令锚点同步）。

## 8. 命令真相源与锚定

**两种粒度须分清（关键，防歧义）**：
- **注册身份**（`@pal.command` / command_names 锚定）= **11 个首词**（5 组 + 6 扁平）。AstrBot 只认首词；子动作是 Commands 层自解析的。
- **门控/help 身份**（子动作分发表 / `admin_only_commands` 锁 / `LOCKABLE` / help 行）= **完整路径**（`world status`、`server kick`、`rank`、`me`）。功能门/管理员门/可锁性都按完整路径判定。

- **重构 `command_registry`**：`COMMANDS`（含子动作）/`HELP_LINE`/`PAL_COMMAND_STRINGS`（=完整路径集）/`LOCKABLE_COMMANDS`/`_NON_LOCKABLE` 全面改造为分级模型。`admin_only_commands` 配置值格式随之从扁平（`player`）变完整路径（`world status`、`rank`）——**破坏性、可接受**（无向后兼容），Phase 2 会把它重做成树模型。`_NON_LOCKABLE` = server 管理各动作路径 + link 各动作路径 + 元命令。
- **`command_names_test` 重构**：现锚定 `@pal.command("X")` == `PAL_COMMAND_STRINGS`（26）——改为锚定 **group 首词 + 扁平命令**（11 个 `@pal.command`）== 注册；另加**子动作分发表**锚定（每组的子动作集 == 该组 handler 实际能分发的动作）。
- **不可锁集 / 跨端锚定**：`_NON_LOCKABLE`（server 管理 + link + 元命令）、`LOCKABLE_COMMANDS`、前端 `PAL_COMMANDS`（Phase 2 才重做权限 UI，Phase 1 保持前端命令锁 chip 与后端 LOCKABLE 跨端锚定**在新命令串模型下仍全等**）。**注意**：命令串从扁平变分级后，前端 `PAL_COMMANDS`/`frontend_pal_commands_test` 的锚定值须同步更新，否则跨端测试红。
- 命名空间加载冒烟（`namespace_runtime_smoke_test`）改为跑分级命令（group handler + 子动作），命令数/calls 清单更新。

## 9. 分层实现映射

| 层 | 改动 |
|---|---|
| `config.py` + `_conf_schema.json` + 前端 schema | 新增 `world_mode`(single/multi) |
| `application/routing_service.py` | `resolve` 模式感知（single→唯一服务器 + 放宽 _authorized；写仍管理员门在别处） |
| `application/query_service.py` | `rank` 加 mode 参数 + `total` 全时段聚合查询 |
| `presentation/server_arg.py` | 扩展为分级解析（剥 `/pal <组>` + 取子动作 + 剩余参数 + 尾 @override 保留） |
| `presentation/command_registry.py` | 分级真相源重构（子动作分发表 + help + 锚定源） |
| `presentation/commands.py` | 组分发方法（world/guild/player/server/link）+ 子动作路由 + 门施加；rank mode 分支 |
| `presentation/formatters.py` | help 分级视图（组 + 子动作，功能门 + 角色过滤，含裸 group 迷你帮助） |
| `presentation/locale.py` | 各组/子动作用法提示、单模式 link 隐藏提示、rank 变体文案 |
| `main.py` | 11 个 `@pal.command`（5 组 + 6 扁平）取代 26 扁平；改注册描述（命令数/分级） |
| `tests/**` | command_names 重构 + 分发表锚定 + 冒烟改分级 + frontend_pal_commands 锚点更新 + readme 锚点 |
| 前端 `schema.ts`/`chapters.ts` | `world_mode` 开关（总设置）；PAL_COMMANDS 命令串更新 |
| docs / README / 版本四源 | 分级命令文档重写 + v0.9.5 |

## 10. 错误处理

- 未知 group：AstrBot 未注册的 `/pal xxx` 由框架处理（现状），无需特殊。
- 未知子动作：`/pal world foo` → 回该组用法（列出合法子动作 + 示例）。
- 裸 group：回该组迷你帮助（功能门 + 角色过滤）。
- ArgError（多 @override）：回现有 ArgError 兜底文案。
- 单模式 `/pal link *`：回「单世界模式无需选择服务器」提示。
- 变体非法（`/pal rank foo`）：回 rank 用法（today/total/level）。

## 11. 测试策略

- **解析**：分级解析（剥两级 + 子动作 + 参数 + @override + 空白折叠 + ArgError）。
- **组分发**：每组各子动作路由到正确实现 + 施加正确门（功能门/管理员）；未知子动作回用法；裸 group 回迷你帮助（角色过滤：guest 不见管理动作）。
- **模式基础**：multi 现状回归不变；single→resolve 唯一服务器（忽略 override/绑定）、_authorized 放宽读、写仍管理员门、link 隐藏、0/>1 台边界。
- **rank 变体**：today/total/level 三 mode；total 全时段聚合正确 + 隐私过滤 + strict 砍时长；非法 mode 回用法。
- **锚定**：11 `@pal.command` == 真相源；子动作分发表 == 各组实际可分发动作；前端 PAL_COMMANDS 跨端锚点（新命令串）；readme 命令锚点；命名空间冒烟跑分级到深分支。
- **help**：分级视图 + 角色过滤 + 裸 group 迷你帮助 + 未开放功能提示。

## 12. 版本

`v0.9.0 → v0.9.5`，四源同步（metadata.yaml / main.py @register / `__init__.py` / README 徽章）。Phase 2 同为 v0.9.5（不再抬版本）。

## 13. 风险与开放项

- **破坏性迁移**：老用户所有命令改打法——help/docs 须清晰引导；发布说明强调。
- **单模式 _authorized 放宽**：单模式读命令对所有上下文开放（写仍管理员门）——须对抗复核确认这是可接受的单世界语义、无写侧回退。
- **命令串锚点全面变动**：扁平→分级使前端 PAL_COMMANDS/frontend_pal_commands_test、readme 锚点、command_names 全部要改，漏一处即红——迁移清单须完整。
- **裸 group vs 变体默认的一致性**：裸 group=帮助（不执行），但 `rank`(扁平带变体) 裸=today（执行）——二者规则不同（组 vs 带默认变体的扁平命令），须文档说明避免用户困惑。
- **Phase 2 依赖**：命令树位置与功能门此轮不对齐（`world` 组含 core+events+report 三门）——Phase 2 权限「按组调」时须解决命令树↔功能门映射，本轮先并存。
