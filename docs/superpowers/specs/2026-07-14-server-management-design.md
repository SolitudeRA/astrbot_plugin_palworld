# 服务器管控设计（全量写操作 + 权限门 + 二次确认 + 审计）

> 状态：设计定稿待对抗复核 · 目标版本 **v0.9.0** · 依赖已合并的 PR #18 权限管理

## 1. 定位转变（产品级）

插件从**只读监测**正式跨入**读写管控**。这是里程碑变更（v0.8.7 → **v0.9.0**）。

当前多处硬承诺「只读，仅调用官方只读端点，不控制服务器、不执行任何写/管理操作」必须改写为受控写定位：**写操作默认全部关闭、仅授权管理员可用、全程落库审计**。承诺从「绝不写」降级为「受控写」。

需同步改写「只读」文案的位置（对抗复核须核这份清单不漏）：
- `README.md`（L13/L15/L33/L63/**L98 最强声明**、版本徽章、命令计数）
- `main.py` `@register(...)` 描述串（L81）与版本参数
- `palworld_terminal/__init__.py` 包 docstring + `__version__`
- `palworld_terminal/adapters/palworld_rest.py` 模块 docstring
- `docs/commands.md`、`docs/configuration.md`
- `metadata.yaml` version

## 2. 范围

**In（本期交付）**：Palworld 官方 REST 的 7 个管理写端点全部落地 + 二次确认 + 审计（落库 + 前端只读查看页）。

**7 写端点**（Palworld `POST /v1/api/<X>`）：`announce` · `save` · `kick` · `unban` · `ban` · `shutdown` · `stop`。

**Out（非目标 / YAGNI）**：
- 不做定时/自动化写操作（无「每晚自动存档」之类调度）——写是请求驱动。
- 不做审计记录的删除/导出/前端筛选高级功能（本期只读倒序展示最近 N 条）。
- 不改现有只读命令与轮询采集链路。
- 不引入 RCON/WebSocket 通道（纯 REST）。

## 3. 命令面

| 命令 | 组 | 危险级 | 语法 | 说明 |
|---|---|---|---|---|
| `/pal announce <消息>` | basic | 低 | 消息为剩余整串 | 全服广播 |
| `/pal save` | basic | 低 | 无参 | 存档 |
| `/pal kick <名字\|userid> [理由]` | basic | 中 | 首 token=目标，其余=理由 | 踢人（可重连） |
| `/pal unban <userid>` | basic | 中 | 单 userid | 解封 |
| `/pal ban <名字\|userid> [理由]` | danger | 高 | 首 token=目标，其余=理由 | 封禁 |
| `/pal shutdown <秒> [公告]` | danger | 高 | 首 token=秒(int)，其余=公告 | 倒计时关服 |
| `/pal stop` | danger | 高 | 无参 | 强制停服（不存档） |
| `/pal confirm` | 控制命令 | — | 无参 | 确认待执行的高危操作 |

**参数解析**：沿用现有 `server_arg` / 首词自解析风格。`announce` 的消息、`kick`/`ban` 的理由为「剩余整串」（保留空格）。`shutdown` 秒数非法（非正整数）回用法提示。所有写命令支持显式 `@server` 覆盖（复用现有 `server_arg` 解析）定位目标服务器。

**目标玩家解析（kick/ban）**：
- 首 token 若匹配 `steam_...` 之类 userid 形态 → 直接用作 userid。
- 否则视为**角色名**：执行时**实时** `GET /players` 该服务器，按 `name` 精确匹配求 userid。
  - 唯一命中 → 用其 userid。
  - 多个同名 → 回候选列表（名 + userid 尾段），提示改用精确 userid。
  - 零命中 → 回「未找到在线玩家 <名>，可用 `/pal online` 查看或直接传 userid」。
- 实时拉取的明文 userid **用完即弃**，不落库明文（隐私模型不破）。

## 4. 安全模型（三层，复用 PR #18 地基）

### 4.1 特性开关（默认全关）
两个默认关的 feature 组，仅 AstrBot 设置页/配置可开：
- `server_admin_basic` = {announce, save, kick, unban}
- `server_admin_danger` = {ban, shutdown, stop}

命令按组归属（`command_registry.COMMANDS`）；`@_gated` 装饰器自动对未启用组回 `feature_disabled`。运营者可只开 basic 不暴露 danger。`confirm` 归属**核心控制命令**（core 组，恒注册），仅在存在 danger pending 时有实际效果；danger 组关闭时无 pending 可确认，`confirm` 恒回「无待确认操作」，无害。

**注**：写命令**不进** `feature_groups.ENDPOINT_GROUP`/`active_endpoints`（那是轮询侧）——写是请求驱动，不参与周期采集。

### 4.2 硬编码授权门（不可意外敞开）
7 个写命令 + `confirm` **全部硬编码仅 `permission_admins` 名单成员**：命令方法体内 `if not is_admin: return L("admin_required")`（照 `server` add/remove 范式，`is_admin` 由 handler lambda 传入 `c.commands.is_plugin_admin(sender_id)`）。

- **不依赖**可选的 `admin_only_commands` 门（那是只读命令的可选锁；对写命令冗余，即便配了也是 no-op，硬编码门恒生效）。
- 空名单 → 无人可执行（fail-closed）。
- 私聊 + `AccessMode` restricted → 经 `RoutingService.resolve` 天然拒（复用现有授权判定）。

### 4.3 可选二次确认（仅 danger 组）
新配置 `require_confirmation`（bool，默认 **false**）。

**开启时**，danger 组命令（ban/shutdown/stop）走两步：
1. **首发**：校验 admin + 组启用 + 参数合法 + 目标解析成功后，**不执行**，把待执行动作存入内存 pending，回预览「⚠️ 将对 <服务器> 执行 <动作摘要>；<超时>秒内回 `/pal confirm` 确认」。
2. **`/pal confirm`**：查该 sender 的 pending；存在且未过期 → 执行存好的动作 → 清 pending → 回结果；否则回「无待确认操作或已超时」。

**关闭时**：danger 命令直接执行。basic 组**永不**需确认。

**pending 状态**：
- 内存态（插件实例级 dict），键 = sender 复合 id（`平台:账号`），值 = (动作、已解析参数含 userid、目标服务器、过期时刻)。
- 每管理员**同时只保留一条** pending；新 danger 命令覆盖旧的。
- 过期时刻 = `clock.now + confirmation_timeout`；`confirm` 时按 clock 判过期。
- 重启不保留（跨重启确认无意义，stale 即弃）。

**不可锁集扩张**：`confirm` **和 7 个写命令**全部列入不可锁集（与现有 `server`/`whoami`/`help` 同列）。理由：写命令受 4.2 硬编码 admin 门管，可选的 `admin_only_commands` 锁对它们是冗余 no-op；把它们排除出可锁集，避免管理员在设置页误以为需/可配置它们的锁。工程后果（关键一致性）：
- `PAL_COMMAND_STRINGS` 含 7 写 + confirm（`command_names_test` 锚定 main.py 注册，必含）。
- `LOCKABLE_COMMANDS = PAL_COMMAND_STRINGS − 不可锁集` → **仍只含只读命令**（写命令被减掉）。
- 前端 `PAL_COMMANDS`（跨端锚定 `LOCKABLE_COMMANDS`）→ 仍只只读命令，命令锁 chip 网格**不出现写命令**，跨端锚定测试不破。
- `config._NON_LOCKABLE` 与 `command_registry` 两处不可锁集定义须同步扩张到 `{server, whoami, help, confirm, announce, save, kick, unban, ban, shutdown, stop}`；PR #18 新增的 M1 锚定测试（`_NON_LOCKABLE == frozenset(PAL_COMMAND_STRINGS) − set(LOCKABLE_COMMANDS)`）会强制两处一致，漏改即红。

## 5. 审计（落库 + 前端只读查看）

### 5.1 表结构（migration_0004）
新表 `admin_audit`：

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `ts` | INTEGER | epoch 秒（clock） |
| `admin_id` | TEXT | 管理员复合 id `平台:账号`（名单本就明文，与配置一致） |
| `action` | TEXT | announce/save/kick/unban/ban/shutdown/stop |
| `server_name` | TEXT | 目标服务器名 |
| `target_name` | TEXT NULL | 目标角色名（kick/ban 有；明文，便于人读） |
| `target_hash` | TEXT NULL | 目标 userid 经现有 `hash_user_id`（+salt）单向 hash；不存明文 |
| `detail` | TEXT NULL | 补充（如 shutdown 秒数、理由摘要；不含敏感） |
| `success` | INTEGER | 1/0 |
| `error` | TEXT NULL | 失败时脱敏错误类别（不含凭证/URL/host） |

每次写操作（无论成败）落一行。目标 userid **仅以 hash 落库**，明文用完即弃——与只读采集侧隐私模型一致。

### 5.2 前端只读审计页
- 新 web 端点（只读）：照 `web_api.handle_status_overview` 范式加 `handle_audit_list(container, limit)`，返回最近 N 条（默认 100，倒序），经 `_has_identity`（`g.username`）鉴权，路由注册于 `main.py`（照现有状态/配置端点）。
- 设置页新增「审计」章（`chapters.ts` 加 `kind` 只读观测，照状态页 `StatusPanel` 只读模式）：表格列 时间 / 管理员 / 动作 / 目标（角色名，userid hash 尾段辅助去歧义）/ 服务器 / 结果。**无编辑/保存往返**。
- 空态：「暂无管理操作记录」。

## 6. 分层实现映射（沿用 DDD 骨架）

| 层 | 改动 |
|---|---|
| `adapters/palworld_rest.py` | 加 `async def post(self, path, json_body) -> RestResponse`，复用现有 auth/CF头/超时/脱敏骨架；写端点路径用独立常量表，**不进** `EndpointName` 轮询枚举 |
| `application/admin_service.py`（新） | `AdminService`：持 `RoutingService`（`.resolve` 定位服务器）+ 目标服务器 rest client（`fetch(PLAYERS)` 名字解析 + `post` 执行）+ 审计 Repository。7 方法 announce/save/kick/unban/ban/shutdown/stop，各返回结果 DTO |
| `container.py` | 加 `_post` 回调（照 `_fetch`）+ 装配 `AdminService` 注入 `Commands` |
| `adapters/sqlite_repository.py` + `infrastructure/migrations.py` | `admin_audit` 表 + `insert_audit(...)` / `list_audit(limit)` |
| `presentation/commands.py` | 加 7+1 方法（硬编码 is_admin 门 + 组 gated + 目标解析 + 确认分支调 AdminService） |
| `presentation/command_registry.py` | `COMMANDS`（basic/danger 两组 + confirm 归 core）/`HELP_LINE`/`PAL_COMMAND_STRINGS` 三表同步（+8 串）；不可锁集扩张到含 7 写 + confirm（见 4.3），故 `LOCKABLE_COMMANDS` 仍只只读命令 |
| `main.py` | 加 8 个 `@pal.command` handler 走 `_guarded_cmd` 并传 `is_admin`；pending 内存态 + `confirm` 编排；改「只读」描述串与版本 |
| `presentation/locale.py` | 新文案（各命令用法/成功/失败/确认预览/无 pending/目标未找到/候选列表等） |
| `presentation/web_api.py` + `config_view.py` | `handle_audit_list` 只读端点 + 审计行 DTO 整形 |
| `config.py` + `_conf_schema.json` | `FeaturesConfig` 加两组 + 新 `server_admin` 配置段；schema 同步（默认关/默认值） |
| `frontend/src/**` | 两组开关进「功能分组」章；`server_admin` 段（确认开关+超时）；新「审计」只读章；单文件产物重建 |
| 文档/版本 | README/commands/configuration 改写 + 版本四源 v0.9.0 |

## 7. 配置项

新 `server_admin` 配置段：
- `require_confirmation`：bool，默认 `false`。开启则 danger 组需二次确认。
- `confirmation_timeout`：int 秒，默认 **30**，可配（合理范围校验，如 5–600）。

两 feature 组开关：`features.server_admin_basic`（默认 false）、`features.server_admin_danger`（默认 false）。

## 8. 错误处理与脱敏

- REST `post` 失败沿用现有 `RestResponse` 脱敏（`error` 不含凭证/URL/host），命令层映射为友好文案 + 落审计（success=0, error=类别）。
- 目标解析失败（未找到/重名/服务器未就绪）在执行前拦截，回明确提示，**不落审计**（未实际发起写）。
- danger 命令首发（确认模式）成功进 pending **不落审计**；真正执行时才落。

## 9. 测试策略

- **AdminService**：FakeRestClient 驱动 7 写路径；名字解析（唯一/重名/零命中/直传 userid）；post 失败映射。
- **确认状态机**：关闭直执；开启 首发→pending→confirm→执行；超时；无 pending；覆盖旧 pending；basic 组不受确认影响。
- **授权门**：非名单成员拒；组关闭拒（`feature_disabled`）；私聊 restricted 拒；空名单 fail-closed。
- **审计**：每写落一行；目标 userid 只 hash 不明文；成败/错误类别正确；`list_audit` 倒序 + limit。
- **前端**：审计章只读渲染（含空态）；两组开关；`server_admin` 段；命令锁 chip 网格**不含**写命令（已定：写命令进不可锁集 → 不在 `LOCKABLE_COMMANDS`/`PAL_COMMANDS`，见 4.3）。
- **跨端锚定**：`PAL_COMMAND_STRINGS` +8；`command_names_test` 锚定 main.py 注册；只读承诺文案锚点更新（readme_test）。
- **命名空间冒烟**：新命令纳入 `namespace_runtime_smoke_test`（组需开启才跑到深分支）。

## 10. 版本

`v0.8.7 → v0.9.0`，四源同步（metadata.yaml / main.py @register / `__init__.py` / README 徽章）。

## 11. 风险与开放项

- **冒充/归属**：Palworld REST 无操作者身份校验；审计记录的是「哪个受托管理员通过 bot 发起」，非游戏内身份。可接受（与 players 组 bind 冒充同属已知项）。
- **danger 组 + 确认关闭**：管理员手滑 stop 丢档——已用「默认关组 + 硬编码门 + 可选确认」三重降低，最终信任授权管理员。文档须显著告警 stop 不存档。
- **名字解析实时依赖 /players**：目标服务器不可达时 kick/ban 无法按名解析——回明确错误，允许直传 userid 兜底。
