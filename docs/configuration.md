# 配置项详解

全部配置可在插件设置页可视化编辑;本页为逐项参考,字段名即配置文件键名。设置页入口与保存行为见[插件页面](#插件页面webui-设置与状态)一节。

## servers(多服务器)

可添加多台 Palworld 服务器。`name` 唯一且不含空格/冒号/`@`;`base_url` 如 `http://127.0.0.1:8212`;密码填 `password_env`(环境变量名,推荐)或 `password`(明文,会落盘)。每台服务器可单独填 `timezone` 覆盖全局时区。

## routing(访问控制)

- **world_mode(运行模式)**:**默认 `single` 单世界**(所有操作对应唯一服务器,取第一台就绪服务器;`link` 组隐藏且运行时拒绝,`@server` 覆盖与群绑定被忽略);`multi` 多世界(一个插件监测多台,按群授权/切换服务器)。首次设置由插件页面引导选择;之后在「连接」章使用带预览、授权迁移和残留清理的切换控件。AstrBot 齿轮配置中的裸字段只作应急直编,会跳过迁移与确认。
- **setup_confirmed(首次设置确认标志)**:bool,默认 `false`。首次设置闸的标志——为 `true` 前(尚未完成首次模式选择),除 `/pal help`/`/pal whoami`/`/pal whereami` 外的 `/pal` 命令一律回引导语(命令闸生效,见[指令文档 · 首次使用](commands.md#首次使用首次设置闸))。**一般无需手动改动**:设置页首次引导屏选运行模式并确认后自动写入 `true`(连同 `world_mode`)。全新安装靠 AstrBot 把 schema 默认回填到配置,`setup_confirmed` 恒为 `false`,故首次装机必经一次设置页确认。
- **access_mode**:默认 `restricted`;`open` 为任意会话可查。restricted 的授权方式随模式不同——单世界查授权群名单 `single_allowed_groups`,多世界查 `/pal link` 群授权(DB 名单)。
- **single_allowed_groups(单世界授权群名单)**:见下小节,**仅 `world_mode=single` + `access_mode=restricted` 时生效**;多世界忽略。
- **group_bindings(可选预设授权)**:仅**多世界**有意义,等价于管理员执行 `/pal link add`,仅作**初始种子**,不覆盖运行时改动;单世界忽略。
- **privacy.mode**:`strict` / `balanced`(默认)/ `advanced`(当前版本按 balanced 生效)。

### single_allowed_groups(单世界授权群名单)

单世界模式下 `restricted` 访问的读授权名单(顶层配置键,与 `group_bindings` 同为 `template_list` 范式)。只有名单内的会话(群/私聊)可查询唯一服务器;`open` 模式忽略本名单。

| 字段 | 类型 | 默认 | 含义 |
| --- | --- | --- | --- |
| `single_allowed_groups` | 名单(逐条) | 空 | 每行 `umo`(会话标识 unified_msg_origin,如 `aiocqhttp:GroupMessage:123456`)+ 可选 `note`(备注)。群里发 `/pal whereami` 可取本会话 UMO,交管理员在设置页「连接」章添加 |

- **取 UMO**:在目标群里发 `/pal whereami`,回显本会话标识;私聊亦有各自 UMO,按同一名单判定。
- **⚠️ 空名单 = 全群不可读**:`single` + `restricted` + 空名单是安全默认(fail-closed)——**当前无人可查询**。插件启动日志会告警提示用 `/pal whereami` + 设置页补名单。全新装机(默认 `single` + 默认 `restricted` + 空名单)即此状态,需管理员完成一次授权引导。
- **写命令不受本名单约束**:`server` 组 7 条写命令仅受管理员硬门(`permission_admins` 管理员名单)把守,**不查授权群名单**——授权管理员可从任意群/私聊管理唯一服务器。
- **明文落盘、勿填 PII**:`umo`/`note` 以**明文**保存到 `data/config/`,`note` 请勿填真实姓名、联系方式等 PII(镜像 `permission_admins` 安全约束)。

> **多世界不读取本名单**:`world_mode=multi` 下读授权走 `/pal link` 群绑定。通过设置页从单世界切换时,可把选中的名单项迁移为多世界群绑定;裸改 `world_mode` 不会迁移。

### 模式互转（设置页切换与授权迁移）

`world_mode` 除首次设置与齿轮裸切外,可在设置页「连接」章的切换控件更改。切换时可按需迁移授权(move 语义,切回不复活):

- 单世界 → 多世界:把选中的 `single_allowed_groups` 群写入多世界群绑定(`group_bindings`)、清空单世界名单。
- 多世界 → 单世界:把选中群的绑定并入 `single_allowed_groups`、清空多世界绑定;多台就绪时可选保留一台并永久删除其余台的全部历史数据(不可恢复)。

删除其余台的数据、或此前从配置中移除服务器所残留的历史数据,可在切换运行模式流程的**完成步**的「残留数据清理」小节清除(服务端重算孤儿集,只删已不在配置中的服务器数据)。该入口暂不常驻设置页;若仅移除了服务器而未切换模式,可在下次进入切换流程时于完成步一并清除。

## permissions(权限管理)

本插件的管理员判定**独立于** AstrBot 全局管理员(`admins_id`):只认下面维护的管理员名单,不认 `admins_id`、不看 `event.role`。玩家发 `/pal whoami` 可查到自己的 `平台:账号` 标识,报给超管加入名单。

| 配置项 | 类型 | 默认 | 含义 |
| --- | --- | --- | --- |
| `permission_admins` | 名单(逐条) | 空 | 管理员名单成员。每行 `id`(账号标识 `平台:账号`,如 `aiocqhttp:12345`)+ 可选 `note`(备注)。只有名单内账号被视为本插件管理员,可执行 `link add`/`link remove`、`server` 组写命令及被锁命令 |
| `command_permissions` | 三态行(逐条) | 空 | **命令树控制面**的落盘真相源。每行为一条命令或一个组指定 `enabled`(是否启用)/ `admin_only`(是否仅管理员)覆盖,各取 `inherit`/`on`/`off`。`command` 填**完整命令路径**(如 `world status`、`player info`)或**组名**(如 `guild`、`player`,对该组所有子命令生效)。建议在设置页「权限」章可视化编辑 |

### 命令树权限模型

每条命令是一个节点,有两个独立开关:

- **`enabled`(是否启用)**:`off` 的命令回「未开启」、`/pal help` 不列出;其数据**采集也随之关闭**(采集派生自启用状态)。`core` 组命令恒开,不可关。
- **`admin_only`(是否仅管理员)**:`on` 时该命令对管理员名单外成员回「该命令需要管理员权限。」。

两轴各取三态 `inherit`(继承)/ `on` / `off`。**稀疏覆盖 + 三级继承**:某命令的生效值先看它自己的覆盖行,没有则看**组**覆盖行,再没有则用**功能组默认**(见 [features](#features功能开关))。只需为要改的命令/组写一行,其余留空即继承。危险写命令(`server ban/shutdown/stop`)**不从组键继承** `enabled`,须逐条显式开启。

**不可锁集**(`admin_only` 覆盖对其无效)= `server` 组各写命令 + `link` 组各命令 + 元命令 `help`/`whoami`/`whereami`/`confirm`——这些由功能门 + 管理员门把守,或按设计恒对所有人开放;`server` 写命令的启停仍由 `command_permissions` 的 `enabled` 控制(默认全关)。

### 从旧版(features / admin_only_commands)迁移

v0.9.5 及更早用 `features` 布尔功能开关 + `admin_only_commands` 名单;**v0.9.6 起统一为 `command_permissions`**。插件**首次装载**时把旧键**一次性自动迁移**成等价三态行并落库(旧键随后清除、四处同源),无需手动改配置。对照关系:

| 旧配置 | 旧值(≠默认才迁移) | 迁移为 `command_permissions` 行 |
| --- | --- | --- |
| `features.report` | `off` | `world today` → `enabled=off` |
| `features.events` | `off` | `world events` → `enabled=off` |
| `features.guilds_bases` | `on` | `guild`(组) → `enabled=on` |
| `features.players` | `on` | `player`(组)+ `rank` + `me` → `enabled=on` |
| `features.server_admin_basic` | `on` | `server announce/save/kick/unban` → `enabled=on` |
| `features.server_admin_danger` | `on` | `server ban/shutdown/stop` → `enabled=on` |
| `admin_only_commands` 各条 | 完整路径(如 `player info`) | 该命令 → `admin_only=on` |

> `admin_only_commands` 里必须是**完整命令路径**;分级前的旧扁平值(如 `player`)无法识别、迁移中会被登记为无效锁并在启动日志告警(不静默)。不可锁集中的命令同样不能通过旧名单加锁,写入后会报告为无效。迁移完成后请在设置页「权限」章核对结果,不要继续维护旧键。

**安全告知(务必阅读)**:

- **名单全局爆炸半径**:管理员名单是**全局**的——加入者在其所在的**每个群**都拥有管理员权,包括对**任意群**执行 `link add`/`link remove` 与 `server` 组写命令。授权前确认对方可被信任到这个范围。
- **多适配器 / 多群共享命名空间**:多个适配器实例或多个群若共用同一个 bot,则共享同一套管理员名单与账号命名空间。多群共用一个 bot 时请谨慎授权。
- **明文落盘、勿填 PII**:`id`/`note` 均以**明文**保存到 `data/config/`,`note` 请勿填真实姓名、联系方式等个人身份信息(PII)。

## polling(轮询,全局设置、逐服务器套用)

| 配置项 | 默认 | 含义 |
| --- | --- | --- |
| `metrics_seconds` | 30 | `/metrics` 轮询间隔(秒),驱动 FPS/在线数等世界指标 |
| `players_seconds` | 30 | `/players` 轮询间隔(秒),驱动在线名单与上下线会话 |
| `info_seconds` | 600 | `/info` 轮询间隔(秒),服务器版本/名称等基本信息(启动时立即拉取一次) |
| `settings_seconds` | 1800 | `/settings` 轮询间隔(秒),世界规则(倍率等)变化很慢,无需频繁 |
| `game_data_seconds` | 120 | `/game-data` 轮询间隔(秒),公会/据点等世界数据(PalGameDataBridge);仅当某条 `guilds_bases` 命令生效启用时才轮询该端点 |
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

## history(数据留存目标,当前尚未自动清理)

| 配置项 | 默认 | 含义 |
| --- | --- | --- |
| `raw_metrics_days` | 7 | 原始指标(逐次轮询采样)保留天数 |
| `aggregate_days` | 90 | 预聚合统计保留天数 |
| `session_days` | 365 | 玩家上下线会话保留天数 |
| `observation_days` | 180 | 世界观察记录保留天数 |

> 当前版本会读取并保存这些留存天数,但尚未由调度器自动执行到期清理。请按自己的运营与合规要求管理 AstrBot 数据目录,不要把这些配置视为自动删除保证。

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

本插件正式支持 **AstrBot ≥ 4.24.1 且 < 5**。安装后可在插件详情页(≥4.24.1)或左侧栏「插件页面」分组(≥4.25.3)打开「PalWorldTerminal 设置」页,可视化编辑服务器/访问控制等全部配置,并查看各服务器只读状态。低于 4.24.1 的版本无法提供本插件所需的设置页与首次设置流程,不在支持范围内。

- **保存即重载**:页面保存配置后插件会自动重启内部容器使其生效,重载期间轮询短暂中断(在线时长统计有极小缺口),聊天指令会临时提示「正在重载」
- **敏感字段**:密码、自定义请求头值等敏感项在页面上不回显明文,显示为「已设置，留空则不修改」;留空提交即保留旧值(内部用保留字 `__unchanged__` 表示未改动)。若修改了某服务器的地址(base_url),出于安全必须重新输入该服务器密码,避免旧凭证被发往新地址
- **鉴权**:页面请求经 AstrBot Dashboard 登录态转发,未登录无法访问

## features(功能开关)

> **v0.9.6 起统一为命令树权限模型**:旧的 `features` 布尔功能开关**已删除**,启停改由 `command_permissions` 三态行承载(见[权限管理](#permissions权限管理))。命令仍按下表的**功能组**归类——功能组决定每条命令的**默认启用状态**与**采集派生**;要改默认,在设置页「权限」章为该命令或整组加一行 `enabled=on/off`。

命令按功能组归类,功能组只决定**默认值**(实际生效值由 `command_permissions` 覆盖):

| 功能组 | 默认 | 命令 | 说明 |
|------|------|------|------|
| `core` | 恒开(不可关) | `world status/rules` `online` `whoami` `whereami` `help` `confirm` `link`(裸) `server`(裸) | 基础命令,始终可用 |
| `report` | 开 | `/pal world today` | 日报/在线统计 |
| `events` | 开 | `/pal world events` | 世界事件记录(关闭后不生成事件) |
| `players` | **默认关** | `/pal player info` `/pal player bind` `/pal player unbind` `/pal rank` `/pal me` | 玩家个体查询(隐私考量默认关) |
| `guilds_bases` | **默认关** | `/pal world overview` `/pal guild list` `/pal guild info` `/pal guild bases` `/pal guild base` | 公会与据点及世界概览,依赖 `game-data`(PalGameDataBridge)派生数据,默认关、由服主按需开启 |
| `server_admin_basic` | **默认关** | `/pal server announce` `/pal server save` `/pal server kick` `/pal server unban` | 服务器管控(基础写):受控写,仅授权管理员可用,详见 [server_admin](#server_admin服务器管控) |
| `server_admin_danger` | **默认关** | `/pal server ban` `/pal server shutdown` `/pal server stop` | 服务器管控(高危写):停服/封禁等,建议配合二次确认,详见 [server_admin](#server_admin服务器管控) |

关闭的命令指令回「未开启」、`/pal help` 里不再列出。**采集派生自启用状态**:观测只读端点(`/info` `/metrics` `/players` `/settings`)**恒采集**,与命令启停无关;`/game-data` 端点仅当 `guilds_bases` 组有命令生效启用时才轮询(`bases.*` 与 `game_data_seconds` 亦随之生效)。

**关于 `guilds_bases`(默认关)**:公会/据点/PalBox 命令与归队至此的 `world overview` 依赖 `/v1/api/game-data`(PalGameDataBridge)派生数据,与 `players` 同为**默认关**,由服主在 `command_permissions` 命令树按需为对应命令启用。启用任一 `guilds_bases` 命令后,`/game-data` 端点方随之轮询、`bases.*` 据点推导参数亦生效。

## server_admin(服务器管控)

服务器管控(受控写)相关配置。写命令**默认全部关闭**(须在[权限管理](#permissions权限管理)命令树的 `command_permissions` 中为对应 `server` 写命令显式启用;这些命令归 `server_admin_basic` / `server_admin_danger` 功能组,默认值即关),开启后仅**授权管理员**(`permission_admins` 名单成员)可用,每次操作全程落库审计。命令详见[指令文档 · 服务器管控](commands.md#服务器管控受控写)。

| 配置项 | 类型 | 默认 | 含义 |
| --- | --- | --- | --- |
| `require_confirmation` | bool | `false` | 开启后 `server_admin_danger` 组命令(`ban`/`shutdown`/`stop`)需二次确认:首发回预览,须在超时内回 `/pal confirm` 才执行。`basic` 组永不需确认 |
| `confirmation_timeout` | int(秒) | `30` | 二次确认等待窗口,超时后待确认操作作废(范围 5–600) |
| `audit_retention_days` | int(天) | `180` | 审计记录留存目标(范围 1–3650);当前版本尚未自动清理旧行 |

**安全告知(务必阅读)**:

- **⚠️ OPEN 访问模式爆炸半径**:`routing.access_mode=open` 下写命令**不再受群授权名单约束**——任一授权管理员可从任意群/私聊通过当前路由执行 `stop`/`ban`。强烈劝阻「OPEN + `server_admin_danger` 同开」;多群共享同一 bot 时尤须谨慎。RESTRICTED(默认)下,单世界写命令不查 `single_allowed_groups` 读名单,多世界写命令使用群绑定的当前活动服务器;管控命令不支持 `@server` 临时覆盖。
- **⚠️ `server stop` 丢档**:`/pal server stop` 强制停服**不保存存档**,可能丢失未存进度;需要保存请先 `/pal server save` 或改用 `/pal server shutdown`(倒计时期间正常保存)。故 danger 组默认关、建议开 `require_confirmation`。
- **审计留存与 PII**:`admin_audit` 表含**明文** `admin_id`(授权管理员标识)、`target_name`(目标角色名)与时间,属受控 PII;目标 userid 仅以**哈希**(与观测侧同一 world_id 命名空间)落库,不存明文。`audit_retention_days` 默认 180 天,但当前版本尚未自动执行到期清理,请自行管理数据目录。
- **名字解析绕过隐私过滤(对管理员合理)**:`kick`/`ban` 按角色名解析时实时读取 `/players` 原始 userid,**绕过** `/pal me hide`/`exclude_names` 隐私过滤——写操作需要真 userid,且管理员本可从游戏内看到全部在线玩家,不构成对同侪玩家的存在性泄露。
