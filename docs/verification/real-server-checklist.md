# PalChronicle v0.1 实服验证清单

> 对应设计规格 `docs/superpowers/specs/2026-07-10-palchronicle-v0.1-design.md` 的
> **§21.2 待实服/框架验证清单**（6 项外部事实）与 **§19 验收标准**。
>
> 规格对这些未经证实的外部事实一律采用"保守默认 + 降级"实现；本清单给出：
> 每项**验证什么、怎么验证、当前代码的保守默认（文件 + 函数/常量锚点）、结果不符时改哪里**。
> 逐项完成后勾选 checkbox。
>
> **引用约定**：代码引用一律采用 `文件路径` + `函数名()/方法名()/常量名` 锚点，
> 以抗行号漂移；仅 JSON 配置键等无函数上下文的引用使用键路径。

---

## 1. 前置准备

### 1.1 搭建启用 REST API 的 Palworld 测试服

- [ ] 安装 Palworld Dedicated Server（Steam appid `2394010`，`PalServer`）。
- [ ] 编辑 `Pal/Saved/Config/<平台>/PalWorldSettings.ini`（Windows 为 `WindowsServer`，Linux 为 `LinuxServer`），在 `OptionSettings=(...)` 中确认/加入：
  - `RESTAPIEnabled=True`
  - `RESTAPIPort=8212`（插件默认 `base_url` 即 `http://127.0.0.1:8212`，见 `_conf_schema.json` 的 `servers` 模板 `base_url` 默认值）
  - `AdminPassword="<强密码>"`（REST Basic Auth 的密码；用户名固定 `admin`）
- [ ] 重启服务器后确认 REST 可达（Basic Auth 用户名 `admin`）：

  ```bash
  curl -u admin:<AdminPassword> http://127.0.0.1:8212/v1/api/info
  ```

  插件访问的 5 个端点均为 `GET /v1/api/<path>`（`palworld_terminal/adapters/palworld_rest.py` 的 `_ENDPOINT_PATH` 常量）：
  `info` / `metrics` / `players` / `settings` / `game-data`。
- [ ] 逐个 curl 上述 5 个端点确认全部返回 200——**尤其是 `/v1/api/game-data`**（本清单第 2.1–2.4、2.6 节全部依赖它；不同服务器版本可能不提供该端点）。
- [ ] 安全边界：REST 端口**不要暴露公网**，仅 localhost/内网/VPN（对齐 `README.md`「安全与隐私」节与规格 §15 网络提示）。

### 1.2 插件侧最小配置

按 `_conf_schema.json` 顶层结构，在 AstrBot 插件配置页填写（等价 JSON）：

```jsonc
{
  "servers": [
    {
      "name": "testsv",                       // 唯一、不含空格/冒号/@（config.py 的 _parse_servers() 非法则被跳过）
      "enabled": true,
      "base_url": "http://127.0.0.1:8212",
      "username": "admin",
      "password_env": "PALWORLD_TEST_PASSWORD" // 推荐环境变量；解析见 config.py 的 _resolve_password()
    }
  ],
  "routing": { "access_mode": "open", "default_server": "testsv" }
}
```

- [ ] 在 AstrBot 进程环境中设置 `PALWORLD_TEST_PASSWORD=<AdminPassword>` 后再启动。
- [ ] 说明：`access_mode: "open"` 便于先跑通查询；验证 §19 的 restricted 授权项（第 3.1 节）时需切回默认 `restricted`。
- [ ] 其余配置全部留默认即可：轮询默认 metrics/players 30s、info 600s、settings 1800s、game-data 120s（`palworld_terminal/config.py` 的 `parse_config()` PollingConfig 默认值）。

### 1.3 观察点速查（验证时反复用到）

