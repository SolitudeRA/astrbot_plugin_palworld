# 配置项详解

全部配置可在插件设置页可视化编辑;本页为逐项参考,字段名即配置文件键名。设置页入口与保存行为见[插件页面](#插件页面webui-设置与状态)一节。

## servers(多服务器)

可添加多台 Palworld 服务器。`name` 唯一且不含空格/冒号/`@`;`base_url` 如 `http://127.0.0.1:8212`;密码填 `password_env`(环境变量名,推荐)或 `password`(明文,会落盘)。每台服务器可单独填 `timezone` 覆盖全局时区。

## routing(访问控制)

- **world_mode(运行模式)**:默认 `multi` 多世界(一个插件监测多台,按群授权/切换服务器);`single` 单世界(所有操作对应唯一服务器,取第一台就绪服务器)。单世界模式下 `link` 组隐藏且运行时拒绝,`@server` 覆盖与群绑定被忽略。
- **access_mode**:默认 `restricted`(群需管理员授权才能查询某服务器);`open` 为任意群可查任意服务器。
- **group_bindings(可选预设授权)**:等价于管理员执行 `/pal link add`,仅作**初始种子**,不覆盖运行时改动。
- **privacy.mode**:`strict` / `balanced`(默认)/ `advanced`(当前版本按 balanced 生效)。

> **⚠️ 单世界 × restricted 访问告警**:当 `world_mode=single` 且 `access_mode=restricted` 时,**访问控制被架空**——所有会话(含私聊)都可直接读取唯一服务器,读命令对所有上下文开放。若需按会话/群授权,请改用 `world_mode=multi`。该告警在插件启动日志中输出;**写命令仍受管理员硬门约束**(单世界不放宽写权限)。

## permissions(权限管理)

本插件的管理员判定**独立于** AstrBot 全局管理员(`admins_id`):只认下面维护的受托名单,不认 `admins_id`、不看 `event.role`。玩家发 `/pal whoami` 可查到自己的 `平台:账号` 标识,报给超管加入名单。

| 配置项 | 类型 | 默认 | 含义 |
| --- | --- | --- | --- |
| `permission_admins` | 名单(逐条) | 空 | 受托群管理员。每行 `id`(账号标识 `平台:账号`,如 `aiocqhttp:12345`)+ 可选 `note`(备注)。只有名单内账号被视为本插件管理员,可执行 `link add`/`link remove`、`server` 组写命令及被锁命令 |
| `admin_only_commands` | 字符串列表 | 空 | 锁成**仅管理员**的命令,填**完整命令路径**(如 `player info`、`world status`、`rank`)。被锁命令对名单外成员回「该命令需要管理员权限。」。**不可锁集**(填入会被忽略)= `server` 组各写命令 + `link` 组各命令 + `help`/`whoami`/`confirm`。**v0.9.5 破坏性**:旧扁平值(`player`)须改为完整路径(`player info`),否则锁**静默失效**;无法识别的锁条目会在启动日志中告警(unknown-lock)。迁移映射表见[指令文档 · 锁迁移](commands.md#admin_only_commands-锁迁移v095-破坏性) |

**安全告知(务必阅读)**:

- **名册全局爆炸半径**:受托名单是**全局**的——加入者在其所在的**每个群**都拥有管理员权,包括对**任意群**执行 `link add`/`link remove` 与 `server` 组写命令。授权前确认对方可被信任到这个范围。
- **多适配器 / 多群共享命名空间**:多个适配器实例或多个群若共用同一个 bot,则共享同一套受托名单与账号命名空间。多群共用一个 bot 时请谨慎授权。
- **明文落盘、勿填 PII**:`id`/`note` 均以**明文**保存到 `data/config/`,`note` 请勿填真实姓名、联系方式等个人身份信息(PII)。

## polling(轮询,全局设置、逐服务器套用)

| 配置项 | 默认 | 含义 |
| --- | --- | --- |
| `metrics_seconds` | 30 | `/metrics` 轮询间隔(秒),驱动 FPS/在线数等世界指标 |
| `players_seconds` | 30 | `/players` 轮询间隔(秒),驱动在线名单与上下线会话 |
| `info_seconds` | 600 | `/info` 轮询间隔(秒),服务器版本/名称等基本信息(启动时立即拉取一次) |
| `settings_seconds` | 1800 | `/settings` 轮询间隔(秒),世界规则(倍率等)变化很慢,无需频繁 |
| `game_data_seconds` | 120 | `/game-data` 轮询间隔(秒),公会/据点等世界数据 |
| `jitter_ratio` | 0.10 | 间隔随机抖动比例,避免各端点整齐同时请求 |
| `max_concurrency` | 6 | 全局在途 HTTP 请求上限,保护游戏服务器不被并发压垮 |

背压自适应:某端点响应耗时超过当前间隔时自动指数级拉长该端点的实际轮询间隔(上限为基准的 8 倍),连续多次恢复正常后再逐步回落——无需手动调参。

## world(时区与展示)

| 配置项 | 默认 | 含义 |
| --- | --- | --- |
| `timezone` | `Asia/Tokyo` | 全局时区(IANA 名称),影响 `/pal world today` 等所有时间展示;每台服务器可在 servers 条目里单独填 `timezone` 覆盖 |
| `locale` | `zh-CN` | 文案语言(当前版本仅支持 zh-CN) |
| `fps_smooth` | 50 | FPS ≥ 此值展示为「流畅」 |
| `fps_moderate` | 35 | FPS ≥ 此值(且 < `fps_smooth`)展示为「一般」 |
| `fps_laggy` | 20 | FPS ≥ 此值(且 < `fps_moderate`)展示为「卡顿」;FPS < 此值展示为「严重卡顿」 |

## bases(据点推导,隐私 strict 模式下整体停用)

据点并非 API 直接给出,而是由玩家采样位置**推导**:同一网格位置被连续观察到足够次数才确认为据点。

| 配置项 | 默认 | 含义 |
| --- | --- | --- |
| `enabled` | true | 启用据点/PalBox 推导(strict 隐私模式下强制停用) |
| `assignment_radius` | 5000 | 玩家采样点归属到某据点的最大半径(游戏世界坐标单位) |
| `ambiguity_ratio` | 0.20 | 最近/次近据点距离差比阈值,低于该比例视为归属不明、不计入 |
| `confirmation_samples` | 3 | 同一位置需被一致观察到的次数,达到后才确认建立据点 |
| `position_grid_size` | 2000 | 坐标量化网格边长——落库前坐标先按此粒度取整,即「不公开精确位置」的实现 |
| `z_weight` | 0.5 | 计算距离时 Z 轴(高度)的权重,弱化立体地形带来的误判 |

## history(数据保留天数,到期自动清理)

| 配置项 | 默认 | 含义 |
| --- | --- | --- |
| `raw_metrics_days` | 7 | 原始指标(逐次轮询采样)保留天数 |
| `aggregate_days` | 90 | 预聚合统计保留天数 |
| `session_days` | 365 | 玩家上下线会话保留天数 |
| `observation_days` | 180 | 世界观察记录保留天数 |

## custom_headers(自定义 HTTP 请求头)

随插件对 REST API 的所有轮询请求一并发送。适用于 REST API 经反向代理/网关暴露、需要额外鉴权头的场景(如 Cloudflare Access 的 `CF-Access-Client-Id` / `CF-Access-Client-Secret`)。在设置页按条目添加/移除。

| 字段 | 默认 | 说明 |
|------|------|------|
| `name` | 空 | Header 名(如 `CF-Access-Client-Id`) |
| `value` | 空 | Header 值(明文,与 `value_env` 二选一;明文会落盘到 data/config/) |
| `value_env` | 空 | 值的环境变量名(推荐存放敏感值,如网关 Token) |
| `servers` | 空 | 限定服务器 name,逗号分隔多个。**servers 留空 = 发给所有服务器**(包括之后新增的)——含凭证的头务必限定作用域 |

注意:

- `Authorization`、`Host`、`Expect`、`Content-Length`、`Transfer-Encoding`、`Connection` 为保留头,配置了也会被忽略(Basic Auth 由服务器条目的 username/password 负责)
- `value_env` / `password_env` 指向的环境变量变更后需**重启 AstrBot** 进程才能读到(设置页保存只热重载插件,环境变量是进程级的)
- 被跳过的无效条目会在插件启动日志中以 warning 提示(只含名字与原因,不含值)

## 插件页面(WebUI 设置与状态)

AstrBot ≥ 4.24.1 支持插件自定义 WebUI 页面。安装本插件后,可在插件详情页(≥4.24.1)或左侧栏「插件页面」分组(≥4.25.3)打开「PalWorldTerminal 设置」页,可视化编辑服务器/访问控制等全部配置,并查看各服务器只读状态。低于 4.24.1 的 AstrBot 不显示该页面,插件其余功能不受影响。

- **保存即重载**:页面保存配置后插件会自动重启内部容器使其生效,重载期间轮询短暂中断(在线时长统计有极小缺口),聊天指令会临时提示「正在重载」
- **敏感字段**:密码、自定义请求头值等敏感项在页面上不回显明文,显示为「已设置，留空则不修改」;留空提交即保留旧值(内部用保留字 `__unchanged__` 表示未改动)。若修改了某服务器的地址(base_url),出于安全必须重新输入该服务器密码,避免旧凭证被发往新地址
- **鉴权**:页面请求经 AstrBot Dashboard 登录态转发,未登录无法访问

## features(功能开关)

功能按组可插拔,在设置页勾选。关闭的组不轮询其端点、不装配其服务、指令回「未开放」;代码保留,改开即恢复。

| 组 | 默认 | 指令 | 说明 |
|------|------|------|------|
| `report` | 开 | `/pal world today` | 日报/在线统计 |
| `events` | 开 | `/pal world events` | 世界事件记录(关闭后不生成事件) |
| `players` | **关** | `/pal player info` `/pal player bind` `/pal rank` `/pal me` | 玩家个体查询(隐私考量默认关) |
| `guilds_bases` | **关** | `/pal guild list` `/pal guild bases` 等 | 公会与据点,依赖服务器开放 `/game-data` |
| `server_admin_basic` | **关** | `/pal server announce` `/pal server save` `/pal server kick` `/pal server unban` | 服务器管控(基础写):受控写,仅授权管理员可用,详见 [server_admin](#server_admin服务器管控) |
| `server_admin_danger` | **关** | `/pal server ban` `/pal server shutdown` `/pal server stop` | 服务器管控(高危写):停服/封禁等,建议配合二次确认,详见 [server_admin](#server_admin服务器管控) |

**关于 `guilds_bases` 默认关闭**:Palworld 1.0 的专用服务器虽提供 `/v1/api/game-data` 端点,但未开放启用 `PalGameDataBridge` 的任何 INI 字段或启动参数(上游限制),该端点无真实数据。故公会/据点/PalBox 功能默认关闭。待 Palworld 开放后,在设置页把 `features.guilds_bases` 设为开即整组恢复。`bases.*` 与 `game_data_seconds` 仅在该组开启时生效。

## server_admin(服务器管控)

服务器管控(受控写)相关配置。写命令**默认全部关闭**(见 `features.server_admin_basic` / `server_admin_danger`),开启后仅**授权管理员**(`permission_admins` 名单成员)可用,每次操作全程落库审计。命令详见[指令文档 · 服务器管控](commands.md#服务器管控受控写)。

| 配置项 | 类型 | 默认 | 含义 |
| --- | --- | --- | --- |
| `require_confirmation` | bool | `false` | 开启后 `server_admin_danger` 组命令(`ban`/`shutdown`/`stop`)需二次确认:首发回预览,须在超时内回 `/pal confirm` 才执行。`basic` 组永不需确认 |
| `confirmation_timeout` | int(秒) | `30` | 二次确认等待窗口,超时后待确认操作作废(范围 5–600) |
| `audit_retention_days` | int(天) | `180` | 审计记录留存天数,到期随清理链自动删旧行(范围 1–3650) |

**安全告知(务必阅读)**:

- **⚠️ OPEN 访问模式爆炸半径**:`routing.access_mode=open` 下写命令**不再受群授权名单约束**——任一授权管理员可从任意群/私聊对任意就绪服务器执行 `stop`/`ban`。强烈劝阻「OPEN + `server_admin_danger` 同开」;多群共享同一 bot 时尤须谨慎。RESTRICTED(默认)下 `@server` 覆盖仍受群授权名单约束。
- **⚠️ `server stop` 丢档**:`/pal server stop` 强制停服**不保存存档**,可能丢失未存进度;需要保存请先 `/pal server save` 或改用 `/pal server shutdown`(倒计时期间正常保存)。故 danger 组默认关、建议开 `require_confirmation`。
- **审计留存与 PII**:`admin_audit` 表含**明文** `admin_id`(受托管理员标识)、`target_name`(目标角色名)与时间,属受控 PII;目标 userid 仅以**哈希**(与观测侧同一 world_id 命名空间)落库,不存明文。默认 180 天有界清理,可按需调整。
- **名字解析绕过隐私过滤(对管理员合理)**:`kick`/`ban` 按角色名解析时实时读取 `/players` 原始 userid,**绕过** `/pal me hide`/`exclude_names` 隐私过滤——写操作需要真 userid,且管理员本可从游戏内看到全部在线玩家,不构成对同侪玩家的存在性泄露。
