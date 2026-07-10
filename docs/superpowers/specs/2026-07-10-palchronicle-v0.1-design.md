# PalChronicle v0.1 实现设计规格

> 面向实现的设计规格（Spec）。基于《PalChronicle_完整设计方案.md》(PRD+TDD, v1.0-draft)，
> 裁剪并细化到可直接实现的 **v0.1 MVP** 范围，并叠加本次新增的
> **多服务器 / 多聊天群 / 群↔服务器路由 / 网页配置** 需求。
>
> - 规格版本：v0.1-spec-1
> - 编写日期：2026-07-10
> - 目标运行环境：**AstrBot ≥ 4.10.4**（`template_list` 配置需要；建议最新 4.26.x）、Python ≥ 3.11、SQLite 3
> - 上游设计文档：`C:\Users\arthu\Downloads\PalChronicle_完整设计方案.md`

---

## 1. 范围与目标

### 1.1 v0.1 交付（做）

只读的 Palworld 世界观察插件，覆盖：

- **14 个命令**（全部只读、纯文本、无 LLM、无主动推送）：
  查询类 `/pal status`、`/pal online`、`/pal world`、`/pal rules`、`/pal guilds`、`/pal guild <name>`、
  `/pal bases`、`/pal base <name>`、`/pal events`、`/pal today`、`/pal help`；
  路由类 `/pal servers`、`/pal use <name>`、`/pal unbind <name>`。
- **多服务器采集**：每个启用的服务器一套独立的后台轮询循环（metrics/players/info/settings/game-data）。
- **群↔服务器路由与访问控制**：默认 `restricted`，群需管理员授权后方可查询某服务器。
- **隐私入口清洗**：删 IP/原始账号，ID 做 HMAC，坐标量化落库。
- **SQLite 持久化 + 迁移**。
- **玩家会话追踪**（上线/离线/健康采样累计时长）。
- **世界 / 公会 / PalBox / 据点模型 + 据点归属推导**（high/medium/low 置信度）。
- **事件检测**（升级、新玩家、新公会、新据点、据点消失、工作帕鲁数量变化、世界日里程碑、在线纪录）——仅"检测 + 落库 + 可查询"，不主动推送。
- **模板日报**（`/pal today`，按服务器时区自然日，纯确定性数据生成）。
- **API 失败分级降级**。
- **核心确定性算法的单元测试 + 时间序列集成测试 + 隐私扫描测试 + Golden 文本测试**。

### 1.2 v0.1 不做（留给后续版本）

玩家绑定 `/pal bind`、`/pal me`、成就、榜单、搭档关系、随行帕鲁长期统计、世界观察图鉴、
**主动通知/订阅**、图片卡片、LLM 工具与文案润色、社区任务板、组队 LFG、每日幸运帕鲁、
移动挑战绑定、精确/延迟位置观察、多语言、数据导出、管理页面。

### 1.3 与上游设计文档的偏差记录

| 项 | 上游文档 | 本规格 | 原因 |
|---|---|---|---|
| 插件 id | `astrbot_plugin_palchronicle` | **`astrbot_plugin_palword`** | 沿用已建 git 仓库名，保持数据目录/安装一致（用户确认） |
| 服务器数量 | 单服务器（单 `api:` 块） | **多服务器**（`servers` 列表） | 用户新增需求 |
| 群路由 | 无 | **群↔服务器绑定 + 访问控制**，默认 restricted | 用户新增需求 |
| 主动通知 | v0.2 模块 | v0.1 完全不含（事件仅可查询） | 附录 C 边界，聚焦技术风险验证 |
| 世界主键 | `world_id = worldguid(/epoch)` | `world_id = "{server_id}:{worldguid}:{epoch}"` | 多服务器隔离 |

---

## 2. 命名与版本

- 插件 id（`metadata.yaml.name`）：`astrbot_plugin_palword`（须唯一，前缀 `astrbot_plugin_`）
- 展示名（`display_name`）：`PalChronicle · 帕鲁纪事`
- 内部 Python 包名：`palchronicle`
- 命令前缀：`/pal`
- `metadata.yaml.astrbot_version`: `">=4.10.4"`

`metadata.yaml`：

```yaml
name: astrbot_plugin_palword
display_name: PalChronicle · 帕鲁纪事
desc: 只读的 Palworld 世界纪事、玩家档案与社区观察插件（基于官方 REST API）
version: v0.1.0
author: SolitudeRA
repo: https://github.com/SolitudeRA/astrbot_plugin_palword
astrbot_version: ">=4.10.4"
```

---

## 3. 架构与目录

沿用上游文档 §24.1，仅填充 v0.1 所需文件。`main.py` 保持瘦（读配置 / 装配依赖 / 注册命令组 /
`initialize()` 启动采集 / `terminate()` 收尾），业务全在 `palchronicle/`。