| 观察点 | 位置 |
|---|---|
| SQLite 数据库 | `<StarTools.get_data_dir()>/palworld_terminal.sqlite3`（`palworld_terminal/container.py` 的 `Container.start()`；data_dir 解析见 `main.py` 的 `_resolve_data_dir()`，通常在 AstrBot 的 `data/plugin_data/astrbot_plugin_palworld/` 下） |
| HMAC salt 文件 | 同目录 `secret_salt`（`palworld_terminal/infrastructure/salt.py` 的 `_SALT_FILENAME` 常量），永不入库/入日志 |
| 采集侧日志 | logger `palworld_terminal.snapshot`（`palworld_terminal/application/snapshot_service.py` 模块级 `_log`） |
| 元数据目录 | 插件**安装目录**下的 `metadata/`（`palworld_terminal/` 包的上一级；`container.py` 的 `Container.start()` 以 `Path(__file__).resolve().parent.parent / "metadata"` 解析）。注意：与 data_dir 无关，metadata 随插件包分发 |

- [ ] 查库一律用只读方式，避免与插件写连接争锁：

  ```bash
  sqlite3 "file:palworld_terminal.sqlite3?mode=ro" ".tables"
  ```

---

## 2. 六项待验证事实（规格 §21.2 逐项）

### 2.1 `/players.userId` 与 `/game-data.userid` 是否同值

**验证什么**：两个端点对同一在线玩家给出的原始 id 是否完全一致（规格 §21.2-1；影响身份关联策略）。

**怎么验证**：
- [ ] 保证至少 1 名玩家在线，分别抓取两端点：

  ```bash
  curl -su admin:$PW http://127.0.0.1:8212/v1/api/players   > players.json
  curl -su admin:$PW http://127.0.0.1:8212/v1/api/game-data > game-data.json
  ```

- [ ] 对比 `players.json` 中 `players[].userId` 与 `game-data.json` 中 Player 类型 actor（`type == "Player"`，取值枚举见 `palworld_terminal/domain/enums.py` 的 `UnitType`）的 `userid` 字段：值、大小写、前缀（如 `steam_`）是否逐字符一致。
- [ ] 顺带记录 `playerId` 是否存在及其格式（`player_key` 的一级回退源，见下）。
- [ ] 备注：规格 §21.2-1 提到"首启自检"，当前实现**未内置该自检**，本节以手工 curl 对比替代（见第 4 节注意点 3）。

**当前保守默认**：
- `player_key` 唯一主源是 `/players.userId`：`palworld_terminal/application/player_service.py` 的 `_resolve_identity()`（回退顺序 `userId` → `playerId` → 角色名小写且 `id_confidence=low`）。
- game-data 的 `userid` 被单独解析（`palworld_terminal/adapters/normalizer.py` 的 `normalize_game_data()`，`player_userid` 字段）并 HMAC 脱敏（`palworld_terminal/adapters/privacy_filter.py` 的 `redact_game_data()`），但**不用于生成 `player_key`**，仅 best-effort（规格 §10.1）。

**结果处置**：
- 相符 → 维持现状；可在 v0.2 放宽为直接用 game-data `userid` 关联 Player actor 与玩家身份（改 `player_service.py` 中 game-data 侧关联路径与 `_resolve_identity()` 的注释约定）。
- 不符 → 现状即正确行为，无需改动；在规格 §21.2 处记录实测结论即可。

### 2.2 `InstanceID` 重启稳定性 与 `TrainerInstanceID`/`TrainerNickName` 存在性

**验证什么**：`InstanceID` 在服务器重启后是否保持不变；各 UnitType（`Player`/`OtomoPal`/`BaseCampPal`/`WildPal`/`NPC`）的 actor 是否带 `TrainerInstanceID`/`TrainerNickName` 字段（规格 §21.2-2；影响随行帕鲁/据点关联）。

