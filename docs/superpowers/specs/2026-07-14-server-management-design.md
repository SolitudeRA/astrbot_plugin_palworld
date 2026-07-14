# 服务器管控设计（全量写操作 + 权限门 + 二次确认 + 审计）

> 状态：**已过三视角对抗复核并修订**（正确性/一致性、安全/隐私、AstrBot 平台兼容）· 目标版本 **v0.9.0** · 依赖已合并的 PR #18 权限管理

## 1. 定位转变（产品级）

插件从**只读监测**正式跨入**读写管控**。这是里程碑变更（v0.8.7 → **v0.9.0**）。

当前多处硬承诺「只读，仅调用官方只读端点，不控制服务器、不执行任何写/管理操作」必须改写为受控写定位：**写操作默认全部关闭、仅授权管理员可用、全程落库审计**。承诺从「绝不写」降级为「受控写」。

需同步改写「只读」文案的位置（对抗复核须核这份清单不漏）：
- `README.md`（L13/L15/L33/L63/**L98 最强声明**、版本徽章、命令计数）
- `main.py` `@register(...)` 描述串（L81 含「(只读)」）与版本参数
- `palworld_terminal/__init__.py` 包 docstring + `__version__`
- `palworld_terminal/adapters/palworld_rest.py` 模块 docstring
- `frontend/src/App.vue` 副标题（现「Palworld 服务器监测 · 只读」，复核视角3 m1）
- `docs/commands.md`、`docs/configuration.md`
- `metadata.yaml` version
- **`tests/unit/readme_test.py` 硬锚点**：现断言 README 含 `"不控制服务器"`（readme_test.py:15）——改写只读文案须同步改该锚点短语，否则 CI 红（PR#13 前车之鉴）。

## 2. 范围

**In（本期交付）**：Palworld 官方 REST 的 7 个管理写端点全部落地 + 二次确认 + 审计（落库 + 前端只读查看页）。

**7 写端点**（Palworld `POST /v1/api/<X>`）：`announce` · `save` · `kick` · `unban` · `ban` · `shutdown` · `stop`。

**Out（非目标 / YAGNI）**：
- 不做定时/自动化写操作（无「每晚自动存档」之类调度）——写是请求驱动。
- 不做审计记录的**手动**删除/导出/前端筛选高级功能（本期只读倒序展示最近 N 条）；但有**自动留存清理**（`audit_retention_days`，§5.1/§7）。
- 不改现有只读命令与轮询采集链路。
- 不引入 RCON/WebSocket 通道（纯 REST）。

## 3. 命令面

| 命令 | 组 | 危险级 | 语法 | 说明 |
|---|---|---|---|---|
| `/pal announce <消息>` | basic | 低 | 消息为剩余整串 | 全服广播 |
| `/pal save` | basic | 低 | 无参 | 存档 |
| `/pal kick <名字\|userid> [理由] [@server]` | basic | 中 | 目标+理由 | 踢人（可重连） |
| `/pal unban <userid> [@server]` | basic | 中 | 单 userid | 解封 |
| `/pal ban <名字\|userid> [理由] [@server]` | danger | 高 | 目标+理由 | 封禁 |
| `/pal shutdown <秒> [公告] [@server]` | danger | 高 | 秒(int)+公告 | 倒计时关服 |
| `/pal stop [@server]` | danger | 高 | 无参 | 强制停服（不存档） |
| `/pal confirm` | 控制命令（core） | — | 无参 | 确认待执行的高危操作 |

**参数解析（复核视角1 M5 / 视角3 m1/m2 修订）**：
- **`@server` 覆盖只能置于命令末尾**（现有 `server_arg.parse_arg` 只把 `tokens[-1]` 的 `@x` 当覆盖，`server_arg.py:37-42`）。文档须明写该词序，修正早前 `/pal kick @serverB Alice` 的错误示例为 `/pal kick Alice 理由 @serverB`。
- **已知限制（须文档告警）**：`announce` 消息、`kick`/`ban` 理由是自由文本整串，若**恰以 `@词` 结尾**（如 `/pal announce 快来 @discord`、`/pal ban Alice 作弊 @群`）会被误当服务器覆盖而截断/解析失败。规避：写命令的自由文本不要以 @词 收尾，或显式把 `@server` 放最末。
- **空白折叠**：`parse_arg` 走 `body.split()` + `" ".join()`（`server_arg.py:35,44`），连续空格/换行会塌成单空格。故 announce/理由**不保证逐字保留**原始空白——spec 早前「保留空格」措辞收回，改为「折叠为单空格」。
- `shutdown` 秒数须为正整数且 **有上界**（如 1–86400，复核 m3），越界回用法提示。

**目标玩家解析（kick/ban）**：
- 首 token 若匹配 **Palworld userid 平台前缀形态**（如 `steam_<17位数字>`，spec 须钉死可识别前缀集）→ 直接用作 userid。角色名恰好长得像该形态属边界，文档提示冲突时可显式改传其他形态或走候选列表（复核 M-a）。
- 否则视为**角色名**：执行时**实时** `GET /players` 该服务器，读原始响应的 **`userId` 字段**（`privacy_filter.py:56` 用的即此字段名；非 `name`——`name` 仅用于匹配），按 `name` 精确匹配求其 `userId`。
  - 唯一命中 → 用其 userid。
  - 多个同名 → 回候选列表（名 + userid 尾段），提示改用精确 userid。
  - 零命中 → 回「未找到在线玩家 <名>，可用 `/pal online` 查看或直接传 userid」。
- 该实时 `fetch(PLAYERS)` **绕过 `QueryService`/`redact_players` 隐私过滤**（写操作需真 userid，属必需）；意味着 `/pal me hide`/`exclude_names` 的玩家对管理员仍可按名解析——对服务器运营者合理（管理员本可从游戏内看到全部在线），**不构成** PR#9 面向同侪玩家的存在性红线。§11 显式声明此边界。
- 实时拉取的明文 userid **用完即弃**，不落库明文、不进日志（隐私模型不破）。

## 4. 安全模型（复用 PR #18 地基）

### 4.1 特性开关（默认全关）
两个默认关的 feature 组，仅 AstrBot 设置页/配置可开：
- `server_admin_basic` = {announce, save, kick, unban}
- `server_admin_danger` = {ban, shutdown, stop}

命令按组归属（`command_registry.COMMANDS`）。运营者可只开 basic 不暴露 danger。`confirm` 归属**核心控制命令**（core 组，恒注册），仅在存在 danger pending 时有实际效果；danger 组关闭时无 pending 可确认，`confirm` 恒回「无待确认操作」，无害。

**注**：写命令**不进** `feature_groups.ENDPOINT_GROUP`/`active_endpoints`（那是轮询侧）——写是请求驱动，不参与周期采集。

### 4.2 中央写命令门 `_guarded_admin`（单一 choke point，复核视角2 M1/M2）
**不给 8 个写 handler 各自接线**（逐个复制易漏 is_admin 传参 → 无鉴权的 stop/ban）。所有写命令经**一个**中央门，8 命令只提供「动作闭包」。门内**严格按序**：

1. **admin 硬门（最先，先于 feature 门）**：`if not is_admin: return L("admin_required")`。非管理员**一律** `admin_required`，与组开关状态无关——避免复核视角2 M1 的「非管理员据 `feature_disabled` vs `admin_required` 反推危险组是否开启」的配置态泄漏。
2. **feature 组门**：admin 通过后才判 `features.enabled(该命令组)`；未启用回 `feature_disabled`。
3. **服务器解析 + 授权**：`RoutingService.resolve`（复用只读侧授权：私聊 restricted 拒、群授权名单、`@server` 覆盖）。
4. **参数/目标解析**：kick/ban 实时解析目标 userid（§3）；解析失败在此拦截、不落审计。
5. **确认编排**：danger 组 + `require_confirmation` → 存 pending 回预览（见 4.4）；否则直执。
6. **执行 + 审计**：调 `AdminService` 发 POST；无论成败落一行审计（§5）。

- **不依赖**可选的 `admin_only_commands` 门（那是只读命令的可选锁；对写命令冗余 no-op，硬编码门恒生效）。
- 空名单 → 无人可执行（fail-closed，`is_plugin_admin` 对空集恒 False）。
- **锚定测试**：每个写命令 handler 必过 `_guarded_admin`（不是 `_guarded`/`_guarded_cmd`）——加静态/运行时断言防漏接。

### 4.3 硬编码授权门与门序小结
7 写 + `confirm` 全部硬编码仅 `permission_admins` 名单成员（`is_admin` 由 handler 传入 `c.commands.is_plugin_admin(sender_id)`）。门序 = **admin → feature → 授权 → 目标 → 确认 → 执行**（4.2）。`confirm` 自身也过 admin 硬门。

### 4.4 可选二次确认（仅 danger 组）
新配置 `require_confirmation`（bool，默认 **false**）。

**开启时**，danger 组命令（ban/shutdown/stop）走两步：
1. **首发**：过 admin+组+授权+参数+目标解析后，**不执行**，存 pending，回预览「⚠️ 将对 <服务器> 执行 <动作+目标角色名+userid 尾段+摘要>；<超时>秒内回 `/pal confirm` 确认」（预览**须含目标角色名与 userid 尾段**，消同名歧义，复核视角2 M5）。
2. **`/pal confirm`**：**claim-then-execute（复核视角3 M3 防双执行竞态）**——先**原子 pop** 该 sender 的 pending（先摘走再 await 执行），避免两条快速 confirm 都读到未清 pending 致 double-stop/double-ban。取到后**执行前复检**：
   - (a) sender 仍在 `permission_admins`（confirm 自身 admin 硬门已保证）；
   - (b) **该动作所属 danger 组仍 enabled**（复核视角2 B1 / 视角1 M2：首发后运营者关组则丢弃）；
   - (c) **对目标服务器重跑 `RoutingService.resolve` 授权**（复核视角2 B1/m4：撤群授权/跨上下文则丢弃）。
   - 任一不满足 → 丢弃 pending，回明确文案「待确认操作已失效（权限/组状态变更）」。
   - 全过 → 执行 → 回结果，**成功文案回显「已执行：<动作+目标角色名+userid 尾段+服务器>」**（复核视角2 M5），失败回脱敏错误。
   - 无 pending / 已过期 → 回「无待确认操作或已超时」。

**关闭时**：danger 命令直接执行。basic 组**永不**需确认。

**pending 状态与生命周期**：
- 内存态，键 = sender 复合 id（`平台:账号`），值 = (动作、已解析参数含 userid、目标服务器、**首发上下文 umo**、过期时刻)。**存储与过期判定下沉到持有注入 clock 的层**（`Commands` 或专门 `ConfirmationStore`，**不在 `main.py`**——main 无注入 clock，会逼超时用例 sleep；复核视角1 M1）。过期 = `clock.now + confirmation_timeout`。
- 每管理员**同时只保留一条** pending；新 danger 命令覆盖旧的（覆盖后 confirm 回显消歧，见 4.4）。
- **配置热重载须主动清空 pending**（复核视角2 B1 / 视角3 M4 / 视角1 M2）：`main.py:_apply_and_restart` 只重建 `Container`、**不重建插件实例**，实例级 pending 会跨 reload 存活 → 关组/撤权后旧 pending 仍可确认。故 `_apply_and_restart` 成功后须清 pending（复检 (b)(c) 是第二道保险）。
- 跨进程重启不保留（stale 即弃）。

**跨管理员隔离（复核确认稳）**：键含 sender 复合 id，A 的 confirm 查不到 B 的 pending；空账号 `endswith(":")` 进不了名单，无法建 pending。

**不可锁集扩张**：`confirm` **和 7 个写命令**全部列入不可锁集（与现有 `server`/`whoami`/`help` 同列）。理由：写命令受硬编码 admin 门管，可选的 `admin_only_commands` 锁对它们是冗余 no-op；排除出可锁集避免管理员在设置页误配冗余锁。工程后果（关键一致性）：
- `PAL_COMMAND_STRINGS` 含 7 写 + confirm（`command_names_test` 锚定 main.py 注册，必含）。
- `LOCKABLE_COMMANDS = PAL_COMMAND_STRINGS − 不可锁集` → **仍只含只读命令**（写命令被减掉）。
- 前端 `PAL_COMMANDS`（跨端锚定 `LOCKABLE_COMMANDS`）→ 仍只只读命令，命令锁 chip 网格**不出现写命令**，跨端锚定测试不破。
- `config._NON_LOCKABLE` 与 `command_registry` 两处不可锁集定义须同步扩张到 `{server, whoami, help, confirm, announce, save, kick, unban, ban, shutdown, stop}`；PR #18 新增的锚定测试（`_NON_LOCKABLE == frozenset(PAL_COMMAND_STRINGS) − set(LOCKABLE_COMMANDS)`，`command_names_test.py:31`）会强制两处一致，漏改即红。
- **必须同步更新的硬编码断言（复核视角1 B1 / 视角3 M2）**：`tests/unit/command_names_test.py::test_lockable_excludes_non_lockable`（约 :22-25）**字面量硬编码**了旧不可锁集 `{"server","whoami","help"}`——不可锁集扩张后 `LOCKABLE = PAL − 12 ≠ PAL − 3`，该断言**必红**。须把字面量从 3 项改到 12 项。（`frontend_pal_commands_test` 确实不破，因 LOCKABLE 仍只只读命令。）

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
| `target_hash` | TEXT NULL | 目标 userid 单向 hash（见下 world_id 命名空间）；不存明文 |
| `detail` | TEXT NULL | 补充（如 shutdown 秒数、理由摘要；不含敏感） |
| `success` | INTEGER | 1/0 |
| `error` | TEXT NULL | 失败时脱敏错误类别（不含凭证/URL/host） |

每次写操作（无论成败）落一行。目标 userid **仅以 hash 落库**，明文用完即弃——与只读采集侧隐私模型一致。

**`target_hash` 的 hash 命名空间（复核视角1 M4 / 视角2 m2，必须钉死）**：`hash_user_id(salt, world_id, 明文 userid)` **需 world_id 作命名空间**（`privacy_filter.py:17,56`），只读侧 `redact_players` 即以 world_id 哈希。审计须用**目标服务器当前 world_id**（AdminService 经 `repo.get_current_world(server_id)` 取，照 `commands.py:61` 范式）——与观测侧同源，才能让 `target_hash` 尾段与玩家档案 hash 可合法对照溯源；误用 server_id/空串会使 hash 无意义。**装配前提**：`container.py` 须把 `salt` 注入 `AdminService`（现只注入了 `Commands`）。

**留存/清理（复核视角2 M3）**：`admin_audit` 存明文 `admin_id` + `target_name` + 时间，属长期 PII。加配置 `audit_retention_days`（默认 **180**，与观测侧有界清理对齐），随现有清理链（`HistoryConfig` 同款）定期删旧行，避免无限增长的可交叉去匿名表。

### 5.2 前端只读审计页（复核视角3 B1：非「照抄 StatusPanel」）
- **web 端点**：加 `web_api.handle_audit_list(container, limit)`（照 `handle_status_overview` 只读范式），返回最近 N 条（默认 100，倒序）。路由用 `self._context.register_web_api`（`main.py:115` 现有 API）注册，`_has_identity`→`g.username` 鉴权（避开 PR#6 `request.username` 恒 None 坑）。**须在 `_inflight`/`_idle` 门闩内查询 + guard `container None/restarting`**（照 `main.py:270` `_web_status`），`limit` 从 `request.args` 解析成 int 并 **clamp 上限**（防超大查询，复核视角3 m3）。审计行 DTO 整形在 `config_view.py`。
- **前端路由须改**（复核视角3 B1）：现 `App.vue:54-55` 硬编码 `chapter==='status'` 二分路由（`StatusPanel v-if chapter==='status'` / `SettingsPanel v-show chapter!=='status'`），**不看 `kind`**。审计章不能塞进这套：须(a)新建独立 `AuditPanel.vue`（自 fetch `/audit/list`、渲染只读表），(b)改 `App.vue` 路由为按 `kind`（或显式加审计分支）分派到 AuditPanel。`StatusPanel` 是服务器状态专用页、**不是通用只读表**，不可直接复用。
- **审计章**：`chapters.ts` 加只读章（`kind` 区分观测类），表格列 时间 / 管理员 / 动作 / 目标（角色名 + userid hash 尾段辅助去歧义）/ 服务器 / 结果。**无编辑/保存往返**。
- 空态：「暂无管理操作记录」。

## 6. 分层实现映射（沿用 DDD 骨架）

| 层 | 改动 |
|---|---|
| `adapters/palworld_rest.py` | 加 `async def post(self, path, json_body) -> RestResponse`，复用 auth/CF头/超时/脱敏骨架；**但成功判定须区别于 fetch**（复核视角1 M3）：容忍空 body / 非 JSON / 2xx 含 204，`shutdown`/`stop` 断连按「已发起」处理——**不照搬 fetch 200→强制 `resp.json()` 路径**（那会把成功写落审计为 success=0）。写端点路径用独立常量表，**不进** `EndpointName` 轮询枚举 |
| `application/admin_service.py`（新） | `AdminService`：持 `RoutingService`（`.resolve`）+ **`_fetch`/`_post` 回调（按 server_id 路由，非直接持 client——client 是 container 私有 `dict[server_id→client]`，命令层拿不到单个）** + 审计 `Repository` + **`salt`** + `repo.get_current_world`（审计 hash world_id）。7 方法各返回结果 DTO |
| `container.py` | 加 `_post` 回调（照 `_fetch` `:158`）+ 装配 `AdminService` 注入 `Commands`，**并注入 `salt`**（现只给 Commands） |
| `adapters/sqlite_repository.py` + `infrastructure/migrations.py` | `migration_0004` 建 `admin_audit` 表（现链止于 0003，`migrations_test` 用 `len(MIGRATIONS)` 动态断言，加 0004 安全）+ `insert_audit(...)` / `list_audit(limit)` / 留存清理 |
| **`presentation/formatters.py`（复核视角1 B2 / 视角3 M1，原 spec 漏列）** | `format_help`（:132-141）现只按组启用过滤、**无 per-command admin 门** → 组一开写命令对 guest 泄漏。须对 `server_admin_*` 组命令加 **is_admin 门**（enabled 且 is_admin 才列，或随 `_HELP_ADMIN_EXTRA` 模式仅 admin 段展示）。`confirm` 归 core 会恒进 help，须提供 `HELP_LINE["confirm"]` 否则 `HELP_LINE[name]` KeyError（且 confirm 是否也只对 admin 显示，一并定） |
| `presentation/commands.py` | 加 7+1 方法作**动作闭包**，经中央写门 `_guarded_admin`（§4.2）；pending 存储/过期判定持注入 `self._clock`（复核视角1 M1）；kick/ban 目标解析（§3） |
| `presentation/command_registry.py` | `COMMANDS`（basic/danger 两组 + confirm 归 core）/`HELP_LINE`（含 confirm）/`PAL_COMMAND_STRINGS` 三表同步（+8 串）；不可锁集扩张到含 7 写 + confirm（见 §4.4），故 `LOCKABLE_COMMANDS` 仍只只读命令 |
| `main.py` | 加中央写门 `_guarded_admin`（admin 硬门→feature→授权→目标→确认→执行+审计，§4.2）+ 8 个 `@pal.command` handler（提供动作闭包过该门）+ `confirm` handler；`_apply_and_restart` 成功后**清 pending**（§4.4）；改「(只读)」描述串与版本 |
| `presentation/locale.py` | 新文案（各命令用法/成功回显/失败/确认预览含目标/无 pending/已失效/目标未找到/候选列表等） |
| `presentation/web_api.py` + `config_view.py` | `handle_audit_list` 只读端点（门闩内 + guard None/restarting + limit clamp）+ 审计行 DTO 整形 |
| `config.py` + `_conf_schema.json` | `FeaturesConfig` 加两组字段 + **`enabled()` 字典同步加两键**（复核视角1 M6 / 视角3 m5：漏则 `_gated` 恒 disabled 静默失效）+ `_default_features` + 新 `server_admin` 配置段（`require_confirmation`/`confirmation_timeout`/`audit_retention_days`）；schema 同步（默认关/默认值，管理员实机可见）；前端 `schema.ts` FEATURE 段同步两组 |
| `frontend/src/**` | 两组开关进「功能分组」章；`server_admin` 段（确认开关+超时+留存天）；**新 `AuditPanel.vue` + `App.vue` 路由改（按 kind，复核视角3 B1）** + `chapters.ts` 审计只读章；单文件产物重建 |
| 文档/版本 | README/commands/configuration/App.vue 副标题/readme_test 锚点改写 + 版本四源 v0.9.0 |

## 7. 配置项

新 `server_admin` 配置段：
- `require_confirmation`：bool，默认 `false`。开启则 danger 组需二次确认。
- `confirmation_timeout`：int 秒，默认 **30**，可配（合理范围校验，如 5–600）。
- `audit_retention_days`：int 天，默认 **180**，审计留存上限（随现有清理链删旧行；复核视角2 M3）。

两 feature 组开关：`features.server_admin_basic`（默认 false）、`features.server_admin_danger`（默认 false）。**务必同步 `FeaturesConfig.enabled()` 字典**（否则组恒 disabled 静默失效，§6/§9）。

## 8. 错误处理与脱敏

- REST `post` 失败沿用现有 `RestResponse` 脱敏（`error` 不含凭证/URL/host），命令层映射为友好文案 + 落审计（success=0, error=类别）。
- 目标解析失败（未找到/重名/服务器未就绪）在执行前拦截，回明确提示，**不落审计**（未实际发起写）。
- danger 命令首发（确认模式）成功进 pending **不落审计**；真正执行时才落。

## 9. 测试策略

- **AdminService**：FakeRestClient 驱动 7 写路径；名字解析（唯一/重名/零命中/直传 userid/绕过隐私过滤取真 userId）；`post()` 成功判定（空 body/204/断连不误判为失败，复核视角1 M3）；post 失败映射。
- **中央写门 `_guarded_admin`（复核视角2 M1/M2）**：**门序**——非管理员一律 `admin_required`（与组开关无关，防配置态泄漏）；admin+组关→`feature_disabled`；admin+组开+非管理员不可达（矛盾态断言）；每写命令必过该门（防漏接锚定）。
- **确认状态机（复核视角2 B1/M5 · 视角3 M3 · 视角1 M1/M2）**：关闭直执；开启 首发→pending→confirm→执行；超时（**注入 clock 可测、无需 sleep**）；无 pending；覆盖旧 pending + confirm 回显消歧；**claim-then-execute**（两条快速 confirm 不 double-execute）；**confirm 复检**——首发后撤名单/关 danger 组/撤群授权 → pending 失效丢弃；**config 热重载清 pending**；basic 组不受确认影响。
- **授权门**：非名单成员拒；空名单 fail-closed；私聊 restricted 拒；OPEN 模式 admin 硬门仍在。
- **help 角色隔离（复核视角1 B2 / 视角3 M1）**：`server_admin_*` 组开启后，guest `/pal help` **不含**写命令；admin 可见；`HELP_LINE["confirm"]` 存在不 KeyError。
- **审计**：每写落一行；目标 userid 只 hash 不明文、**hash 用目标服务器 current world_id 命名空间**（与观测侧可对照）；成败/错误类别正确；`list_audit` 倒序 + limit clamp；留存清理删旧行。
- **前端**：`AuditPanel` 只读渲染（含空态）+ `App.vue` 按 kind 路由到审计页（复核视角3 B1）；两组开关；`server_admin` 段；命令锁 chip 网格**不含**写命令（写命令进不可锁集 → 不在 `LOCKABLE_COMMANDS`/`PAL_COMMANDS`，见 §4.4）。
- **跨端锚定**：`PAL_COMMAND_STRINGS` +8；`command_names_test` 锚定 main.py 注册；**更新 `command_names_test.py::test_lockable_excludes_non_lockable` 硬编码非锁集 3→12 项**（复核视角1 B1 / 视角3 M2）；`FeaturesConfig(server_admin_basic=True).enabled("server_admin_basic") is True`（复核视角1 M6）；只读承诺文案锚点更新（readme_test，含 `不控制服务器` 短语）。
- **命名空间冒烟（复核视角3 M5 / 视角1 M-c）**：新命令纳入 `namespace_runtime_smoke_test`——`_FakeRest` 补 `post()` + `fetch(PLAYERS)` stub（否则 AttributeError）；features 种子加 `server_admin_basic/danger: True` + 种在线玩家供名字解析；`calls` 清单 + docstring 命令数更新（现 18 → 26）。

## 10. 版本

`v0.8.7 → v0.9.0`，四源同步（metadata.yaml / main.py @register / `__init__.py` / README 徽章）。

## 11. 风险与开放项

- **冒充/归属**：Palworld REST 无操作者身份校验；审计记录的是「哪个受托管理员通过 bot 发起」，非游戏内身份。可接受（与 players 组 bind 冒充同属已知项）。
- **OPEN 访问模式 × server_admin 爆炸半径（复核视角2 M4，必须文档强告警）**：`permission_admins` 是**全局**名单；RESTRICTED（默认）下 `@server` 覆盖仍受群授权名单约束，但 **`AccessMode.OPEN` 下 `_authorized` 恒 True（`routing_service.py:32`）→ 任一管理员可从任意群/私聊对任意就绪服务器 stop/ban，零群授权约束**。文档须显著劝阻「OPEN + danger 同开」，说明多群共享同一 bot 时的爆炸半径。
- **danger 组 + 确认关闭**：管理员手滑 stop 丢档——已用「默认关组 + admin 硬门 + 可选确认」三重降低，最终信任授权管理员。文档须显著告警 stop 不存档。
- **名字解析实时依赖 /players**：目标服务器不可达时 kick/ban 无法按名解析——回明确错误，允许直传 userid 兜底。
- **名字解析绕过隐私过滤（可接受，已声明）**：AdminService 直读 `/players` 原始 `userId` 绕过 `redact_players`——写操作必需真 userid；被 `/pal me hide`/`exclude_names` 的玩家对管理员仍可按名 kick/ban。对服务器运营者合理（管理员本可从游戏内看到全部在线），**不构成** PR#9 面向同侪玩家的存在性红线。
- **审计留存**：默认 180 天有界清理（§7）；运营者可调。审计表含明文 admin_id/target_name，属受控 PII。
- **确认目标漂移（残余，已缓解）**：confirm 模式下 pending 存的是首发时解析的 userid；超时窗口（默认 30s）内目标下线/同名顶替，confirm 仍踢原 userid。已用「预览带 userid 尾段 + confirm 回显 + 短超时」缓解；不做执行时重解析（会引入首发/确认目标不一致的更大困惑）。