```
astrbot_plugin_palword/
├── main.py                 # Star 子类；仅装配与生命周期
├── metadata.yaml
├── _conf_schema.json       # 网页配置 Schema（servers 用 template_list）
├── requirements.txt        # aiohttp, aiosqlite (pytest/pytest-asyncio 归 dev)
├── README.md · LICENSE
│
├── palchronicle/
│   ├── __init__.py
│   ├── config.py           # 配置解析：把 AstrBotConfig(dict) 解析为强类型 ServerConfig/PollingConfig/... 数据类
│   ├── container.py         # 依赖装配（每服务器一个 Collector/Trackers，一套共享 Repo）
│   │
│   ├── domain/
│   │   ├── models.py        # 数据类：World, PlayerIdentity, PlayerObservation, PlayerSession,
│   │   │                    #        Guild, PalBox, Base, PalObservation, WorldEvent, WorldMetric
│   │   ├── enums.py         # UnitType, ActionCategory, EventType, Confidence, LeaveReason,
│   │   │                    #        AccessMode, LeaveReason, EndpointName
│   │   └── events.py        # 事件类型定义 + dedup_key 构造
│   │
│   ├── application/
│   │   ├── snapshot_service.py    # 编排单次采集→清洗→归一→WorldSnapshot→分发各 tracker
│   │   ├── player_service.py      # 玩家身份 + 会话追踪 + 等级/建筑变化
│   │   ├── guild_service.py       # 公会聚合
│   │   ├── base_service.py        # PalBox 稳定匹配 + 据点归属推导 + 置信度
│   │   ├── event_service.py       # 事件检测/确认/去重
│   │   ├── report_service.py      # 模板日报（按 server/world/自然日）
│   │   ├── routing_service.py     # 群↔服务器解析与访问控制
│   │   └── query_service.py       # 命令读侧（读缓存/DB，组装展示 DTO）
│   │
│   ├── adapters/
│   │   ├── palworld_rest.py       # aiohttp REST 客户端（BasicAuth、超时、重试、安全日志）
│   │   ├── privacy_filter.py      # 入口脱敏（删禁字段、HMAC、坐标量化）
│   │   ├── normalizer.py          # 字段归一（字符串布尔、大小写容错、Class/Action 映射）
│   │   ├── sqlite_repository.py   # 所有表读写（aiosqlite 单连接 + 写锁）
│   │   └── metadata_repository.py # 加载 metadata/*.json（Class/Action/settings 映射）
│   │
│   ├── infrastructure/
│   │   ├── database.py            # 连接、初始化、PRAGMA
│   │   ├── migrations.py          # 迁移器（PRAGMA user_version）
│   │   ├── scheduler.py           # 每服务器每端点轮询循环（间隔+抖动+背压+并发上限）
│   │   ├── cache.py               # 查询短时缓存（TTL）
│   │   ├── locks.py               # 每服务器每端点在途锁 + 全局并发信号量
│   │   ├── salt.py                # HMAC secret salt 生成与持久化
│   │   └── clock.py               # 可注入时钟（测试用）
│   │
│   └── presentation/
│       ├── commands.py            # AstrBot handler（/pal 命令组）
│       ├── formatters.py          # 文本渲染（所有命令输出）
│       ├── server_arg.py          # 解析 "@server" 后缀 + 目标服务器解析入口
│       └── locale.py              # zh-CN 文案表
│
├── metadata/
│   ├── pals.zh-CN.json            # Class → {name_zh, name_en, element, rarity...}
│   ├── actions.json              # Action/AI_Action → ActionCategory
│   └── settings.zh-CN.json        # settings 字段 → {label_zh, unit, enum 映射}
│
└── tests/
    ├── unit/
    ├── integration/               # 时间序列场景
    ├── fixtures/                  # 合成脱敏 API 快照（多场景）
    └── golden/                    # 文本黄金文件
```

**不含**（后续版本）：`templates/`、`presentation/cards.py`、`adapters/llm_tools.py`、
`adapters/astrbot_messaging.py`、`domain/achievements.py`、`domain/privacy.py`（隐私逻辑 v0.1 放 `adapters/privacy_filter.py`）。

---

## 4. 技术选型与关键决策

| 项 | 选择 | 说明 |
|---|---|---|
| HTTP 客户端 | **aiohttp** + `aiohttp.BasicAuth("admin", pwd)` | 每服务器复用一个 `ClientSession`；`terminate()` 关闭 |
| 存储 | **aiosqlite** 单连接 + `asyncio.Lock` 写锁 | 全异步；写串行化；`PRAGMA journal_mode=WAL` |
| 迁移 | 手写迁移器 + `PRAGMA user_version` | 顺序应用 migration 函数；失败即停写并记管理员错误 |
| ID 脱敏 | **HMAC-SHA256(salt, world_id + ":" + raw_user_id)** | salt 见 §4.1 |
| 主时间戳 | **插件接收时间**（epoch 秒，UTC 存储） | game-data 的 `Time` 仅辅助（非 ISO8601，服务器本地时间） |
| 自然日边界 | 按**服务器时区**（`server.timezone` 或全局 `world.timezone`） | 日报/活跃日用 |
| 测试 | pytest + pytest-asyncio | 合成 fixtures |
| 输出 | 纯文本（`event.plain_result`） | v0.1 无图片卡 |

### 4.1 HMAC Secret Salt

- 首次运行用 `secrets.token_bytes(32)` 生成，写入 `<data_dir>/secret_salt`（`data_dir = StarTools.get_data_dir()`）。
- 权限尽量收敛（POSIX 下 0600；Windows 忽略）。
- **永不**写入日志、数据库、配置文件。
- 若文件已存在则读取复用（保证跨重启 player_key 稳定）。

### 4.2 关键 AstrBot API 约定（实现须遵守）