**怎么验证**：
- [ ] 玩家带随行帕鲁在线时抓取 `game-data.json`，按 `type` 分组统计每组内 `InstanceID`/`TrainerInstanceID`/`TrainerNickName` 的存在率（jq 或脚本）。
- [ ] 记下某玩家与其随行帕鲁的 `InstanceID` → 重启 Palworld 服务器（玩家重进）→ 再抓一次，对比两次 `InstanceID` 是否相同。
- [ ] 验证插件侧关联效果：`OtomoPal.trainer_instance_id` 能否命中某 Player 的 `instance_id`（关联逻辑 `palworld_terminal/application/player_service.py` 的 `link_companions()`）。

**当前保守默认**：
- normalizer 对这些字段宽容读取，缺失 → `None`（`palworld_terminal/adapters/normalizer.py` 的 `normalize_game_data()`）。
- 关联失败 → 不关联、不新建身份；`companion_class` 保持 `NULL` 落库（`player_service.py` 的 `apply_players()` 写观察记录时 `companion_class=None`），不阻断快照（规格 §10.1）。

**结果处置**：
- `TrainerInstanceID` 不存在/不可靠 → 改 `link_companions()`（`player_service.py`）改用 `trainer_nickname` 与 `/players.name` 匹配（normalizer 的 `normalize_game_data()` 已解析该字段）。
- `InstanceID` 重启后不稳定 → v0.1 无影响（未做持久键）；但 v0.2 随行帕鲁长期统计**不得**以 `InstanceID` 为持久键，需在 v0.2 设计中标注。

### 2.3 PalBox 是否总提供可用坐标与 `GuildID`

**验证什么**：game-data 中 PalBox 条目的 `LocationX/Y/Z` 与 `GuildID`/`GuildName` 是否总是非空（规格 §21.2-3；影响据点推导可靠性）。

**怎么验证**：
- [ ] 在有多个公会、多个据点的存档上抓 `game-data.json`，统计 PalBox 条目中坐标三元组与 `GuildID` 的缺失率。
- [ ] 开插件跑 ≥ 3 个 game-data 采集周期（默认 3×120s）后查库：

  ```sql
  SELECT palbox_key, guild_key, position_cell FROM palboxes;
  SELECT base_key, guild_key, confidence FROM bases;
  ```

  预期：每个游戏内据点对应一行 `palboxes`；`bases.confidence` 大多为 `high`/`medium`。
- [ ] `/pal guilds` 应列出公会（含 PalBox 数），而非"公会数据暂不可用"。

**当前保守默认**：
- 缺任一坐标的 PalBox 直接跳过、不进快照（`palworld_terminal/adapters/normalizer.py` 的 `normalize_game_data()` PalBox 解析分支）。
- `GuildID` 缺失 → `guild_key=None`（`palworld_terminal/application/base_service.py` 的 `_guild_key()`），该据点置信度强制 `low`（`BaseService.apply()` 的置信度判定），低置信度不进公开事件（规格 §10.3）。
- 公会聚合侧 `guild_id` 缺失的 actor/PalBox 一律不归公会（`palworld_terminal/application/guild_service.py` 的 `GuildService.apply()`）；无公会数据时 `/pal guilds` 显示 `L("guilds_unavailable")`（`palworld_terminal/presentation/formatters.py` 的 `format_guilds()`，文案 `palworld_terminal/presentation/locale.py` 的 `MESSAGES["guilds_unavailable"]`）。

**结果处置**：
- 坐标/GuildID 稳定可用 → 维持现状，实测通过即可放心宣传据点功能。
- 经常缺失 → 据点推导不可靠：考虑把 `bases.enabled` 默认改为关闭（`config.py` 的 `parse_config()` BasesConfig 默认值）或在 README/`/pal bases` 输出中加强"推导、可能不全"的措辞；`GuildName` 缺失时的公会显示名回退已存在（`GuildService.apply()`，`公会-` + key 前缀）。

### 2.4 game-data 字段真实大小写与取值格式（含 `IsActive`）

