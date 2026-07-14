# 完整指令与功能开关

所有指令以 `/pal` 前缀触发、返回纯文本。查询指令只读;**服务器管控为受控写**(默认全关、仅授权管理员、全程审计,见[服务器管控](#服务器管控受控写))。带「功能组」的指令仅在对应组开启时可用(见下方矩阵);`core` 组指令恒可用。

## 指令详表

| 指令 | 参数 | 功能组 | 权限 / 场景 | 说明 |
|------|------|--------|-------------|------|
| `/pal status` | — | `core` | 所有人 | 世界状态(在线数、FPS 流畅度等) |
| `/pal online` | — | `core` | 所有人 | 当前在线玩家名单 |
| `/pal world` | — | `core` | 所有人 | 世界概览 |
| `/pal rules` | — | `core` | 所有人 | 世界规则(倍率等) |
| `/pal today` | — | `report` | 所有人 | 今日日报 / 在线统计 |
| `/pal events` | — | `events` | 所有人 | 世界事件记录 |
| `/pal guilds` | — | `guilds_bases` | 所有人 | 公会列表 |
| `/pal guild` | `<名称>` | `guilds_bases` | 所有人 | 公会详情 |
| `/pal bases` | — | `guilds_bases` | 所有人 | 据点列表 |
| `/pal base` | `<名称\|#序号>` | `guilds_bases` | 所有人 | 据点详情 |
| `/pal rank` | `[time\|level]` | `players` | 所有人 | 排行榜:今日在线时长榜 + 等级榜 |
| `/pal player` | `<玩家名>` | `players` | 所有人 | 逐个玩家查询(等级、时长、据点等) |
| `/pal me` | `[hide\|show]` | `players` | 所有人 | 我的档案;`hide`/`show` 自助从排行/查询中隐藏或恢复 |
| `/pal bind` | `<玩家名>` | `players` | 所有人 | 绑定平台账号 ↔ 玩家(供 `/pal me` 识别本人) |
| `/pal unbind` | — | `players` | 所有人 | 解除我的玩家绑定(与 `/pal bind` 对称) |
| `/pal server` | `[add\|remove <名称>]` | `core` | 所有人（add/remove 管理员·仅群聊） | 裸命令=服务器列表+本群授权/活动；`add`/`remove` 授权/撤销本群 |
| `/pal whoami` | — | `core` | 所有人（**建议私聊**） | 查看我的账号标识 `平台:账号`(如 `aiocqhttp:12345`);报给超管加入受托名单用 |
| `/pal help` | — | `core` | 所有人 | 帮助(按当前启用的组过滤指令) |
| `/pal announce` | `<消息>` | `server_admin_basic` | **仅授权管理员** | 全服广播(消息为剩余整串) |
| `/pal save` | — | `server_admin_basic` | **仅授权管理员** | 保存世界存档 |
| `/pal kick` | `<玩家名\|userid> [理由]` | `server_admin_basic` | **仅授权管理员** | 踢出玩家(可重连);目标可传角色名(实时解析)或直接传 userid |
| `/pal unban` | `<userid>` | `server_admin_basic` | **仅授权管理员** | 解封玩家 |
| `/pal ban` | `<玩家名\|userid> [理由]` | `server_admin_danger` | **仅授权管理员** · 高危 | 封禁玩家(可选二次确认) |
| `/pal shutdown` | `<秒> [公告]` | `server_admin_danger` | **仅授权管理员** · 高危 | 倒计时关服;秒数为正整数(1–86400),公告为剩余整串(可选二次确认) |
| `/pal stop` | — | `server_admin_danger` | **仅授权管理员** · 高危 | 立即停服,**不存档(丢档风险)**(可选二次确认) |
| `/pal confirm` | — | `core` | **仅授权管理员** | 确认执行上一条待确认的高危操作;无待确认操作时回「无待确认操作或已超时」 |

任意查询指令末尾可加 **`@<服务器名>`** 单次指定目标服务器(详见下文「多服务器与群授权」)。

> **写命令的 `@server` 词序**:服务器覆盖只识别命令**末尾**的 `@<服务器名>`,如 `/pal kick Alice 作弊 @beta`。`announce` 消息、`kick`/`ban` 理由是自由文本整串,若**恰以 `@词` 结尾**(如 `/pal announce 快来 @discord`)会被误当服务器覆盖——自由文本请勿以 `@词` 收尾,或显式把 `@server` 放最末。连续空格/换行会被折叠为单空格,不保证逐字保留。

## 功能开关 → 可用指令矩阵

功能按组可插拔(设置页「功能开关」章勾选)。**关闭某组:其指令回「未开放」、`/pal help` 里不再列出、也不轮询该组端点**;代码保留,改开即恢复。

| 功能组 | 默认 | 对应指令 | 开启时 | 关闭时指令行为 |
|--------|------|----------|--------|----------------|
| `core`(不可关闭) | 恒开 | `status` `online` `world` `rules` `server` `whoami` `help` | ✅ 可用 | —(无法关闭) |
| `report` | 开 | `today` | ✅ 可用 | ❌ 回「未开放」、help 隐藏 |
| `events` | 开 | `events` | ✅ 可用(并记录世界事件) | ❌ 回「未开放」、不生成事件 |
| `guilds_bases` | **关** | `guilds` `guild` `bases` `base` | ✅ 可用 | ❌ 回「未开放」、help 隐藏 |
| `players` | **关** | `rank` `player` `me` `bind` `unbind` | ✅ 可用 | ❌ 回「未开放」、help 隐藏 |
| `server_admin_basic` | **关** | `announce` `save` `kick` `unban` | ✅ 仅授权管理员可用 | ❌ 管理员回「未开放」、help 隐藏;非管理员一律「需要管理员权限」 |
| `server_admin_danger` | **关** | `ban` `shutdown` `stop` | ✅ 仅授权管理员可用(可选二次确认) | ❌ 管理员回「未开放」、help 隐藏;非管理员一律「需要管理员权限」 |

> `server_admin_basic` / `server_admin_danger` 默认关闭:属**受控写**,详见下节[服务器管控](#服务器管控受控写)。非管理员对写命令**一律**回「需要管理员权限」(与组开关状态无关,避免据回执反推危险组是否开启)。

> `players` 默认关闭:玩家个体查询含隐私考量。时长榜仅统计**今日**在线时长、等级榜含离线全体;`strict` 隐私模式下更保守(时长榜停用、玩家档案隐藏坐标等)。支持管理员排除名单与玩家自助 `/pal me hide`——被排除或隐藏者不出现在排行/查询中,且不泄露其存在。

> `guilds_bases` 默认关闭:依赖服务器开放 `/game-data`,而 Palworld 1.0 专用服务器上游未开放 `PalGameDataBridge`,故公会/据点/PalBox 整组默认停用,详见[配置项详解](configuration.md#features功能开关)。

## 多服务器与群授权

- `/pal server`:列出所有服务器与本群授权/活动状态。
- `/pal server add <名称>`（管理员，仅群聊）：授权本群使用该服务器并设为活动服务器。
- `/pal server remove <名称>`（管理员，仅群聊）：撤销本群对该服务器的授权。
- **@server 尾缀**:任意查询指令可在末尾加 `@<服务器名>` 单次指定目标服务器,如 `/pal status @alpha`、`/pal guild 晨曦联盟 @beta`(服务器名不含空格,公会/据点名可含空格)。

## 权限管理

本插件用**两层权限模型**,与 AstrBot 全局管理员(`admins_id`)相互独立——`_is_admin` **只认**插件自己的受托名单,不认 AstrBot 的 `admins_id`,也不看 `event.role`。

- **受托名单(`permission_admins`)**:超管在设置页「权限」章逐条维护(每行含 `id` = `平台:账号`,和可选 `note` 备注)。**只有**名单内的账号被视为本插件的管理员。玩家在群里(建议私聊)发 `/pal whoami` 得到自己的 `平台:账号`,报给超管加入。
- **内置 server 门**:`/pal server add`、`/pal server remove` 恒需管理员,现改由受托名单判定(名单外成员执行会被拒)。
- **命令门(`admin_only_commands`)**:超管可把任意查询命令锁成仅管理员可用(填 astrbot 命令串,如 `player`、`rank`)。被锁命令对名单外成员回「该命令需要管理员权限。」。**不可锁集** = `{server, whoami, help}`(这三条永远对所有人开放,填入会被忽略)。

> **安全告知**:受托名单是**全局**的——加入者在其所在的**每个群**都拥有管理员权(含对任意群执行 `server add`/`server remove`)。多适配器实例 / 多群共用同一 bot 时共享同一命名空间,请谨慎授权。`id`/`note` 以**明文**落盘到 `data/config/`,`note` 勿填真实姓名、联系方式等 PII。详见[配置项详解 · 权限](configuration.md#permissions权限管理)。

## 服务器管控(受控写)

v0.9.0 起插件从**只读监测**跨入**受控写管控**:提供 7 条对官方 REST 写端点的管理命令(`announce`/`save`/`kick`/`unban`/`ban`/`shutdown`/`stop`)+ `/pal confirm` 二次确认。承诺从「绝不写」转为「受控写:默认全关、仅授权管理员、全程审计」。

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

- **OPEN 访问模式爆炸半径**:`access_mode=open` 下 `_authorized` 恒真,写命令**不再受群授权名单约束**——任一授权管理员可从任意群/私聊对任意就绪服务器 `stop`/`ban`。强烈劝阻「OPEN + `server_admin_danger` 同开」;多群共享同一 bot 时尤须谨慎。
- **`stop` 丢档**:`/pal stop` 强制停服**不保存存档**,可能丢失未存进度。需要保存请先 `/pal save`,或改用 `/pal shutdown`(倒计时期间正常保存)。
- **冒充/归属**:Palworld REST 无操作者身份校验,审计记录的是「哪个受托管理员通过 bot 发起」,非游戏内身份。
- **名字解析依赖 /players**:目标服务器不可达时无法按名解析,回明确错误,可直传 userid 兜底。

## 降级行为

API 不可达时显示「当前无法获取世界数据,最后成功更新 N 分钟前」,**绝不**臆断「服务器已关机」。部分端点失败时降级相关模块,其余照常。