- 命令组：`@filter.command_group("pal")` 装饰的是**普通 `def`**（函数体 `pass`）；子命令 `@pal.command("status")` 是 **`async def` + `yield event.plain_result(...)`**（异步生成器）。
- 管理命令：`@filter.permission_type(filter.PermissionType.ADMIN)` 叠在 `@pal.command(...)` 之上。
- 配置注入：`__init__(self, context: Context, config: AstrBotConfig)`；`AstrBotConfig` 从 `astrbot.api` 导入，是 `dict` 子类；一律 `.get(k, default)` 读取。
- 生命周期：`async def initialize()`（起后台任务）、`async def terminate()`（cancel 任务、关 session/db）。后台任务用 `asyncio.create_task` 并持引用；循环体内 try/except 防单次异常杀死循环；`terminate()` 中 `cancel()` 并 `await`。
- 会话标识：`event.unified_msg_origin`（`平台实例:消息类型:会话id`）。判群：`event.get_message_type() == MessageType.GROUP_MESSAGE`（或 `not event.is_private_chat()`）。群 id：`event.get_group_id()`（私聊返回 `""`）。
- 存储：业务数据 SQLite 于 `StarTools.get_data_dir()`；本规格**不使用** KV（路由状态也入 SQLite，见 §7）。

---

## 5. 配置设计（`_conf_schema.json`）

顶层字段：`servers`（`template_list`）、`group_bindings`（`template_list`）、`routing`（`object`）、
`polling`（`object`）、`world`（`object`）、`bases`（`object`）、`privacy`（`object`）、`history`（`object`）。

> 注意：`template_list` 仅在**顶层**验证可用；不确定能否嵌套在 `object` 内，故 `group_bindings`
> 独立为顶层字段，不嵌进 `routing`。



### 5.1 servers（template_list）

```jsonc
"servers": {
  "type": "template_list",
  "description": "Palworld 服务器列表（网页可添加多个；name 需唯一）",
  "hint": "密码建议填环境变量名(password_env)而非明文；明文会落盘到 data/config/",
  "default": [],
  "templates": {
    "server": {
      "name": "Palworld 服务器",
      "display_item": "name",
      "items": {
        "name":         { "type": "string", "description": "服务器名称（唯一标识，勿含空格/冒号/@）", "default": "" },
        "enabled":      { "type": "bool",   "description": "是否启用", "default": true },
        "base_url":     { "type": "string", "description": "REST API 地址", "default": "http://127.0.0.1:8212", "obvious_hint": true },
        "username":     { "type": "string", "description": "Basic Auth 用户名", "default": "admin" },
        "password":     { "type": "string", "description": "密码（明文，与 password_env 二选一）", "default": "" },
        "password_env": { "type": "string", "description": "密码环境变量名（推荐，与 password 二选一）", "default": "" },
        "timeout":      { "type": "int",    "description": "请求超时(秒)", "default": 10 },
        "verify_tls":   { "type": "bool",   "description": "校验 TLS 证书（http 忽略）", "default": true },
        "timezone":     { "type": "string", "description": "该服务器时区（IANA，如 Asia/Tokyo；留空用全局）", "default": "" }
      }
    }
  }
}
```

### 5.2 routing（object）+ group_bindings（顶层 template_list）

```jsonc
"routing": { "type": "object", "description": "群↔服务器 路由与访问控制", "items": {
  "access_mode":    { "type": "string", "description": "restricted=群需管理员授权; open=任意群任意服务器", "default": "restricted", "options": ["restricted", "open"] },
  "default_server": { "type": "string", "description": "全局默认服务器 name（群未指定且未绑定时的兜底）", "default": "" }
}},
"group_bindings": {
  "type": "template_list",
  "description": "预设 群→服务器 授权（可选，等价于管理员 /pal use）",
  "default": [],
  "templates": { "binding": { "name": "绑定", "display_item": "umo", "items": {
    "umo":    { "type": "string", "description": "会话标识 unified_msg_origin，如 aiocqhttp:GroupMessage:123456", "default": "" },
    "server": { "type": "string", "description": "服务器 name", "default": "" },
    "active": { "type": "bool",   "description": "设为该群活动服务器", "default": true }
  }}}
}
```

### 5.3 polling / world / bases / privacy / history（object）

```jsonc
"polling": { "type": "object", "description": "轮询间隔（全局，逐服务器套用）", "items": {
  "metrics_seconds":   { "type": "int", "default": 30 },
  "players_seconds":   { "type": "int", "default": 30 },
  "info_seconds":      { "type": "int", "default": 600 },
  "settings_seconds":  { "type": "int", "default": 1800 },
  "game_data_seconds": { "type": "int", "default": 120 },
  "jitter_ratio":      { "type": "float", "default": 0.10 },
  "max_concurrency":   { "type": "int", "description": "全局在途 HTTP 请求上限", "default": 6 }
}},
"world": { "type": "object", "items": {
  "timezone": { "type": "string", "default": "Asia/Tokyo" },
  "locale":   { "type": "string", "default": "zh-CN", "options": ["zh-CN"] },
  "fps_smooth":   { "type": "int", "default": 50 },
  "fps_moderate": { "type": "int", "default": 35 },
  "fps_laggy":    { "type": "int", "default": 20 }
}},
"bases": { "type": "object", "items": {
  "enabled":             { "type": "bool",  "default": true },
  "assignment_radius":   { "type": "int",   "default": 5000 },
  "ambiguity_ratio":     { "type": "float", "default": 0.20 },
  "confirmation_samples":{ "type": "int",   "default": 3 },
  "position_grid_size":  { "type": "int",   "default": 2000 },
  "z_weight":            { "type": "float", "default": 0.5 }
}},
"privacy": { "type": "object", "items": {
  "mode":              { "type": "string", "default": "balanced", "options": ["strict", "balanced", "advanced"] },
  "public_exact_ping": { "type": "bool", "default": false },
  "public_positions":  { "type": "bool", "default": false }
}},
"history": { "type": "object", "items": {
  "raw_metrics_days":  { "type": "int", "default": 7 },
  "aggregate_days":    { "type": "int", "default": 90 },
  "session_days":      { "type": "int", "default": 365 },
  "observation_days":  { "type": "int", "default": 180 }
}}
```