**验证什么**：官方 example 的 ActorData 为空、仅有 schema 表（规格 §21.2-4），需确认真实响应的**顶层键名**、**actor 字段键名大小写**与 `IsActive` 的类型（字符串布尔还是原生布尔）。

**怎么验证**：
- [ ] 抓 `game-data.json`，确认顶层键是否为 `characters` / `palboxes`（当前解析入口 `palworld_terminal/adapters/normalizer.py` 的 `_character_list()`/`_palbox_list()` 只认这两个键的大小写变体）。若真实键名不同（如 `ActorData`），本项即为不符。
- [ ] dump 单个 actor 的完整键名集合，与 `normalize_game_data()` 的候选键逐一核对（`instanceid`、`trainerinstanceid`、`guildid`、`locationx`、`isactive` 等）。
- [ ] 确认 `IsActive` 实际取值：`"true"/"false"` 字符串、布尔或 0/1。
- [ ] 跑一段时间后检查未知 Class 落库情况：

  ```sql
  SELECT class_name, count FROM unknown_classes ORDER BY count DESC;
  ```

**当前保守默认**：
- 键名取值大小写不敏感（`palworld_terminal/adapters/normalizer.py` 的 `ci_get()`）；每个字段都给了多个候选键名。
- `IsActive` 经 `str_bool()` 容错（`normalizer.py`，接受 bool/int/字符串），实际调用于 `normalize_game_data()` 的 `is_active` 字段。
- 未知 Class → 经 `_register_class_if_unknown()`（`normalizer.py`）登记（`palworld_terminal/adapters/metadata_repository.py` 的 `pal_name()` 与 `take_unknown_classes()`），落 `unknown_classes` 表（`palworld_terminal/application/snapshot_service.py` 的 `ingest_game_data()`；建表见 `palworld_terminal/infrastructure/migrations.py` 的 `unknown_classes` 建表语句），不丢整快照。

**结果处置**：
- 键名/结构不符 → 在 `normalizer.py` 对应 `ci_get(...)` 调用中**追加**真实键名候选（不删旧候选）；顶层键不符则改 `_character_list()`/`_palbox_list()`。
- 无论结果如何：把真实（脱敏后）响应样本补进 `tests/fixtures/`，覆盖规格 §17 的"大小写混用键 / `IsActive` 字符串布尔"场景；未知 Class 高频条目补进 `metadata/pals.zh-CN.json`。

### 2.5 AstrBot 框架事实（`event.message_str` / `object` 子字段渲染 / 子命令别名）

**验证什么**（规格 §21.2-5，三个子项）：
1. 目标 AstrBot 版本的事件对象是否确有 `message_str` 属性；
2. `_conf_schema.json` 中 `object` 内子字段的 `options`（下拉）渲染是否被支持；
3. 命令组子命令 `alias=` 与中文子命令名是否被支持。

**怎么验证**：
- [ ] 在真机 AstrBot 中发 `/pal guild 某个含空格的公会名 @testsv`，确认公会名与 `@server` 均被正确解析（自解析逻辑 `palworld_terminal/presentation/server_arg.py` 的 `parse_arg()`）。**故障特征**：若 `message_str` 属性名不对，`main.py` 的 `_msg()` 会返回空串，所有带参命令表现为"参数为空"（如 `/pal guild X` 报"未找到公会"且名字为空、`@server` 永远不生效）。
- [ ] 打开插件配置页，检查 `routing.access_mode`（`_conf_schema.json` 的 `routing.items.access_mode` 用了 `options`）是否渲染为下拉框；否则确认降级为文本框后仍能正确保存 `restricted`/`open`。
- [ ] 子命令别名：当前实现**未注册任何 `alias=`/中文子命令**（`main.py` 的 `@pal.command("...")` 注册区全部为英文），已是规格允许的降级形态。本子项验证为可选增强：在测试分支上给某个子命令加 `alias={"状态"}` 试注册，观察目标版本是否报错。

