# PalChronicle · 帕鲁纪事（astrbot_plugin_palworld）

> 只读的 Palworld 世界纪事、玩家档案与社区观察 AstrBot 插件，基于官方 REST API。

## 安全与隐私（请先阅读）

- **只读**：本插件仅调用官方只读端点 `/info`、`/metrics`、`/players`、`/settings`、`/game-data`，**不控制服务器**、不执行任何写/管理操作。
- **不存储 IP**：入口即删除 IP、Basic Auth 凭证、原始平台账号与原始内部 ID；玩家标识仅以 `HMAC-SHA256(salt, world_id + ":" + raw_user_id)` 落库。
- **不公开精确位置**：坐标默认量化为粗网格；`strict` 隐私模式下坐标完全不落库、据点模块停用。Ping 仅以“优秀/正常/偏高”分桶展示，不存原始数值。
- **需在服务器端启用 REST**：Palworld 服务器须开启 REST API（`RESTAPIEnabled=True` 并设置管理员密码）。
- **勿暴露公网**：REST API 请勿直接暴露到公网，走 localhost / 内网 / VPN / 反向代理；密码建议用环境变量（`password_env`）而非明文。

## 环境要求

- AstrBot ≥ 4.24.1（插件设置页需此版本；建议最新 4.26.x）
- Python ≥ 3.11
- SQLite 3

## 安装

1. 将本插件放入 AstrBot 的 `plugins/` 目录（或通过插件市场安装）。
2. 安装依赖：`pip install -r requirements.txt`（运行时仅需 aiohttp、aiosqlite、tzdata）。开发者请改装 `pip install -r requirements-dev.txt`（叠加 PyYAML、pytest 等测试依赖）。
3. 在 AstrBot 网页配置页填写服务器与路由（见下）。
4. 重载插件。

## 配置

在插件配置页：

- **servers（多服务器）**：可添加多台 Palworld 服务器。`name` 唯一且不含空格/冒号/`@`；`base_url` 如 `http://127.0.0.1:8212`；密码填 `password_env`（环境变量名，推荐）或 `password`（明文，会落盘）。
- **routing.access_mode**：默认 `restricted`（群需管理员授权才能查询某服务器）；`open` 为任意群可查任意服务器。
- **group_bindings（可选预设授权）**：等价于管理员执行 `/pal use`，仅作**初始种子**，不覆盖运行时改动。
- **privacy.mode**：`strict` / `balanced`（默认）/ `advanced`（v0.1 按 balanced 生效）。

### polling（轮询，全局设置、逐服务器套用）

| 配置项 | 默认 | 含义 |
| --- | --- | --- |
| `metrics_seconds` | 30 | `/metrics` 轮询间隔（秒），驱动 FPS/在线数等世界指标 |
| `players_seconds` | 30 | `/players` 轮询间隔（秒），驱动在线名单与上下线会话 |
| `info_seconds` | 600 | `/info` 轮询间隔（秒），服务器版本/名称等基本信息（启动时立即拉取一次） |
| `settings_seconds` | 1800 | `/settings` 轮询间隔（秒），世界规则（倍率等）变化很慢，无需频繁 |
| `game_data_seconds` | 120 | `/game-data` 轮询间隔（秒），公会/据点等世界数据 |
| `jitter_ratio` | 0.10 | 间隔随机抖动比例，避免各端点整齐同时请求 |
| `max_concurrency` | 6 | 全局在途 HTTP 请求上限，保护游戏服务器不被并发压垮 |

背压自适应：某端点响应耗时超过当前间隔时自动指数级拉长该端点的实际轮询间隔（上限为基准的 8 倍），连续多次恢复正常后再逐步回落——无需手动调参。

### world（时区与展示）

| 配置项 | 默认 | 含义 |
| --- | --- | --- |
| `timezone` | `Asia/Tokyo` | 全局时区（IANA 名称），影响 `/pal today` 等所有时间展示；每台服务器可在 servers 条目里单独填 `timezone` 覆盖 |
| `locale` | `zh-CN` | 文案语言（v0.1 仅支持 zh-CN） |
| `fps_smooth` | 50 | FPS ≥ 此值展示为“流畅” |
| `fps_moderate` | 35 | FPS ≥ 此值（且 < `fps_smooth`）展示为“一般” |
| `fps_laggy` | 20 | FPS ≥ 此值（且 < `fps_moderate`）展示为“卡顿”；FPS < 此值展示为“严重卡顿” |

### bases（据点推导，隐私 strict 模式下整体停用）

据点并非 API 直接给出，而是由玩家采样位置**推导**：同一网格位置被连续观察到足够次数才确认为据点。