### 5.4 配置解析（`config.py`）

- 把 `AstrBotConfig`（dict）解析为强类型数据类：`ServerConfig`、`RoutingConfig`、`PollingConfig`、`WorldConfig`、`BasesConfig`、`PrivacyConfig`、`HistoryConfig`、`AppConfig`。
- **server_id 校验**：`name` 去空白后作为 `server_id`；若为空、重复、含 `:`/`@`/空白 → 记 warning 并跳过该条（不崩溃）。
- **密码解析**：`password_env` 非空 → `os.environ.get(password_env)`；否则用 `password`；都为空 → 该服务器视为未就绪，记 warning、不启动其采集循环、命令查询时提示"未配置凭证"。
- **热更新边界**：`terminate()`→重载会重建容器，因此配置变更经插件重载生效。v0.1 不实现运行时热更（文档 §25.3 的热更留后续）。

---

## 6. 多服务器采集架构

### 6.1 采集循环

- 每个"就绪"（enabled 且凭证可用）的服务器，`scheduler` 为其 5 个端点各起一个循环任务：
  - `/metrics` 30s、`/players` 30s、`/info` 600s（启动即拉一次）、`/settings` 1800s、`/game-data` 120s。
  - 实际间隔 = `base * random(1-jitter, 1+jitter)`（`clock` 可注入以便测试确定性）。
- **在途锁**：同一服务器同一端点只允许一个在途请求（`locks.py`）。全局 `asyncio.Semaphore(max_concurrency)` 限制总并发。
- **背压**：若 `/game-data` 处理时间 > 采样间隔 → 跳过下一次、自动提升该服务器 game-data 间隔（乘性退避，封顶），记 `collector` 降频日志，不刷群。
- **隔离**：任一服务器异常/超时不影响其他服务器循环。循环体 try/except，异常记日志后按间隔继续。

### 6.2 采集→存储管线（`snapshot_service`）

1. `palworld_rest` 拉取原始响应（记录 `duration_ms`、`payload_bytes`、`status_code`，**绝不**记 URL 凭证/Authorization）。
2. `privacy_filter`：删除禁止字段（IP、原始 accountName、原始 userId/playerId 明文），对 userId/playerId 做 HMAC 得 `player_key`；坐标按 `privacy.mode` 处理（strict 不落库网格；balanced 落粗网格）。
3. `normalizer`：字符串布尔（`IsActive` `"true"/"false"` → bool）、大小写容错（`userid`/`HP`/`GuildID`/`LocationX` 混用）、缺失字段宽容、Class/Action 映射（未知归 `unknown` 并记 `unknown_classes`，不丢整快照）。
4. 构造内存 `WorldSnapshot`（不落库原始 game-data）。
5. 分发到各 tracker（player/guild/base）与 `event_service`。
6. 仅落库：观察聚合值、会话、指标、事件、量化位置。

### 6.3 世界隔离与 epoch

- `world_id = f"{server_id}:{worldguid}:{epoch}"`（TEXT）。
- 每服务器维护"当前 world_id"。`/info` 返回新 `worldguid` → 视为换世界：关闭旧世界活动会话为 `uncertain`，切换当前 world_id，暂停跨世界比较。
- `epoch` 默认 0；预留给"worldguid 未变但管理员显式重置统计"（v0.1 无重置命令，epoch 恒 0，但 schema 与主键已含 epoch）。

---

## 7. 群 ↔ 服务器 路由与访问控制（`routing_service` + SQLite）

### 7.1 存储：`group_servers` 表（SQLite，非 KV）

| 字段 | 类型 | 说明 |
|---|---|---|
| umo | TEXT | 会话标识（unified_msg_origin） |
| server_id | TEXT | 服务器 name |
| allowed | INTEGER | 1=该群被授权使用此服务器 |
| active | INTEGER | 1=该群当前活动服务器（每 umo 至多一个 active） |
| updated_at | INTEGER | 更新时间 |

主键 `(umo, server_id)`。启动时把 `routing.group_bindings` 预设 upsert 进表（allowed=1，active 按预设）。

### 7.2 目标服务器解析（每条查询命令）

顺序：
1. 命令中的 `@server`（显式覆盖，单次）。
2. 本群活动服务器（`group_servers.active=1`）。
3. 全局 `routing.default_server`。
4. 仅配置一台就绪服务器 → 用它。
5. 否则 → 友好提示：`本会话未指定服务器。管理员可用 /pal use <名称> 绑定，或 /pal servers 查看可用服务器。`

### 7.3 访问校验

- `access_mode = restricted`（默认）：解析出的 `server_id` 必须在本 umo 的 `allowed=1` 集合内（或经 `@server` 显式指定时同样要求 allowed）。否则拒绝：`本会话未被授权使用服务器「X」。请管理员先执行 /pal use X。`
- `access_mode = open`：任意群可用任意就绪服务器（仍走解析顺序，但跳过 allowed 校验）。
- 私聊：`open` 模式可用（解析走 default/单服务器）；`restricted` 模式私聊无 allowed 记录 → 拒绝并提示改为群聊使用。

### 7.4 路由命令