**当前保守默认**：
- 所有带 `<name>`/`@server` 的 handler 仅 `(self, event)` 签名、`getattr(event, "message_str", "")` 防御性取文本（`main.py` 的 `_msg()`），属性缺失不抛异常（规格 §4.2）。
- schema 的 `options` 若不渲染仅影响配置页体验，不影响 `parse_config()` 读值（`palworld_terminal/config.py`）。
- 中文别名未实现 = 按规格 §13 "不支持则降级、不阻塞 v0.1" 处理。

**结果处置**：
- `message_str` 属性名不同 → 只改 `main.py` 的 `_msg()` 一处。
- `options` 不支持 → 按规格 §5 说明降级为纯 `string` + `description`（改 `_conf_schema.json`）。
- 别名支持 → 可选地在 `main.py` 补注册规格 §13 列出的 7 个中文别名。

### 2.6 `/game-data` 典型响应体大小与处理耗时（背压校准）

**验证什么**：真实（尤其是大存档）服务器上 game-data 的 payload 大小与端到端处理耗时，用于校准背压常数 k/cap/M 与 `game_data_seconds`（规格 §21.2-6、§6.1）。

**怎么验证**：
- [ ] 直接测原始响应：

  ```bash
  curl -su admin:$PW -o /dev/null -w "bytes=%{size_download} time=%{time_total}\n" \
       http://127.0.0.1:8212/v1/api/game-data
  ```

  分别在少量帕鲁与"满据点+多玩家"两种负载下各测数次。
- [ ] 插件侧指标：`RestResponse` 自带 `duration_ms`/`payload_bytes`（`palworld_terminal/adapters/palworld_rest.py` 的 `RestResponse` 数据类）。当前 scheduler **不打印**背压调整日志（见第 4 节注意点 2），可用 DB 时间戳间距观察实际采集节奏：

  ```sql
  SELECT observed_at - LAG(observed_at) OVER (ORDER BY observed_at) AS gap
  FROM base_observations WHERE world_id = '<world_id>' ORDER BY observed_at;
  ```

  gap 稳定在 ~120s（±10% 抖动，`config.py` 的 `parse_config()` `jitter_ratio` 默认 0.10）说明未触发背压；若翻倍增长（240/480/960）说明处理时间超过了间隔。
- [ ] 处理 game-data 的同时发 `/pal online`，确认回复不被阻塞（CPU 密集部分已用 `asyncio.to_thread` 卸载，`palworld_terminal/application/snapshot_service.py` 的 `ingest_game_data()`）。

**当前保守默认**：
- `game_data_seconds` 默认 120s（`palworld_terminal/config.py` 的 `parse_config()`）。
- 背压常量：`_BACKOFF_K=2.0`、`_BACKOFF_CAP=8.0`（上限 base×8=960s）、`_RECOVER_STREAK=3`（`palworld_terminal/infrastructure/scheduler.py` 模块级常量）；双向调节逻辑 `_adjust_backpressure()`；计时覆盖 fetch+入库全程（`Scheduler._tick()`，符合 §6.1 "端到端处理时间"）；在途锁 tick 合并（同在 `_tick()` 开头）。

**结果处置**：
- 大存档下处理时间逼近/超过 120s → 上调 `game_data_seconds` 默认值（`config.py` 的 `parse_config()` 与 `_conf_schema.json` 的 `polling.items.game_data_seconds` 同步改），或调整 `scheduler.py` 的三个背压常量；相应更新 `tests/unit/scheduler_backpressure_test.py`。
- payload 达数十 MB → 评估 `resp.json()`（`palworld_rest.py` 的 `fetch()`）内存峰值，必要时在 README 给大服运维建议。

---

## 3. 验收标准核查表（规格 §19）

### 3.1 功能

