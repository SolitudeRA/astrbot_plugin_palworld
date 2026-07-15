# 完整指令与功能开关

自 v0.9.5 起指令改为**分级结构**:`/pal <组> <动作> [参数]`。5 个命令组(`world`/`guild`/`player`/`server`/`link`)+ 7 个扁平命令(`rank`/`online`/`me`/`help`/`whoami`/`whereami`/`confirm`)。所有指令以 `/pal` 前缀触发、返回纯文本。查询指令只读;**服务器管控为受控写**(默认全关、仅授权管理员、全程审计,见[服务器管控](#服务器管控受控写))。带「功能组」的指令仅在对应组开启时可用(见下方矩阵);`core` 组指令恒可用。

> **裸组 = 迷你帮助**:只发组名(如 `/pal world`、`/pal server`)返回该组可用子动作的迷你帮助(按当前功能开关与你的角色过滤——访客不会看到管控写子动作)。

## 首次使用(首次设置闸)

**全新安装后须先在插件设置页完成一次运行模式选择并确认**(选单世界 / 多世界),命令才全部开放。未确认前(`routing.setup_confirmed` 非 `true`),除下列元命令外的所有 `/pal` 命令一律回引导语(「🔧 帕鲁世界终端尚未完成首次设置。请打开插件设置页,选择运行模式(单服务器 / 多服务器)并确认后即可使用。」):

- `/pal help` —— 分级帮助
- `/pal whoami` —— 查看我的账号标识
- `/pal whereami` —— 查看当前群标识

> 设置页在未确认时以**首次引导屏**取代正常配置章节;选模式并确认即写入 `world_mode` + `routing.setup_confirmed=true` 并保存,命令闸随即解除、转入正常设置页。模式主开关仍在 AstrBot 齿轮配置里(见[运行模式](#运行模式单世界--多世界)与[配置项详解 · routing](configuration.md#routing访问控制))。

## 指令详表

### `world` 组 —— 世界观测(查询)

| 指令 | 参数 | 功能组 | 说明 |
|------|------|--------|------|
| `/pal world status` | — | `core` | 世界状态(在线数、FPS 流畅度、世界天数等) |
| `/pal world overview` | — | `core` | 世界概览 |
| `/pal world rules` | — | `core` | 世界规则(倍率等) |
| `/pal world today` | — | `report` | 今日日报 / 在线统计 |
| `/pal world events` | — | `events` | 世界事件记录 |

### `guild` 组 —— 公会与据点(查询)

| 指令 | 参数 | 功能组 | 说明 |
|------|------|--------|------|
| `/pal guild list` | — | `guilds_bases` | 公会列表 |
| `/pal guild info` | `<名称>` | `guilds_bases` | 公会详情 |
| `/pal guild bases` | — | `guilds_bases` | 据点列表 |
| `/pal guild base` | `<名称\|#序号>` | `guilds_bases` | 据点详情 |

### `player` 组 —— 玩家档案(查询)

| 指令 | 参数 | 功能组 | 说明 |
|------|------|--------|------|
| `/pal player info` | `<玩家名>` | `players` | 逐个玩家查询(等级、时长、据点等) |
| `/pal player bind` | `<玩家名>` | `players` | 绑定平台账号 ↔ 玩家(供 `/pal me` 识别本人) |
| `/pal player unbind` | — | `players` | 解除我的玩家绑定(与 `bind` 对称) |

### 扁平命令 —— 常用查询与元命令

| 指令 | 参数 | 功能组 | 权限 / 场景 | 说明 |
|------|------|--------|-------------|------|
| `/pal rank` | `[today\|total\|level]` | `players` | 所有人 | 排行榜变体:`today` 今日在线时长榜(缺省)、`total` 留存期内累计在线时长榜、`level` 等级榜 |
| `/pal online` | — | `core` | 所有人 | 当前在线玩家名单 |
| `/pal me` | `[hide\|show]` | `players` | 所有人 | 我的档案;`hide`/`show` 自助从排行/查询中隐藏或恢复 |
| `/pal whoami` | — | `core` | 所有人(**建议私聊**) | 查看我的账号标识 `平台:账号`(如 `aiocqhttp:12345`);报给超管加入受托名单用 |
| `/pal whereami` | — | `core` | 所有人 | 查看**当前群标识**(UMO,如 `aiocqhttp:GroupMessage:123456`);单世界 restricted 下报给管理员加入授权群名单用。两模式恒可用、只回显本会话标识、不接受任何目标参数 |
| `/pal help` | — | `core` | 所有人 | 分级帮助(按当前启用的组 + 你的角色过滤指令) |
| `/pal confirm` | — | `core` | **仅授权管理员** | 确认执行上一条待确认的高危操作;无待确认操作时回「无待确认操作或已超时」 |

> **`rank` 变体与隐私**:`today` / `total` 均为**在线时长**榜,`strict` 隐私模式下**两者一并停用**(回提示);`total` 只累计**留存期内**(非全时段)且同样尊重排除名单与 `/pal me hide`——被隐藏玩家的整组名字从榜单消失,不泄露其存在。`level` 为等级榜。

### `server` 组 —— 服务器管控(受控写)

见下节[服务器管控](#服务器管控受控写)。命令:`/pal server announce`、`/pal server save`、`/pal server kick`、`/pal server unban`、`/pal server ban`、`/pal server shutdown`、`/pal server stop`(均**仅授权管理员**)。

### `link` 组 —— 服务器选择与群授权(仅多世界模式)

见下节[多世界模式与群授权](#多世界模式与群授权)。命令:`/pal link list`、`/pal link add <名称>`、`/pal link remove <名称>`。**单世界模式下 `link` 组隐藏且运行时拒绝**(无需选择服务器)。

任意查询指令末尾可加 **`@<服务器名>`** 单次指定目标服务器(详见下文「多世界模式与群授权」)。

> **写命令的 `@server` 词序**:服务器覆盖只识别命令**末尾**的 `@<服务器名>`,如 `/pal server kick Alice 作弊 @beta`。`announce` 消息、`kick`/`ban` 理由是自由文本整串,若**恰以 `@词` 结尾**(如 `/pal server announce 快来 @discord`)会被误当服务器覆盖——自由文本请勿以 `@词` 收尾,或显式把 `@server` 放最末。连续空格/换行会被折叠为单空格,不保证逐字保留。

## 功能开关 → 可用指令矩阵

功能按组可插拔(v0.9.6 起由设置页「权限」章的命令树控制,落盘为 `command_permissions`;详见[配置项详解 · 命令树权限模型](configuration.md#features功能开关))。**关闭某命令/组:其指令回「未开放」、`/pal help` 里不再列出**;`guild` 组关闭时还会停采 `/game-data` 端点(观测只读端点恒采集)。代码保留,改开即恢复。

| 功能组 | 默认 | 对应指令(完整路径) | 开启时 | 关闭时指令行为 |
|--------|------|----------|--------|----------------|
| `core`(不可关闭) | 恒开 | `world status` `world overview` `world rules` `online` `server`(裸) `link`(裸) `whoami` `whereami` `help` `confirm` | ✅ 可用 | —(无法关闭) |
| `report` | 开 | `world today` | ✅ 可用 | ❌ 回「未开放」、help 隐藏 |
| `events` | 开 | `world events` | ✅ 可用(并记录世界事件) | ❌ 回「未开放」、不生成事件 |
| `guilds_bases` | **关** | `guild list` `guild info` `guild bases` `guild base` | ✅ 可用 | ❌ 回「未开放」、help 隐藏 |
| `players` | **关** | `player info` `player bind` `player unbind` `rank` `me` | ✅ 可用 | ❌ 回「未开放」、help 隐藏 |
| `server_admin_basic` | **关** | `server announce` `server save` `server kick` `server unban` | ✅ 仅授权管理员可用 | ❌ 管理员回「未开放」、help 隐藏;非管理员一律「需要管理员权限」 |
| `server_admin_danger` | **关** | `server ban` `server shutdown` `server stop` | ✅ 仅授权管理员可用(可选二次确认) | ❌ 管理员回「未开放」、help 隐藏;非管理员一律「需要管理员权限」 |

> `server_admin_basic` / `server_admin_danger` 默认关闭:属**受控写**,详见下节[服务器管控](#服务器管控受控写)。非管理员对写命令**一律**回「需要管理员权限」(与组开关状态无关,避免据回执反推危险组是否开启)。

> `players` 默认关闭:玩家个体查询含隐私考量。时长榜仅统计**今日/留存期内**在线时长、等级榜含离线全体;`strict` 隐私模式下更保守(时长榜停用、玩家档案隐藏坐标等)。支持管理员排除名单与玩家自助 `/pal me hide`——被排除或隐藏者不出现在排行/查询中,且不泄露其存在。

> `guilds_bases` 默认关闭:依赖服务器开放 `/game-data`,而 Palworld 1.0 专用服务器上游未开放 `PalGameDataBridge`,故公会/据点/PalBox 整组默认停用,详见[配置项详解](configuration.md#features功能开关)。

## 运行模式:单世界 / 多世界

`routing.world_mode` 决定服务器路由方式,**默认 `single` 单世界**。切换入口是插件齿轮配置里的模式主开关(自定义设置页无模式开关,只按当前模式呈现对应配置形态)。无存量用户,改默认直接生效、**无迁移**。

- **`single` 单世界(默认)**:所有操作对应**唯一**服务器(取第一台就绪服务器)。`link` 组**隐藏且运行时拒绝**(无需选择),`@server` 覆盖与群绑定被忽略。读授权见下方 restricted 说明。
- **`multi` 多世界**:一个插件监测多台服务器,按群授权、按群切换活动服务器。`link` 组用于选择/授权;查询可用 `@<服务器名>` 单次覆盖。读授权走 `/pal link` 的群授权(DB 名单)。

### 单世界的读授权(restricted)与写命令

- **读命令**:`access_mode=restricted` 时按**授权群名单**(顶层配置 `single_allowed_groups`)放行——**仅名单内会话(群/私聊)**可查询唯一服务器,名单外一律拒(回文案指向 `/pal whereami` + 设置页名单)。`access_mode=open` 则对所有会话开放,忽略名单。
- **配置名单**:在群里发 `/pal whereami` 取本会话标识(UMO),交管理员在设置页「连接」章的**授权群名单**里添加(每行 `umo` + 可选 `note`)。私聊亦按同一名单判定。
- **⚠️ 空名单 = 全群不可读**:`single` + `restricted` + 空名单是安全默认(fail-closed),**当前无人可查询**——插件启动日志会告警提示补名单。全新装机是此状态,需管理员用 `/pal whereami` 完成一次授权引导。
- **写命令不受读名单约束**:`server` 组 7 条写命令**不查授权群名单**,仅受**管理员硬门**(`permission_admins` 受托名单)把守——授权管理员可从任意群/私聊管理唯一服务器(与模式无关)。

### 在设置页切换模式（single ↔ multi）

除首次设置外,运行模式可在插件设置页「连接」章的**切换控件**随时更改(齿轮裸切仍容忍,但无引导、无迁移):

- **切换按钮**按当前模式与就绪服务器数派发:
  - 单世界 → 多世界:弹**确认对话框**,列出「单世界授权群名单」中的群,默认全部勾选迁移(迁移后绑定到唯一就绪服务器)。
  - 多世界 → 单世界(1 台就绪):弹**确认对话框**,列出各群的多世界绑定,标注「已有保留台权限」(默认勾选)/「将获新权」(默认不勾),可手动调整。
  - 多世界 → 单世界(多台就绪):进入**转移向导**——① 选保留哪台 → ② 勾选迁移哪些群 → ③ 其余台「保留 / 永久删除(含全部历史数据,不可恢复)」→ ④ 摘要 + 强确认。删除其余台时须勾选「我了解此操作不可恢复」方可确认。
- 授权采用 **move 语义**:迁移到目标介质后清空源介质,切回原模式不会复活旧授权;未勾选的群切换后需重新授权(单世界填入授权群名单,多世界用 `/pal link` 绑定)。
- **未保存的更改**会禁用切换入口——请先保存再切换(转移只读最后保存的配置)。
- 切换失败(如群数超上限、预绑定失败、重载回滚)**不改变模式**、仅提示错误;成功但清理未尽时会切换并提示人工核查。

### 残留数据清理（孤儿服务器）

从配置中移除服务器(或多台切单台时选择删除)后,若数据库仍残留其历史数据,「连接」章底部会出现**残留数据清理**小节,列出这些孤儿服务器。勾选「我了解此操作不可恢复」后点击「清理残留数据」即可清除。清理为服务端现场重算孤儿集执行(不信任前端列表),仅删除确实已不在配置中的服务器数据,不会误删在册服务器。

## 多世界模式与群授权

> 以下 `link` 组仅在 **`world_mode=multi`** 下可用。

- `/pal link list`:列出所有服务器与本群授权/活动状态。
- `/pal link add <名称>`(管理员,仅群聊):授权本群使用该服务器并设为活动服务器。
- `/pal link remove <名称>`(管理员,仅群聊):撤销本群对该服务器的授权。
- **@server 尾缀**:任意查询指令可在末尾加 `@<服务器名>` 单次指定目标服务器,如 `/pal world status @alpha`、`/pal guild info 晨曦联盟 @beta`(服务器名不含空格,公会/据点名可含空格)。

## 权限管理

本插件用**两层权限模型**,与 AstrBot 全局管理员(`admins_id`)相互独立——`_is_admin` **只认**插件自己的受托名单,不认 AstrBot 的 `admins_id`,也不看 `event.role`。

- **受托名单(`permission_admins`)**:超管在设置页「权限」章逐条维护(每行含 `id` = `平台:账号`,和可选 `note` 备注)。**只有**名单内的账号被视为本插件的管理员。玩家在群里(建议私聊)发 `/pal whoami` 得到自己的 `平台:账号`,报给超管加入。
- **内置管理门**:`server` 组全部写命令、`/pal link add`、`/pal link remove`、`/pal confirm` 恒需管理员,由受托名单判定(名单外成员执行会被拒)。
- **命令门(`admin_only_commands`)**:超管可把任意查询命令锁成仅管理员可用,填**完整命令路径**(如 `player info`、`world status`、`rank`)。被锁命令对名单外成员回「该命令需要管理员权限。」。**不可锁集**(填入会被忽略)= `server` 组各写命令(`server announce` … `server stop`)+ `link` 组各命令(`link list`/`link add`/`link remove`)+ 元命令 `help`/`whoami`/`confirm`——这些由功能门 + 管理员门双闸把守,绝不可再被锁。

### ⚠️ admin_only_commands 锁迁移(v0.9.5 破坏性)

分级后 `admin_only_commands` 的值从**扁平命令**(`player`)改为**完整路径**(`player info`)。**旧扁平值升级后不匹配新路径 = 锁静默失效(fail-open)**,插件会在启动日志中对每条无法识别的锁条目告警(unknown-lock),但**不会**替你猜测迁移。请照下表逐条改写:

| 旧扁平锁值 | 新完整路径 | 旧扁平锁值 | 新完整路径 |
|---|---|---|---|
| `status` | `world status` | `guilds` | `guild list` |
| `world` | `world overview` | `guild` | `guild info` |
| `rules` | `world rules` | `bases` | `guild bases` |
| `today` | `world today` | `base` | `guild base` |
| `events` | `world events` | `player` | `player info` |
| `rank` | `rank`(不变) | `bind` | `player bind` |
| `online` | `online`(不变) | `unbind` | `player unbind` |
| `me` | `me`(不变) | — | — |

> **失锁风险**:未迁移的旧值(如仍写 `player`)不再匹配任何命令 → 该锁**不生效**,原本仅管理员的命令**对所有人开放**。请在升级后立即核对 `admin_only_commands`,并留意启动日志的 unknown-lock 告警。`server`/`link` 写命令**不可锁**(始终受管理员门把守),旧配置里若锁了它们(如 `kick`),升级后同样报 unknown-lock,可直接删除该条。

> **安全告知**:受托名单是**全局**的——加入者在其所在的**每个群**都拥有管理员权(含对任意群执行 `link add`/`link remove` 与 `server` 组写命令)。多适配器实例 / 多群共用同一 bot 时共享同一**命名空间**,请谨慎授权。`id`/`note` 以**明文**落盘到 `data/config/`,`note` 勿填真实姓名、联系方式等 PII。详见[配置项详解 · 权限](configuration.md#permissions权限管理)。

## 服务器管控(受控写)

插件从**只读监测**跨入**受控写管控**:`server` 组提供 7 条对官方 REST 写端点的管理命令(`announce`/`save`/`kick`/`unban`/`ban`/`shutdown`/`stop`)+ `/pal confirm` 二次确认。承诺从「绝不写」转为「受控写:默认全关、仅授权管理员、全程审计」。

| 指令 | 参数 | 功能组 | 权限 / 场景 | 说明 |
|------|------|--------|-------------|------|
| `/pal server announce` | `<消息>` | `server_admin_basic` | **仅授权管理员** | 全服广播(消息为剩余整串) |
| `/pal server save` | — | `server_admin_basic` | **仅授权管理员** | 保存世界存档 |
| `/pal server kick` | `<玩家名\|userid> [理由]` | `server_admin_basic` | **仅授权管理员** | 踢出玩家(可重连);目标可传角色名(实时解析)或直接传 userid |
| `/pal server unban` | `<userid>` | `server_admin_basic` | **仅授权管理员** | 解封玩家 |
| `/pal server ban` | `<玩家名\|userid> [理由]` | `server_admin_danger` | **仅授权管理员** · 高危 | 封禁玩家(可选二次确认) |
| `/pal server shutdown` | `<秒> [公告]` | `server_admin_danger` | **仅授权管理员** · 高危 | 倒计时关服;秒数为正整数(1–86400),公告为剩余整串(可选二次确认) |
| `/pal server stop` | — | `server_admin_danger` | **仅授权管理员** · 高危 | 立即停服,**不存档(丢档风险)**(可选二次确认) |

### 三层安全模型

写命令经**单一中央门**把守,按序判定(任一不过即拦截):

1. **管理员硬门(最先)**:非受托名单成员**一律**回「需要管理员权限」——与功能组开关状态无关,不泄露危险组是否开启。硬编码仅认 `permission_admins` 名单,空名单则无人可执行(fail-closed)。
2. **功能组门**:命令按组归属——`server_admin_basic` = {announce, save, kick, unban}、`server_admin_danger` = {ban, shutdown, stop},**默认全关**。运营者可只开 basic 不暴露 danger。
3. **服务器授权门**:复用只读侧授权(RESTRICTED 下私聊拒、群授权名单、`@server` 覆盖)。**注意 OPEN 访问模式的爆炸半径**(见下)。

### 二次确认(仅 danger 组,可选)

配置 `require_confirmation`(默认关)。开启后 `ban`/`shutdown`/`stop` 首发**不执行**,回预览(含目标角色名 + userid 尾段 + 摘要),须在 `confirmation_timeout` 秒(默认 30)内回 `/pal confirm` 确认。确认时**重新复检**权限/组状态/服务器授权,任一变更则丢弃待确认操作。每管理员同时只保留一条待确认操作,新的覆盖旧的;配置热重载会清空所有待确认操作。`basic` 组**永不**需确认。

### 目标玩家解析(kick / ban)

目标可传 **userid**(如 `steam_<17位数字>`,直接使用)或**角色名**(执行时实时 `GET /players` 按名精确匹配求 userid):唯一命中即用;同名多个回候选列表提示改用精确 userid;零命中回「未找到在线玩家」。该实时解析**绕过隐私过滤**读取真 userid(写操作必需),对服务器运营者合理——**不影响** `/pal me hide` 对同侪玩家的存在性保护。明文 userid 用完即弃、不落库、不进日志。

### 审计(落库 + 前端只读查看)

每次写操作(无论成败)落一行审计到 `admin_audit` 表:时间、管理员标识、动作、服务器、目标(角色名 + userid **哈希**,不存明文)、结果/错误类别。审计可在设置页「审计」章只读查看(最近 N 条,倒序)。留存受 `audit_retention_days`(默认 180 天)限制,随清理链自动删旧行。审计表含明文 `admin_id`/`target_name`,属受控 PII。

### ⚠️ 安全告知(务必阅读)

- **OPEN 访问模式爆炸半径**:`access_mode=open` 下 `_authorized` 恒真,写命令**不再受群授权名单约束**——任一授权管理员可从任意群/私聊对任意就绪服务器 `server stop`/`server ban`。强烈劝阻「OPEN + `server_admin_danger` 同开」;多群共享同一 bot 时尤须谨慎。
- **`server stop` 丢档**:`/pal server stop` 强制停服**不保存存档**,可能丢失未存进度。需要保存请先 `/pal server save`,或改用 `/pal server shutdown`(倒计时期间正常保存)。
- **冒充/归属**:Palworld REST 无操作者身份校验,审计记录的是「哪个受托管理员通过 bot 发起」,非游戏内身份。
- **名字解析依赖 /players**:目标服务器不可达时无法按名解析,回明确错误,可直传 userid 兜底。

## 降级行为

API 不可达时显示「当前无法获取世界数据,最后成功更新 N 分钟前」,**绝不**臆断「服务器已关机」。部分端点失败时降级相关模块,其余照常。