- `/pal servers`（Guest）：列出所有已配置服务器（name、就绪/在线状态、本群是否 allowed、是否 active）。即便本群未授权也可列（仅名称与状态，无世界数据），便于管理员得知名称。
- `/pal use <name>`（**Admin**）：把本群对 `<name>` 置 `allowed=1` 且 `active=1`（其他 server 的 active 清 0）。restricted/open 下均可用；这是授权的主入口。仅群聊可用（私聊拒绝）。
- `/pal unbind <name>`（**Admin**，附加）：撤销本群对 `<name>` 的 allowed；若其为 active 则清空 active。

> v0.1 命令清单据此共 **14 个**（含 `unbind`）。`unbind` 视为 `use` 的对称操作，实现成本极低，纳入 v0.1。

---

## 8. 领域模型（`domain/models.py`，dataclass）

字段沿用上游文档 §8，补充 `server_id`/`world_id`。关键类：

- `World(world_id, server_id, worldguid, epoch, server_name, version, first_seen_at, last_seen_at, current_day)`
- `PlayerIdentity(player_key, world_id, latest_name, first_seen_at, last_seen_at, latest_level, latest_guild_key, id_confidence)`
- `PlayerObservation(observed_at, world_id, player_key, name, level, ping, building_count, guild_key, position_cell?, companion_class?)`
- `PlayerSession(id, world_id, player_key, joined_at, last_confirmed_at, left_at?, observed_seconds, status[active/closed/uncertain], leave_reason)`
- `Guild(guild_key, world_id, latest_name, first_seen_at, last_seen_at, observed_member_count, palbox_count, base_pal_count)`
- `PalBox(palbox_key, world_id, guild_key, position_cell, first_seen_at, last_seen_at, status)`
- `Base(base_key, world_id, palbox_key, display_name?, guild_key, confidence, locked_by_admin, hidden)`
- `BaseObservation(base_key, observed_at, worker_count, active_count, average_level, average_hp_ratio, action_distribution_json)`
- `WorldMetric(world_id, observed_at, fps, frame_time, online_players, world_day, basecamp_count)`
- `WorldEvent(event_id, world_id, event_type, subject_type, subject_key, occurred_at, confirmed_at, payload_json, visibility, confidence, dedup_key)`

枚举（`domain/enums.py`）：`UnitType(Player/OtomoPal/BaseCampPal/WildPal/NPC)`、
`ActionCategory(working/moving/idle/combat/sleeping/eating/incapacitated/unknown)`、
`EventType`（见 §11）、`Confidence(high/medium/low)`、`LeaveReason(observed_timeout/world_offline/unknown)`、
`AccessMode(restricted/open)`、`EndpointName(info/metrics/players/settings/game_data)`。

---

## 9. 数据库 Schema（`sqlite_repository` + `migrations`）

`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;`。迁移器用 `PRAGMA user_version` 记录版本，
顺序应用 `MIGRATIONS = [migration_0001, ...]`。迁移失败 → 停止写入、记管理员级错误、命令返回"数据库迁移失败"。

### 9.1 表（v0.1）

- `schema_meta`（或用 `user_version`）
- `servers(server_id PK, name, host, enabled, first_seen_at, last_seen_at, last_ok_at)`
- `group_servers(umo, server_id, allowed, active, updated_at, PK(umo,server_id))`
- `worlds(world_id PK, server_id, worldguid, epoch, server_name, version, first_seen_at, last_seen_at, current_day)` UNIQUE(server_id, worldguid, epoch)
- `players(player_key, world_id, latest_name, first_seen_at, last_seen_at, latest_level, latest_guild_key, id_confidence, PK(player_key, world_id))`
- `player_sessions(id PK, world_id, player_key, joined_at, last_confirmed_at, left_at, observed_seconds, status, leave_reason)`
- `player_observations(id PK, world_id, player_key, observed_at, level, ping_bucket, building_count, guild_key, companion_class, position_cell)`
- `guilds(guild_key, world_id, latest_name, first_seen_at, last_seen_at, PK(guild_key, world_id))`
- `palboxes(palbox_key, world_id, guild_key, position_cell, first_seen_at, last_seen_at, status, PK(palbox_key, world_id))`
- `bases(base_key, world_id, palbox_key, display_name, guild_key, confidence, locked_by_admin, hidden, first_seen_at, last_seen_at, PK(base_key, world_id))`
- `base_observations(id PK, world_id, base_key, observed_at, worker_count, active_count, average_level, average_hp_ratio, action_distribution_json)`
- `world_metrics(id PK, world_id, observed_at, fps, frame_time, online_players, world_day, basecamp_count)`
- `world_events(event_id PK, world_id, event_type, subject_type, subject_key, occurred_at, confirmed_at, payload_json, visibility, confidence, dedup_key)`
- `daily_aggregates(world_id, day, key, value_json, PK(world_id, day, key))`（预聚合；v0.1 亦可按需即时计算 + 短缓存）
- `unknown_classes(class_name PK, first_seen_at, count)`

### 9.2 索引

```sql
CREATE UNIQUE INDEX idx_events_dedup ON world_events(dedup_key);
CREATE INDEX idx_events_world_time ON world_events(world_id, occurred_at);
CREATE INDEX idx_sessions_player_time ON player_sessions(world_id, player_key, joined_at);
CREATE INDEX idx_obs_player_time ON player_observations(world_id, player_key, observed_at);
CREATE INDEX idx_metrics_world_time ON world_metrics(world_id, observed_at);
CREATE INDEX idx_baseobs_base_time ON base_observations(world_id, base_key, observed_at);
```

### 9.3 保留清理