- [ ] **连接启用 REST 的世界**：`/pal status` 显示真实服务器名/版本/天数（与 curl `/v1/api/info` 对照）。
- [ ] **info/metrics/players 正确显示**：`/pal status`、`/pal online` 的在线数、FPS、玩家等级/Ping 桶与 curl 原始值一致（据点数以官方 `metrics.basecampnum` 为准，规格 §13）。
- [ ] **解析 game-data 主要 Actor 类型并计数**：`/pal world` 各 UnitType 计数与 `game-data.json` 手工分组计数一致；`unknown_classes` 表无爆炸式增长。
- [ ] **识别玩家会话**：玩家上线后 `player_sessions` 出现 `status='active'` 行；下线后连续 2 个健康快照（约 60s）转 `closed`/`observed_timeout`（`palworld_terminal/application/player_service.py` 的 `apply_players()` 缺席计数分支）。
- [ ] **检测确认后升级**：玩家真实升级后 `world_events` 出现 `PLAYER_LEVEL_UP`，`/pal events` 可见。
- [ ] **公会多据点+置信度**：一个公会建 ≥2 个据点，`bases` 表出现 ≥2 行且标 `confidence`；`/pal bases` 展示（低置信度默认不展示）。
- [ ] **生成结构化事件**：`SELECT event_type, count(*) FROM world_events GROUP BY 1;` 覆盖 NEW_PLAYER/NEW_GUILD/NEW_BASE 等。
- [ ] **模板日报不虚构**：`/pal today` 仅含当日真实事件；空白日输出"平静的一天"（`palworld_terminal/presentation/locale.py` 的 `MESSAGES["empty_day"]`）。
- [ ] **game-data 失败保留基础状态**：临时阻断 game-data（如防火墙拦 URL 路径）→ `/pal status`/`/pal online` 仍正常，仅世界详情缺失（失败静默返回，`palworld_terminal/application/snapshot_service.py` 的 `ingest_game_data()` 失败早退）。
- [ ] **多服务器互不串数据**：配两台测试服，各自 `worlds.world_id` 以 `server_id` 为前缀（构造见 `snapshot_service.py` 的 `ingest_info()`，格式 `server_id:worldguid:epoch`）；`/pal status @A` 与 `@B` 数据互不混淆。
- [ ] **restricted 授权闭环**：`access_mode=restricted` 下，未授权群任意查询被拒（文案 `locale.py` 的 `MESSAGES["not_authorized"]`）；管理员 `/pal use testsv` 后同群可查（`MESSAGES["use_ok"]`）；私聊被拒（`MESSAGES["private_restricted"]`）。

### 3.2 隐私（P0，全部必须通过）

- [ ] **DB 无 IP/原始 ID/原始 ping**：真机跑 ≥1h 后全库扫描（自动化版本见 `tests/integration/privacy_test.py` 的 `test_db_has_no_ip_no_raw_id_no_password_no_raw_ping`）：

  ```bash
  sqlite3 "file:palworld_terminal.sqlite3?mode=ro" .dump | grep -E "([0-9]{1,3}\.){3}[0-9]{1,3}"
  sqlite3 "file:palworld_terminal.sqlite3?mode=ro" .dump | grep -i "<真实steamid片段>"
  ```

  唯一允许命中 IP 形态的是运营者自己配置的端点与网格键列（豁免清单见 `privacy_test.py` 的 `_IP_SCAN_EXCLUDE` 常量）。`player_observations` 只应有 `ping_bucket` 枚举值（入口分桶 `palworld_terminal/adapters/privacy_filter.py` 的 `bucketize_ping()`；`ip`/`accountName` 在 `redact_players()` 处即被丢弃）。