| 配置项 | 默认 | 含义 |
| --- | --- | --- |
| `enabled` | true | 启用据点/PalBox 推导（strict 隐私模式下强制停用） |
| `assignment_radius` | 5000 | 玩家采样点归属到某据点的最大半径（游戏世界坐标单位） |
| `ambiguity_ratio` | 0.20 | 最近/次近据点距离差比阈值，低于该比例视为归属不明、不计入 |
| `confirmation_samples` | 3 | 同一位置需被一致观察到的次数，达到后才确认建立据点 |
| `position_grid_size` | 2000 | 坐标量化网格边长——落库前坐标先按此粒度取整，即“不公开精确位置”的实现 |
| `z_weight` | 0.5 | 计算距离时 Z 轴（高度）的权重，弱化立体地形带来的误判 |

### history（数据保留天数，到期自动清理）

| 配置项 | 默认 | 含义 |
| --- | --- | --- |
| `raw_metrics_days` | 7 | 原始指标（逐次轮询采样）保留天数 |
| `aggregate_days` | 90 | 预聚合统计保留天数 |
| `session_days` | 365 | 玩家上下线会话保留天数 |
| `observation_days` | 180 | 世界观察记录保留天数 |

### custom_headers（自定义 HTTP 请求头）

随插件对 REST API 的所有轮询请求一并发送。适用于 REST API 经反向代理/网关暴露、需要额外鉴权头的场景（如 Cloudflare Access 的 `CF-Access-Client-Id` / `CF-Access-Client-Secret`）。在 WebUI 配置页按条目添加/删除。

| 字段 | 默认 | 说明 |
|------|------|------|
| `name` | 空 | Header 名（如 `CF-Access-Client-Id`） |
| `value` | 空 | Header 值（明文，与 `value_env` 二选一；明文会落盘到 data/config/） |
| `value_env` | 空 | 值的环境变量名（推荐存放敏感值，如网关 Token） |
| `servers` | 空 | 限定服务器 name，逗号分隔多个。**servers 留空 = 发给所有服务器**（包括之后新增的）——含凭证的头务必限定作用域 |

注意：

- `Authorization`、`Host`、`Expect`、`Content-Length`、`Transfer-Encoding`、`Connection` 为保留头，配置了也会被忽略（Basic Auth 由服务器条目的 username/password 负责）
- `value_env` / `password_env` 指向的环境变量变更后需**重启 AstrBot** 进程才能读到（WebUI 保存配置只热重载插件，环境变量是进程级的）
- 被跳过的无效条目会在插件启动日志中以 warning 提示（只含名字与原因，不含值）

### 插件页面（WebUI 设置与状态）

AstrBot ≥ 4.24.1 支持插件自定义 WebUI 页面。安装本插件后，可在插件详情页
（≥4.24.1）或左侧栏「插件页面」分组（≥4.25.3）打开「PalChronicle 设置」页，
可视化编辑服务器/路由等配置，并查看各服务器只读状态面板。低于 4.24.1 的
AstrBot 不显示该页面，插件其余功能不受影响。设置页现以 Vue 页面提供，可视化
编辑全部 9 个配置节（服务器/请求头/路由/轮询/世界/据点/隐私/保留/特性）。

- **保存即重载**：页面保存配置后插件会自动重启内部容器使其生效，重载期间
  轮询短暂中断（在线时长统计有极小缺口），聊天命令会临时提示「正在重载」
- **敏感字段**：密码、自定义请求头值等敏感项在页面上不回显明文，显示为
  「已设置（留空保持不变）」；留空提交即保留旧值（内部用保留字
  `__unchanged__` 表示未改动）。若修改了某服务器的地址（base_url），出于
  安全必须重新输入该服务器密码，避免旧凭证被发往新地址
- **鉴权**：页面请求经 AstrBot Dashboard 登录态转发，未登录无法访问

### features（功能开关）

功能按组可插拔，在插件配置页勾选。关闭的组不轮询其端点、不装配其服务、命令回「未开放」；代码保留，改开即恢复。

| 组 | 默认 | 命令 | 说明 |
|------|------|------|------|
| `report` | 开 | `/pal today` | 日报/在线统计 |
| `events` | 开 | `/pal events` | 世界事件记录（关闭后不生成事件） |
| `guilds_bases` | **关** | `/pal guilds` `/pal bases` 等 | 公会与据点，依赖服务器开放 `/game-data` |

**关于 `guilds_bases` 默认关闭**：Palworld 1.0 的专用服务器虽提供 `/v1/api/game-data` 端点，但未开放启用 `PalGameDataBridge` 的任何 INI 字段或启动参数（上游限制），该端点无真实数据。故公会/据点/PalBox 功能默认关闭。待 Palworld 开放后，在配置页把 `features.guilds_bases` 设为开即整组恢复。`bases.*` 与 `game_data_seconds` 仅在该组开启时生效。

## 多服务器与群授权用法

