# 完整指令与功能开关

所有指令以 `/pal` 前缀触发、返回纯文本,全部只读。带「功能组」的指令仅在对应组开启时可用(见下方矩阵);`core` 组指令恒可用。

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

任意查询指令末尾可加 **`@<服务器名>`** 单次指定目标服务器(详见下文「多服务器与群授权」)。

## 功能开关 → 可用指令矩阵

功能按组可插拔(设置页「功能开关」章勾选)。**关闭某组:其指令回「未开放」、`/pal help` 里不再列出、也不轮询该组端点**;代码保留,改开即恢复。

| 功能组 | 默认 | 对应指令 | 开启时 | 关闭时指令行为 |
|--------|------|----------|--------|----------------|
| `core`(不可关闭) | 恒开 | `status` `online` `world` `rules` `server` `whoami` `help` | ✅ 可用 | —(无法关闭) |
| `report` | 开 | `today` | ✅ 可用 | ❌ 回「未开放」、help 隐藏 |
| `events` | 开 | `events` | ✅ 可用(并记录世界事件) | ❌ 回「未开放」、不生成事件 |
| `guilds_bases` | **关** | `guilds` `guild` `bases` `base` | ✅ 可用 | ❌ 回「未开放」、help 隐藏 |
| `players` | **关** | `rank` `player` `me` `bind` `unbind` | ✅ 可用 | ❌ 回「未开放」、help 隐藏 |

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

## 降级行为

API 不可达时显示「当前无法获取世界数据,最后成功更新 N 分钟前」,**绝不**臆断「服务器已关机」。部分端点失败时降级相关模块,其余照常。