后台低频清理任务按 `history.*` 删除过期数据（原始指标 7 天、观察 180 天、会话 365 天；
事件与日报长期保留；精确坐标不落库）。

---

## 10. 追踪与推导算法

### 10.1 玩家身份与会话（`player_service`）

- `raw_user_id`：优先 `/players.userId`，回退 `playerId`；`/game-data` Player Actor 用 `userid`。都缺失 → 回退角色名，`id_confidence=low`（改名会产生新身份，须标注）。
- `player_key = HMAC-SHA256(salt, world_id + ":" + raw_user_id)`。
- **会话**：以健康 `/players` 快照为准。
  - 出现且无 active 会话 → 新建 `active` 会话（`joined_at=接收时间`）。
  - 每次健康快照仍在线 → 更新 `last_confirmed_at`，`observed_seconds += min(now - last_confirmed_at, players_seconds * 容差)`（按健康采样间隔累计，避免 API 中断虚增；上游 §15.1）。
  - 连续两个健康 `/players` 快照缺失 → 关闭会话（`closed`，`leave_reason=observed_timeout`）。
  - `/players` 整体不可用（端点失败/世界离线）→ 会话置 `uncertain`，**不**结束、不误判离线。
  - 换世界（worldguid 变）→ 旧世界活动会话置 `uncertain`。
- 重启恢复：`initialize()` 时从 DB 读回 `active`/`uncertain` 会话续跟。
- 等级/建筑变化：与 `players.latest_level`/`building_count` 比较，喂给 `event_service`。

### 10.2 公会聚合（`guild_service`）

从 `/game-data` 按 `GuildID` 聚合：观察成员数（Player Actor + 在线玩家）、PalBox 数、工作帕鲁数、公会名。首次见 → 记 `first_seen_at`，喂 NEW_GUILD 事件候选。

### 10.3 PalBox 稳定匹配 + 据点归属（`base_service`，上游 §13）

- **PalBox 稳定 id**：`palbox_key = f"{world_id}|{guild_key}|{cell_x}:{cell_y}:{cell_z}"`（量化坐标）。坐标轻微漂移 → 最近邻匹配已有 PalBox 而非新建（阈值 = `position_grid_size`）。
- **据点归属**：
  1. 每个 PalBox 作为候选据点锚点，按 `GuildID` 分组。
  2. 每个 `BaseCampPal`：在同公会 PalBox 中找最近者，距离 `d = sqrt(dx²+dy²+z_weight·dz²)`。
  3. `d < assignment_radius` → 分配；最近与次近距离差 < `ambiguity_ratio` → 标 ambiguous。
  4. 无候选/过远 → 归"未确定据点"。
  5. 连续 `confirmation_samples` 次归属一致才建持久 `bases` 记录。
- **置信度**：high（同公会 + 距离明显小于阈值 + ≥3 次一致 + 最近/次近差明显）；medium（同公会 + 阈值内 + 仅 1~2 次）；low（多 PalBox 接近 / 字段缺失 / 归属摆动）。**低置信度不进入公开事件与统计**（除非管理员锁定；v0.1 无锁定命令，故低置信度仅内部记录，不进 `/pal events`）。
- **据点观察指标**（趣味推导，须标注为"插件推导"）：
  - `active_ratio = active_workers / max(worker_count,1)`
  - `activity_score = 100*(0.75*active_ratio + 0.25*known_action_ratio)`
  - `health_score = 100*(0.8*avg_hp_ratio + 0.2*(1-low_hp_ratio))`
  - **禁止**输出产量/仓库/食物/SAN/工作适应性类表述。

---

## 11. 事件检测（`event_service`，上游 §14）

原则：前后确认快照差异；不稳定事件需确认次数；`dedup_key` 唯一索引防重复；区分"观察发生时间"与"确认时间"；API 断线期间不推断真实离线；低置信度推导事件不进公开源。

v0.1 事件类型：

| EventType | 判定 | dedup_key |
|---|---|---|
| `PLAYER_LEVEL_UP` | 新等级 > 历史确认等级，且连续两次观察或 players/game-data 互证；跨多级记 old→new；等级下降不生成负面事件（记数据异常） | `world_id|LEVEL_UP|player_key|new_level` |
| `NEW_PLAYER` | 首次观察到该 player_key | `world_id|NEW_PLAYER|player_key` |
| `NEW_GUILD` | 首次观察到该 guild_key | `world_id|NEW_GUILD|guild_key` |
| `NEW_BASE` | 新 PalBox 候选连续两次存在 + 与已有据点距离超合并阈值 + 公会稳定 + 置信度≥medium | `world_id|NEW_BASE|base_key` |
| `BASE_VANISHED` | 连续 ≥3 次未观察到 + game-data 健康 + worldguid 未变（文案："据点已连续多次未被观察到"） | `world_id|BASE_VANISHED|base_key|first_missing_day` |
| `WORKER_DELTA` | `abs(cur-baseline) >= max(3, baseline*0.2)` 且连续两次确认 | `world_id|WORKER_DELTA|base_key|day|bucket` |
| `WORLD_DAY_MILESTONE` | `days` 跨过 {100,200,365,500,1000,2000} | `world_id|WORLD_DAY|milestone` |
| `ONLINE_RECORD` | 同时在线刷新历史最高，且持续 ≥1 个完整玩家采样周期 | `world_id|ONLINE_RECORD|record_value` |

会话上下线不进事件源（降噪）；仅存 `player_sessions`。所有事件落 `world_events`，经 `/pal events`、`/pal today` 呈现。