- [ ] **日志无 Basic Auth/IP/原始 ID/响应体原文**：DEBUG 级别跑 1h，grep 日志文件中的密码、`Basic `、服务器 IP、steamid（HTTP 错误只报类别不带 host/URL，`palworld_terminal/adapters/palworld_rest.py` 的 `fetch()` 异常分支与 `_error_response()`；对应自动化 `privacy_test.py` 的 `test_logs_never_leak_raw_on_degradation_paths`）。
- [ ] **公共命令无原始 ID**：逐条跑 14 个命令，输出只含角色名/公会名，无 steamid/UUID/精确坐标。
- [ ] **strict 模式**：`privacy.mode=strict` 重跑采集 → `palboxes`/`bases`/`base_observations` 为空表、`player_observations.position_cell` 全 NULL（结构性保证 `privacy_filter.py` 的 `redact_game_data()` strict 分支；自动化 `privacy_test.py` 的 `test_strict_mode_persists_no_bases_no_palboxes` 与 `test_strict_mode_position_cell_all_null`）；`/pal bases` 提示 strict 停用（`locale.py` 的 `MESSAGES["bases_disabled_strict"]`）。
- [ ] **worldguid 变化不合并旧世界**：换存档重启 → `worlds` 出现新行，旧世界会话被置 `uncertain` 并记入待收敛表（`snapshot_service.py` 的 `ingest_info()` 换世界分支），统计不跨世界混算；旧世界 uncertain 会话随后由新世界的 players tick 超时收敛（见 3.4 与第 4 节注意点 1）。

### 3.3 性能

- [ ] **缓存查询 P95 < 500ms**：同一分钟内连续触发 ≥20 次 `/pal status`（15s TTL 内命中缓存，`palworld_terminal/application/query_service.py` 的 `QueryService.status()`，TTL 见模块级 `_STATUS_TTL` 常量），从 AstrBot 日志取"收到消息→发出回复"时间差，算 P95。注意该指标针对缓存命中路径（规格 §9.4）。
- [ ] **game-data 处理不阻塞回复**：在最大存档负载下，game-data 采集进行中发 `/pal online`，回复延迟无明显尖峰（`asyncio.to_thread` 卸载，`snapshot_service.py` 的 `ingest_game_data()`）。
- [ ] **采样任务无重叠堆积**：观察 `world_metrics.observed_at` 间距稳定在 30s±10%，无成串密集写入（在途锁 `scheduler.py` 的 `Scheduler._tick()` 开头）。
- [ ] **7 天连续运行无任务泄漏**：每日同一时间记录——AstrBot 进程 RSS、`palworld_terminal.sqlite3` 及 `-wal` 文件大小、日志中异常堆栈计数；7 天内 RSS 与 WAL 无单调无界增长。
- [ ] **`terminate()` 全量关闭**：禁用/卸载插件 → 日志无 `Unclosed client session` / `Task was destroyed but it is pending` 警告（关闭链 `palworld_terminal/container.py` 的 `Container.stop()`：scheduler → rest clients → db）。

### 3.4 可靠性

- [ ] **API 短暂中断不误报全员离线**：停 Palworld 进程（或拦截端口）2 分钟再恢复 → 期间会话转 `uncertain` 而非 `closed`（`snapshot_service.py` 的 `ingest_players()` 失败分支 → `player_service.py` 的 `mark_uncertain()`）；恢复后同玩家会话被**复用**（`joined_at` 不变，复用查询含 uncertain，`palworld_terminal/adapters/sqlite_repository.py` 的 `get_open_session()`）。**超时收敛已接线**：`apply_players()` 在每个健康 players 快照末尾调用 `sweep_uncertain()`——验证预期为：停服超过 `uncertain_timeout`（默认 900s，`config.py` 的 `parse_config()` PrivacyConfig）后恢复，**首个健康 players tick** 即把未回归玩家的 uncertain 会话关为 `closed/world_offline`；停服短于 900s 恢复则复用原会话。
- [ ] **重复快照不重复生成事件**：让世界静止（无人操作）连续多个采集周期 → `world_events` 行数不增长（`dedup_key` 唯一索引，`palworld_terminal/infrastructure/migrations.py` 的 `idx_events_dedup`）。
- [ ] **重启后从 DB 恢复活动会话**：玩家在线时重启 AstrBot → 重启后该玩家会话延续（同 `id`、`joined_at` 不变；恢复路径 `player_service.py` 的 `recover_on_start()` + 首个健康快照的复用逻辑 `apply_players()`）。换世界后、收敛完成前重启的旧世界 open 会话，由重启后首个 info tick 从 DB 重建待收敛集合（`snapshot_service.py` 的 `_restore_prev_worlds()` / `sqlite_repository.py` 的 `list_worlds_with_open_sessions()`）。
- [ ] **迁移失败停写并有明确错误**：真机难以自然触发；可在测试副本上手动 `PRAGMA user_version = 999` 后启动，确认插件报"数据库迁移失败"类管理员错误且不再写库。