- `/pal servers`：列出所有服务器与本群授权/活动状态。
- `/pal use <名称>`（管理员，仅群聊）：授权本群使用该服务器并设为活动服务器。
- `/pal unbind <名称>`（管理员）：撤销本群对该服务器的授权。
- **@server 尾缀**：任意查询命令可在末尾加 `@<服务器名>` 单次指定目标服务器，如 `/pal status @alpha`、`/pal guild 晨曦联盟 @beta`（服务器名不含空格，公会/据点名可含空格）。

## 命令一览（全部只读、纯文本）

所有命令以 `/pal` 前缀触发、返回纯文本。带「功能组」的命令仅在对应组开启时可用（见下方矩阵）；`core` 组命令恒可用。

### 命令详细说明

| 命令 | 参数 | 功能组 | 权限 / 场景 | 说明 |
|------|------|--------|-------------|------|
| `/pal status` | — | `core` | 所有人 | 世界状态（在线数、FPS 流畅度等） |
| `/pal online` | — | `core` | 所有人 | 当前在线玩家名单 |
| `/pal world` | — | `core` | 所有人 | 世界概览 |
| `/pal rules` | — | `core` | 所有人 | 世界规则（倍率等） |
| `/pal today` | — | `report` | 所有人 | 今日日报 / 在线统计 |
| `/pal events` | — | `events` | 所有人 | 世界事件记录 |
| `/pal guilds` | — | `guilds_bases` | 所有人 | 公会列表 |
| `/pal guild` | `<名称>` | `guilds_bases` | 所有人 | 公会详情 |
| `/pal bases` | — | `guilds_bases` | 所有人 | 据点列表 |
| `/pal base` | `<名称\|#序号>` | `guilds_bases` | 所有人 | 据点详情 |
| `/pal rank` | `[time\|level]` | `players` | 所有人 | 排行榜：今日在线时长榜 + 等级榜 |
| `/pal player` | `<玩家名>` | `players` | 所有人 | 逐个玩家查询（等级、时长、据点等） |
| `/pal me` | `[hide\|show]` | `players` | 所有人 | 我的档案；`hide`/`show` 自助从排行/查询中隐藏或恢复 |
| `/pal bind` | `<玩家名>` | `players` | 所有人 | 绑定平台账号 ↔ 玩家（供 `/pal me` 识别本人） |
| `/pal servers` | — | `core` | 所有人 | 服务器列表 + 本群授权 / 活动状态 |
| `/pal help` | — | `core` | 所有人 | 帮助（按当前启用的组过滤命令） |
| `/pal use` | `<名称>` | `core` | **管理员 · 仅群聊** | 授权本群使用该服务器并设为活动服务器 |
| `/pal unbind` | `<名称>` | `core` | **管理员** | 撤销本群对该服务器的授权 |

任意查询命令末尾可加 **`@<服务器名>`** 单次指定目标服务器（详见上文「多服务器与群授权用法」）。

### 功能开关 → 可用命令矩阵

功能按组可插拔（配置页 `features` 勾选）。**关闭某组：其命令回「未开放」、`/pal help` 里不再列出、也不轮询该组端点**；代码保留，改开即恢复。

| 功能组 | 默认 | 对应命令 | 开启时 | 关闭时命令行为 |
|--------|------|----------|--------|----------------|
| `core`（不可关闭） | 恒开 | `status` `online` `world` `rules` `servers` `help` `use` `unbind` | ✅ 可用 | —（无法关闭） |
| `report` | 开 | `today` | ✅ 可用 | ❌ 回「未开放」、help 隐藏 |
| `events` | 开 | `events` | ✅ 可用（并记录世界事件） | ❌ 回「未开放」、不生成事件 |
| `guilds_bases` | **关** | `guilds` `guild` `bases` `base` | ✅ 可用 | ❌ 回「未开放」、help 隐藏 |
| `players` | **关** | `rank` `player` `me` `bind` | ✅ 可用 | ❌ 回「未开放」、help 隐藏 |

> `players` 默认关闭：玩家个体查询含隐私考量。时长榜仅统计**今日**在线时长、等级榜含离线全体；`strict` 隐私模式下更保守（时长榜停用、玩家档案隐藏坐标等）。支持管理员排除名单与玩家自助 `/pal me hide`——被排除或隐藏者不出现在排行/查询中，且不泄露其存在。

> `guilds_bases` 默认关闭详见上文 `features` 节（依赖服务器开放 `/game-data`，而 Palworld 1.0 专用服务器上游未开放 `PalGameDataBridge`，故公会 / 据点 / PalBox 整组默认停用；`bases.*` 与 `game_data_seconds` 也仅在该组开启时生效）。

## 降级说明

API 不可达时显示“当前无法获取世界数据，最后成功更新 N 分钟前”，**绝不**臆断“服务器已关机”。部分端点失败时降级相关模块，其余照常。

## 许可证

见 LICENSE。