---

## 12. 统计（`query_service` / `report_service`，上游 §15）

- 观察在线时长：按健康采样区间累计（见 §10.1），不用首尾差。
- 活跃日：某自然日累计观察在线 ≥ 10 分钟。
- 在线纪录：历史/本日/本周最高；仅持续一个完整采样周期才确认历史纪录。
- 建筑增长：`max(0, latest_confirmed - period_start)`；下降不生成负面事件。
- 日报（模板模式）内容排序：世界里程碑 → 新纪录 → 新玩家/公会/据点 → 玩家成长 → 公会/据点变化 → 轻量编辑部总结。无显著事件 → 输出"平静的一天"，不编造。

---

## 13. 命令规格（`commands.py` + `formatters.py`）

通用：
- 命令组 `/pal`；子命令均 `async def` + `yield event.plain_result(text)`。
- 读侧优先命中缓存/DB（缓存 TTL：status/online 15s、world/guild/base 90s、rules 30min、today 当日短缓存），不每条命令打 API。
- **`@server` 后缀**：`server_arg.py` 先从消息尾部剥离 `@<token>` 作为显式服务器覆盖，再解析其余参数。
- 目标服务器与访问校验见 §7；失败返回对应友好文案。
- API 降级文案见 §14。

| 命令 | 权限 | 行为 / 输出要点 |
|---|---|---|
| `/pal status [@s]` | Guest | 世界名·天数、在线态、玩家 N/M、据点数、FPS+流畅度标签（阈值可配）、帧时间、当前在线简表、今日最高在线、数据更新时间。API 不可达→§14 文案 |
| `/pal online [@s]` / `/pal players` | Guest | 当前在线：角色名·Lv·模糊化Ping·本次观察在线时长。隐私：坐标/IP/账号不展示 |
| `/pal world [@s]` | Guest | 世界天数、在线玩家、玩家角色/随行/工作帕鲁/野生/NPC/PalBox/公会计数、瞬时/平均 FPS；当前最常见野生帕鲁 Top（标注"仅当前快照"） |
| `/pal rules [@s]` | Guest | 成长/多人规则（经验/捕获/刷新/掉落倍率、孵蛋、PVP/友伤、最大玩家、公会/据点上限）；字段→中文/单位/枚举映射（settings.zh-CN.json） |
| `/pal guilds [@s]` | Guest | 世界公会列表：已观察成员、PalBox、工作帕鲁、近7日活跃成员 |
| `/pal guild <name> [@s]` | Guest | 单公会详情：首/最近观察、成员、当日/当周活跃、PalBox、工作帕鲁、平均等级、据点变化事件 |
| `/pal bases [@s]` | Guest | 据点列表（含置信度）；低置信度默认折叠/不展示 |
| `/pal base <name\|#> [@s]` | Guest | 据点详情：置信度、PalBox、工作帕鲁、平均等级、HP分布、活跃数、Action 分布、观察标签（均标注"插件推导"） |
| `/pal events [@s]` | Guest | 近期世界事件（默认最近 N 条）；v0.1 实现 `/pal events` 与 `/pal events today`；`events guild <g>`/`events player <p>` 为可选增强，未实现时回退为全部近期事件 |
| `/pal today [@s]` | Guest | 模板日报（当日，按服务器时区）：活跃玩家、总观察在线、最高同时在线、世界天数推进、今日升级、据点变化、今日纪录、编辑部摘要；空白日不编造 |
| `/pal servers` | Guest | 列出所有服务器：name、就绪/在线、本群 allowed/active |
| `/pal use <name>` | **Admin** | 授权本群使用并设为活动服务器（仅群聊） |
| `/pal unbind <name>` | **Admin** | 撤销本群对该服务器的授权 |
| `/pal help [topic]` | Guest | 按角色显示；不向普通用户展示管理命令细节 |

中文别名（少量，避免冲突）：`/pal 在线`=online、`/pal 世界`=world、`/pal 据点`=bases、
`/pal 公会`=guilds、`/pal 今日`=today、`/pal 状态`=status、`/pal 服务器`=servers。

---

## 14. 错误处理与降级（上游 §22）

- **API 全不可达**：`当前无法获取 Palworld 世界数据。最后成功更新：N 分钟前。` **绝不**说"服务器已关机"（只读 API 无法区分进程停止/网络/认证/端口）。
- **部分端点失败**：metrics 成功 + game-data 失败 → 仍给 status/online，隐藏世界 Actor 详情；players 失败 → 会话 uncertain，不结束；settings 失败 → 用最近缓存 + 显示更新时间；info 新 worldguid → 切 epoch、暂停跨世界比较。
- **401 认证失败**：管理日志记 HTTP 401；用户仅见"世界数据接口配置异常"。
- **Schema 变化**：宽容解析、未知字段忽略、必需字段缺失仅降级相关模块、保留匿名 schema 摘要排错、日志不写敏感原文。
- **数据不一致**：`metrics.currentplayernum` 与 `/players` 数量不一致 → 状态卡以 `/players` 明细为准，附"官方指标：N"，连续异常记诊断日志。
- **未配置任何服务器**：所有查询命令提示"尚未配置 Palworld 服务器，请在插件配置页添加"。

---

## 15. 隐私与安全（上游 §23，MVP 验收 §29.2）