---

## 4. 已知实现注意点（验证前先知晓，避免误判）

1. **`sweep_uncertain` 已接入运行时（本条曾记录"无运行时调用方"，已过期）**：uncertain 超时收敛（默认 900s 后 `closed/world_offline`，`player_service.py` 的 `sweep_uncertain()`）现有三条运行时路径：
   - **同世界端点恢复**：`apply_players()` 在每个健康 players 快照末尾调用 `sweep_uncertain()`（中断期间置 uncertain 且本快照未回归、已超时的会话立即收敛）；
   - **换世界遗留**：`snapshot_service.py` 的 `_sweep_prev_worlds()` 在每个 players tick 开头（无论本次 `/players` 成败）代旧世界收敛，竞态残留的 active 会话先归位 uncertain 再 sweep；`ingest_players()` 另有过期 world 守卫（对照 `_current_worlds` 内存权威世界），并发换世界期间的过期 tick 不会复活旧世界会话；
   - **重启悬置**：`_restore_prev_worlds()` 在启动后首个 info tick 从 DB 重建待收敛集合（`list_worlds_with_open_sessions()`），换世界后、收敛完成前重启也不悬置。

   运行时路径自动化覆盖见 `tests/integration/player_uncertain_test.py`（`test_players_recovery_sweeps_timed_out_uncertain`、`test_world_switch_sweeps_old_world_on_next_tick`、`test_stale_world_players_tick_does_not_resurrect_sessions`、`test_restart_rebuilds_prev_worlds_from_db` 等）。**实服验证预期**：停服恢复后（超过 900s）首个健康 players tick 即收敛超时会话为 `closed/world_offline`，无需等待任何独立定时任务。
2. **背压调整无日志**：规格 §6.1 要求"记 collector 降频/恢复日志"，当前 `palworld_terminal/infrastructure/scheduler.py` 无任何日志输出（全模块无 logging）。实服校准（第 2.6 节）只能靠 DB 时间戳间距推断背压是否触发；建议实现侧补一条 INFO 日志再进入 7 天稳定性观察。
3. **`userId`/`userid` 首启自检未实现**：规格 §21.2-1 括注"首启自检"，当前代码没有该自检逻辑（`normalize_game_data()` 解析、`redact_game_data()` 脱敏 game-data 侧 `userid`，但无跨端点对比），第 2.1 节以手工 curl 对比替代；若希望长期保留自检，需在 `snapshot_service` 首个健康 game-data 快照处补对比与日志。
4. **`privacy.mode=advanced` 的可见提示已实现**：规格 §15 要求 advanced 按 balanced 生效且**用户可见地提示**——当前 `query_service.py` 的 `rules()` 在 `mode=advanced` 时输出 `advanced_note`（"advanced 隐私模式暂按 balanced 生效。"，由 `formatters.py` 的 `format_rules()` 渲染为"注：…"）。验证 strict/balanced 时顺带确认：配置为 `advanced` 时 `/pal rules` 展示该提示，且落库/展示行为与 balanced 完全一致。