- **永不保存**：IP、REST 密码/Basic Auth Header、原始平台账号、原始内部 ID、完整实时轨迹、完整原始 game-data 历史快照。
- **默认不公开**：精确坐标、精确 PalBox 坐标、完整在线时长（可配）、Ping 精确值（默认模糊为 优秀/正常/偏高）。
- **坐标**：strict 不落库网格；balanced（默认）落粗网格（`position_grid_size`）；advanced 需全体同意（v0.1 不实现 advanced 的启用流程，配置项存在但按 balanced 行为处理并记提示）。
- **日志脱敏**：HTTP 错误不输出含凭证的 URL；不记密码/Authorization/IP/原始 ID/精确坐标。
- **网络提示**：README 强调 REST API 勿暴露公网，走 localhost/内网/VPN/反代。

---

## 16. 元数据文件（`metadata/`）

- `pals.zh-CN.json`：`{ internal_class: { pal_number, name_zh, name_en, element_types, rarity, metadata_version } }`。v0.1 提供结构 + 一批常见帕鲁种子条目；未知 Class → 安全缩写显示 + 记 `unknown_classes`，不阻断快照。
- `actions.json`：`{ action_or_ai_action: category }`，category ∈ ActionCategory；未知 → `unknown`。
- `settings.zh-CN.json`：`{ setting_field: { label_zh, unit, enum_map? } }`，供 `/pal rules` 渲染。

> 说明：v0.1 不追求完整帕鲁图鉴，元数据为"结构 + 种子 + 未知安全降级"，可后续增量补全。

---

## 17. 测试策略（上游 §27）

- **单元**：Schema 宽容解析；禁字段删除；HMAC 稳定性；坐标量化；Class/Action 映射（含未知）；会话健康区间累计；共同在线交集（工具函数，供后续版本，但函数可先测）；据点最近邻归属 + 置信度；事件确认与去重；文本格式化；`server_arg` 的 `@server` 解析；路由解析顺序与访问校验。
- **集成（时间序列）**：用合成快照序列验证 上线/离线、**API 中断不误判离线**、升级确认、PalBox 抖动不误报新据点、新据点确认、据点消失确认、在线纪录、世界日跨里程碑、worldguid 切换隔离。
- **隐私扫描**：DB 全表无 IPv4/IPv6 模式、无原始 userId/playerId、无明文密码；日志无 Basic Auth。
- **Golden**：`/pal status`、`/pal world`、`/pal today`、`/pal rules` 文本快照 + 隐私脱敏输出。
- **合成 fixtures 场景**（`tests/fixtures/`）：正常世界；无玩家；多公会多据点；字段缺失；未知 Class；`IsActive` 字符串布尔；大小写混用键；worldguid 切换；API 中断后恢复；401。
- clock 与轮询抖动可注入，保证测试确定性。

---

## 18. 实现阶段（供 writing-plans 细化）

1. **骨架 + 基础设施**：目录、`metadata.yaml`、`_conf_schema.json`、`requirements.txt`、`config.py`、`database.py`+`migrations.py`、`salt.py`、`clock.py`、`locks.py`、`cache.py`、`palworld_rest.py`（安全日志）。
2. **管线 + 采集**：`domain/models.py`+`enums.py`、`privacy_filter.py`、`normalizer.py`、`metadata_repository.py`、`snapshot_service.py`、`scheduler.py`（抖动/背压/并发/降级/多服务器隔离）。
3. **追踪 + 推导**：世界隔离与 epoch、`player_service`（哈希+会话+等级/建筑）、`guild_service`、PalBox 稳定匹配、`base_service`（归属+置信度）、工作帕鲁聚合。
4. **事件 + 日报**：`event_service`（8 类事件+确认+去重）、`daily_aggregates`、`report_service`（模板日报）。
5. **路由 + 命令**：`routing_service` + `group_servers` 表、`server_arg`、`commands.py`(14 命令)、`formatters.py`、`locale.py`、`query_service`+缓存、按角色 help。
6. **测试 + 文档**：单元/时间序列/隐私/golden 测试与 fixtures、README（首屏强调 只读/不控服务器/不存IP/不公开位置/需启用REST/勿暴露公网/多服务器与群授权用法）。

---

## 19. 验收标准（对齐上游 §29 + 多服务器）

**功能**：连接启用 REST 的世界；正确显示 info/metrics/players；解析 game-data 主要 Actor 类型并计数；
识别玩家会话；检测确认后升级；推导至少一个公会下多个据点并标置信度；生成结构化事件；
生成不虚构的模板日报；game-data 失败时保留基础状态；**多服务器各自独立采集且互不串数据**；
**restricted 模式下未授权群被正确拒绝、`/pal use` 授权后可查询**。

**隐私**：DB 无 IP；日志无 Basic Auth；公共命令无原始 ID；精确坐标默认不落库；位置默认不公开；
推导指标有说明；worldguid 变化后不合并旧世界。

**性能**：普通缓存查询 P95 < 500ms；game-data 处理不阻塞消息回复；采样任务无重叠堆积；
7 天连续运行无任务泄漏；`terminate()` 能关闭所有服务器的 session 与后台任务。

**可靠性**：API 短暂中断不误报全员离线；重复快照不重复生成事件；重启后从 DB 恢复活动会话；
迁移失败停写并给明确管理员错误。

---

## 20. 明确不在 v0.1（复述边界）

绑定/档案/成就/榜单/搭档/随行帕鲁长期统计/图鉴/主动通知/图片卡/LLM/任务板/LFG/幸运帕鲁/
移动挑战/精确或延迟位置观察/多语言/数据导出/管理页面/运行时配置热更。
以上均在 domain/DB/命令层预留扩展位（如 epoch、visibility、confidence、daily_aggregates），不提前实现。
