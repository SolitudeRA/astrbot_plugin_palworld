# game-data 上线：娱乐向功能再设计（4 功能 + 数据地基）设计（spec）

> 日期：2026-07-24　分支：`feat/gamedata-live-features`（base main `6bb56c3`，v1.1.0 线）
> 起因：Palworld `/v1/api/game-data`（Pocketpair 官方 GameData API）已在实服确认上线（不再 404）。经**实服全量探测 + 官方 schema 双重印证**，确认真实响应结构与当前解析器假设**根本不符**——直接机械解禁会静默产出空数据。本 spec 在验证过的真实数据上，以**娱乐性与参与感**为导向，设计围绕 game-data 打造的 4 个功能，并夯实其数据地基。
> 已过一轮 4 棱镜对抗复核（数据可行性/隐私C1/架构分层/完整性机制），本稿为复核后定稿。

---

## 1. 背景事实（已定论，勿重查）

### 1.1 真实 game-data 结构（实测样本 + 官方 schema 双重印证）
官方文档：<https://docs.palworldgame.com/api/rest-api/game-data>。实测样本：0 人在线仅 5 个 PalBox；1 人在线 136 actor（131 Character = 126 BaseCampPal + 2 WildPal + 2 NPC + 1 Player，外加 5 PalBox）。**两份样本 OtomoPal 数均为 0**（玩家未带出随身帕鲁）。

顶层：`{ Time, FPS, AverageFPS, InGameTime, InGameDays, ActorData }`
- `InGameTime`(如 "17:44") / `InGameDays`(如 590) 官方文档未列但真服实有——以实测为准。
- `FPS`/`AverageFPS` 现 normalizer 恰能解析（ci_get 大小写不敏感命中）。

`ActorData` = **单一扁平数组**，每条经 `Type` 二分（`oneOf`）：
- **`Type == "Character"`**：类别在 `UnitType` ∈ `{Player, OtomoPal, BaseCampPal, WildPal, NPC}`（与 `domain/enums.py` 的 `UnitType` 逐字吻合）。字段（实测 100% 存在）：`InstanceID`(格式 `<32hex> : <32hex>`)、`NickName`、`TrainerInstanceID`/`TrainerNickName`/`TrainerClass`（官方："owner 的 InstanceID，仅 OtomoPal/BaseCampPal 适用"；**实测 BaseCampPal 全空**）、`userid`(仅 Player)、`ip`(仅 Player)、`level`、`HP`、`MaxHP`、`GuildID`、`GuildName`、`Class`(BP 资产名，如 `BP_ChickenPal_C`/`BP_Player_Female_C`)、`Action`、`AI_Action`、`LocationX/Y/Z`、`RotationX/Y/Z`、`Stage`、`IsActive`("true"/"false" 字符串)。
- **`Type == "PalBox"`**：字段 `Name`(据点默认名)、`GuildID`、`GuildName`、`Class`(`BP_BuildObject_PalBoxV2_C`)、`LocationX/Y/Z`。

**关键错法**：现 `normalizer.normalize_game_data` 读顶层 `characters[]`/`palboxes[]`、类别取 `ci_get("type","unittype")`——真实无这两个顶层键、且 `Type` 恒 "Character/PalBox" → **在真数据上产出空快照**（复核已核实 normalizer.py:134-140,160 现状）。

### 1.2 隐私与数据可见性（硬约束）
- **C1 隐私红线**：`ip` 官方 schema 就有（仅 Player 有值）——**永不入库/展示/日志**。`userid` HMAC 脱敏（现已做）。**精确坐标不出公共命令**（现有隐私不变量；strict 清坐标）。玩家名/公会名明文可用（非红线）。
- **C2 就近可见性**：game-data 只含**在线玩家附近**的 actor（0 人在线仅 PalBox；1 人在线其周边 126 工作帕鲁涌现）。**一切"统计"实为"当前可见"口径**，措辞必须诚实（"此刻""当前快照"），不得吹成"全服全量"。
- **C4 推导性质**：公会/据点是插件从 `GuildID` 聚合与 PalBox 坐标聚类**推导**（非官方实体），保留"观察推导/置信度"免责。

### 1.3 据点聚类参数已在真数据验证
126 工作帕鲁到最近 PalBox 2D 距离 p50=1917 / max=3535，**全部落在 `assignment_radius=5000` 内**；据点推导算法参数在真数据上成立。

### 1.4 元数据缺口（实测量化）
- `metadata/actions.json`：43 键全为 `EPalActionType::*`/`EPalWorkType::*`；真实 token 是 `BP_AIAction_Worker_Working`/`BP_ActionMining`/… → **真实动作 0% 命中，全 unknown**。
- `metadata/pals.zh-CN.json`：279 键为 `PalDataParameter/*`/裸名；真实 `Class` 是 `BP_*_C` → strip `BP_`/`_C` 后仅 **26/128 实例命中**。**利好**：该文件**已含 `element_types` 元素源**（复核发现），元素派生有现成地基。
- **拿不到的数据（设计禁区）**：帕鲁词条/被动技能/个体值(IV)/凝魂/亲密度（在存档 `.sav`，REST 不给）；精确坐标（隐私）；背包/物品/建筑/击杀/PVP。已核实 136 actor 全部键仅 26 个且皆标量，无词条字段。

### 1.5 现有命令面与开关现状（实测 `command_registry.py` + `command_permissions.py`）
`/pal` 组下已有：`world status|overview|events|today`、`guild info|base|bases`、`player info|bind`（**bind = 群号→游戏名认领身份**）、`me [hide|show]`（个人卡）、`rank today|total|level`（排行榜）、`online`、`status`、`link`、`server`、`confirm`。
feat_group 与默认：`me`/`rank`/`player` 属 `players`；`guild *`/`world overview` 属 `guilds_bases`。**注意 `FEATURE_DEFAULTS` 里 `players` 与 `guilds_bases` 默认均为 False**——即**默认关、需管理员在配置页开**。本 spec 说"players 未上游锁定/可配"指它未被 game-data 上游锁强制关（对比 guilds_bases 现被 force-lock），**非"默认开"**。

### 1.6 门控与解禁（承 2026-07-16 lock spec）
game-data 管线由单一常量 `shared/command_permissions.py` 的 `UPSTREAM_UNAVAILABLE_FEATURES = {"guilds_bases"}` 硬锁。解禁走 lock spec **§7 最小恢复**（见 §4.1）。`world overview` 归队 `guilds_bases` 是永久的，不回滚。
**跨端点依赖（承重）**：`_DERIVED_ENDPOINT_FEATURE = {GAME_DATA: "guilds_bases"}`——GAME_DATA 端点**仅当某条 guilds_bases 命令 `effective_enabled` 才轮询**。故所有依赖 game-data 的功能（含 me 的随身帕鲁）**在部署未启用任一 guilds_bases 命令时数据恒空**。

---

## 2. 目标 / 非目标

**目标**：① 修 normalizer 适配真实 ActorData 契约，解禁 game-data 管线（lock §7 最小恢复），让数据在真服可用；② 全量重建两份元数据（动作含**新增 `ActionCategory.SLACKING` 摸鱼类**、帕鲁名+元素）；③ 在验证过的数据上落地 4 个娱乐向功能：**我的名片（文字/图片）· 据点车间现场 · 排行榜·飞升榜 · 服务器图鉴**；④ 严守 C1/C2/C4 口径，隐私护栏以测试证实（非口头）。

**非目标**：不做自动推送（push）与昼夜皮肤；不做禁区功能（§1.4）；不改 `GameDataSnapshot` 的 `characters[]/palboxes[]` 二桶结构（仅改解析 + 加两个顶层标量字段）；不动据点推导算法与参数。

---

## 3. 范围与分阶段（每阶段可独立评审/合并）

- **阶段 0 · 数据地基**：解禁 §7 + normalizer ActorData 适配 + InGameDays/InGameTime 解析（含 redact 透传）+ 元数据重建（含 SLACKING）+ 脱敏真样本 fixture 沉淀 + ports/枚举扩展。
- **阶段 1 · 独立先行**：排行榜·飞升榜（走 players 端点历史，不依赖 game-data 解禁，可并行）。
- **阶段 2 · 富化**：我的名片（文字/图片）+ 据点车间现场（吃地基）。
- **阶段 3 · 新造**：服务器图鉴（吃地基 + 新表 `observed_species`）。

---

## 4. 共享地基（阶段 0）

### 4.1 解禁 game-data 管线（lock §7 **最小恢复**，不半拆）
复核裁定：`UPSTREAM_UNAVAILABLE_FEATURES` 常量、`upstream_unavailable()`、`upstream_unavailable_group()`、`effective_enabled` 首行 force-off、`enable_configurable` 的 `not in` 子句 **必须存活**（被 `enable_configurable` 与跨端锚定测试 `frontend_pal_commands_test` 引用）。故：
- **后端（单点解禁）**：`shared/command_permissions.py` 的 `UPSTREAM_UNAVAILABLE_FEATURES` **清空为 `frozenset()`**（不删常量/函数）。空集下 `upstream_unavailable()` 恒 False → force-off 行休眠无害、`enable_configurable` 的 `not in` 恒真 → guild×4 + overview 变可配、`active_endpoints` 允许 GAME_DATA 随 guilds_bases 命令激活。**级联一处到位，无需逐符号删。**
- **后端（lock 专属机件回收，§7.4）**：删 `config.py` 上游分流收集器 + `PermissionsConfig.upstream_ineffective_keys` 字段 + `main.py` 上游告警块。（空集下它们已死；一并回收避免死码。）
- **前端**：`schema.ts` 5 节点（overview + guild×4）删 `unavailable`；**guild×4 `enableConfigurable` false→true、overview `enableConfigurable` false→true**（跨端锚定强制，`overview` `defaultEnabled` 保持 false）；`permissions.ts` 删 `unavailable` 首判；`CommandTree.vue` 删"暂不可用"锁定行/徽标；`SettingsPanel.vue` 删说明横幅 + **localStorage 键 `palworld-terminal-gd-banner-dismissed`**；产物 `pages/settings` 重建（no-drift）。
- **测试**：按 lock spec §5A/§5B 镜像反转（force-off/横幅专属测试删除、被反转断言翻回、示范载体可留 player）；**`tests/integration/conftest.py` 的测试专用 `_wire_game_data`**（锁定期绕生产门装配 game-data）解禁后冗余——改夹具用生产装配（guild 命令开）或删该 helper。
- **docs**：README/commands.md/configuration.md/_conf_schema.json 的"暂不可用"文案回收，`readme_test.py` 中文锚点同 commit。
- **dex 归属**：新 `dex` 命令的 feat_group = `guilds_bases`（决策已定；同一 game-data 命脉）。

### 4.2 normalizer ActorData 适配（承重）
blast radius = `adapters/normalizer.py` + **`domain/models.py`（加 2 字段）** + **`domain/privacy.py`（redact 透传）**；`GameDataSnapshot` 的 `characters[]/palboxes[]` 二桶结构不变，下游 `guild_service/base_service/query_*/player_service` 零改动（复核确认下游只读二桶及逐 actor 字段）。
- `adapters/normalizer.py`：读容器 `ci_get(raw, "actordata", "actor_data")`（保留旧 `characters`/`palboxes` 候选为防御回退，追加不删）；遍历 ActorData 按 `Type` 分流（`"PalBox"`→`PalBoxActor`；否则 Character→`CharacterActor`，`unit_type` **改取 `ci_get(item,"unittype","unit_type","type")`**——`UnitType` 优先、`type` 仅回退）。**`ip` 绝不读入模型**（`CharacterActor` 无 ip 字段，保持）。未知 `UnitType`/`Type`→`UNKNOWN` + 现有 `unknown_classes` 采集延伸。
- `domain/models.py`：`GameDataSnapshot` 新增 `in_game_days: int`（默认 0）、`in_game_time: str`（默认 ""）；normalizer 从顶层 `InGameDays`/`InGameTime` 填。口径：**`WorldMetric.world_day` 仍以 metrics.days 为权威真源；game-data 的 `in_game_days` 仅存作参考/氛围文案，不一致不告警、不覆盖**。
- `domain/privacy.py`：`redact_game_data` 逐字段重建 `GameDataSnapshot` 处**补拷 `in_game_days`/`in_game_time`**（否则到达消费方前被静默重置为默认值）——加"redact 后新字段仍在"单测。
- **fixture 沉淀（隐私承重，见 §11）**：实测真样本**必须脱敏后**入 `tests/fixtures/`：`ip`→RFC5737 文档段 `203.0.113.x`（一眼假、永不撞真玩家）；`userid`/`InstanceID`/`NickName`/`GuildID`→显式假值（沿现有 `steam_00001`/`INST-P1`/`Akari` 风格，InstanceID 保持 `<hex> : <hex>` 形但用假 hex）；**落库前 grep 核验无真 IP 网段、无真 32hex GUID 形**。fixture 须**显式带一个假 `ip` 字段**（用于真正跑通"raw 含 ip→模型/库/日志无 ip"守卫，见 §11）。

### 4.3 元数据全量重建
- **新增 `ActionCategory.SLACKING`（摸鱼）到 `domain/enums.py`**（复核裁定：现枚举无摸鱼成员，`action_category` 执行 `ActionCategory(value)`，映到未登记值会 ValueError；映到 idle 则摸鱼不可分——必须先加枚举成员，这是 §6 车间的**硬前置**）。
- `metadata/actions.json`：按真实 `BP_Action*`/`BP_AIAction*` token → `ActionCategory` 完整映射。归类（写死，消解 §4.3/§6 措辞矛盾）：Worker_Working/Mining/Harvesting/Deforest/GenerateEnergy/Feeding→`working`；`InSpa`/`DodgeWork`→**`slacking`**；`BaseCampWorker_Wait`/`RandomRest`/`Work_WaitForWorkable`→`idle`；Approach/Wandering→`moving`；WildLife/NPC_*→各归类。保留 unknown 兜底。
- **工序（复核裁定）**：`InSpa/DodgeWork/…` 等 ~37 真实 token 目前**仅见于 spec、无 fixture 佐证**——**先沉淀脱敏 fixture（§4.2）→ 从中确认真实 token → 再回填 actions.json**，避免摸鱼归类对不上真 token。
- `metadata/pals.zh-CN.json`：新增/重建 `BP_*_C → {中文名}` 映射（元素复用现有 `element_types`）。数据源：公开 paldex/datamine 构建，strip `BP_`/`_C` 兼容旧键 + 显式补缺口（LegendDeer/BOSS/物种变体）；极冷门缺失走优雅降级（缩写名 + 元素 unknown）。
- **官方图鉴物种总数**（dex 分母）：随 paldex 源一并确定；**无法确定 → dex 降级不显分母/缺失清单**（见 §8）。

### 4.4 新持久化 `observed_species`（dex 用）
- `infrastructure/migrations.py` 新表 `observed_species(species_class TEXT PK, species_name TEXT, element TEXT, first_seen_at INT, first_seen_name TEXT, observe_count INT)`；永久累积（不 prune）。
- `adapters/repo_dex.py` CRUD；**扩 ports（承重，复核裁定）**：`application/ports.py` 的 `ReadRepositoryPort` 加 dex 读方法、`WriteRepositoryPort` 加 `upsert_observed_species`（`Repository` 结构化满足即可）——否则 `query_dex`（application）直导 `repo_dex`（adapters）违 layers 契约、或 `self._repo` 调 dex 方法触 mypy attr-defined。
- **采集（隐私+口径承重）**：`snapshot_service.ingest_game_data` 中，upsert **挂在 `redact_game_data` 之后、消费已脱敏 `gd`**（不读 raw `resp.data`），且置于 `if self._guilds is None or self._bases is None: return` 短路**之后**（与 guilds_bases 一致停摆）。
- **只收真帕鲁物种（复核裁定）**：仅对 `UnitType ∈ {OtomoPal, BaseCampPal, WildPal}` 的 actor upsert——**排除 Player(`BP_Player_*`)/NPC/PalBox(`BP_BuildObject_*`)**，否则虚增物种数、污染元素分桶。
- **`first_seen_name` 取值钉死（隐私红线）**：**只可取 `NickName`/`TrainerNickName`（明文名）**；取不到存 NULL/空串，**严禁回退到 `instance_id`/`player_userid`/`InstanceID`**（该表不 prune，回退 id = 永久泄漏 GUID/steamid）。repo_dex upsert 加测试守此。

---

## 5. 功能① 我的名片 `扩 /pal me`（文字 / 图片）

**玩法**：个人卡——等级 · HP · 公会 · 本次在线时长 · **超越有记录玩家的 X%**（等级百分位）· 脚边**随身帕鲁高光**（物种+元素+等级+当前状态）。可选文字版或图片版。

**分层**（feat_group `players`；随身帕鲁高光需 game-data 端点在轮询）：
- application `query_players` mixin（`_RankProfileQueries`，复核确认归属正确）：`me_card(player_key)` → `MeCardDTO`。**读 `self._world_cache`（随身）须在 `_RankProfileQueries` 或共享基类声明 `_world_cache: Any`**（复核 SD6：否则重蹈 Spec ② mypy attr-defined；spec 早先只对 `_DexQueries` 提了此模式）。
  - **百分位（复核 SD4·改用现成查询）**：**复用现成 `list_players_by_level`（按 `players.latest_level`）**算该玩家超越比例——`player_observations` 无分布聚合查询、`ReadRepositoryPort` 亦无，**不新增地基**；`latest_level` 路径既有且口径正贴"有记录玩家"。措辞"超越**有记录玩家**的 X%"（不用"全服"，C2）。
  - **随身帕鲁 join（复核 SD1·防重复哈希，承重）**：`shared_world` 存**已脱敏**快照——其 `Player.player_userid` 已 = `hash_user_id(salt,world_id,raw)`，HIGH 置信 `player_key` 同样 = `hash_user_id(salt,world_id,raw)`，二者**已相等**。故 join **直接 `Player.player_userid == player_key`**——**切勿再套一层 hash**（否则 `hash(hash)≠key` → 随身恒空、"满"态永不可达；且 query 层无 raw userid，"raw 仅用于比对"不可实现）。命中后取该 Player 的 `instance_id`（redact 透传未 hash，§9 P6），匹配 `OtomoPal.trainer_instance_id`（`link_companions` owner_instance→pal_class）。**不按 TrainerNickName join**。仅靠名字解析的 LOW 置信 player_key 与 userid 哈希对不上 → 该类玩家随身自然缺席（可接受降级）。
  - **实证缺口（诚实标注）**：两份实测样本 OtomoPal 数为 0、BaseCampPal trainer 全空——随身逻辑仅官方 schema 背书。**动工前先抓一份含 OtomoPal 的真样本确认 `TrainerInstanceID` 有值**；未带出/不在线/game-data 未轮询 → 该段省略降级。
  - **跨端点依赖（诚实标注，复核 M1）**：随身帕鲁需 GAME_DATA 端点在轮询（即部署已启用至少一条 guilds_bases 命令，如 dex/guild base）；否则 `shared_world` 无快照 → 随身恒空、该段省略。§5/§9 措辞如实说明，不误导。
- domain/application：`Element` 枚举 → `domain/enums.py`；**DTO 全落 `application/dtos.py`**（仓内无 `domain/dtos.py`）。`MeCardDTO` 承载（复核 SD3·离线字段数据现成——`last_seen_at` 在 `PlayerIdentity`、累计在线走**现成 `total_durations()`**，已在 `PlayerProfileDTO.total_seconds`/`ReadRepositoryPort`）：`online`、`guild_name`、`hidden`、`last_seen_at`、`first_seen_at`、`total_seconds`、`today_seconds`、`percentile`、`online_seconds`，加 `companion: Optional[CompanionView(species_name, element, level, action_label, hp_ratio)]` **＋判别位 `companion_status ∈ {shown, none_out, no_data}`**（见下）。可复合/扩展现有 `PlayerProfileDTO`。**离线时间字段在 application 层预粗化**（`last_seen_at`→相对天/粗档，**不出绝对时间戳**——复核 P1 隐私：绝对登录/登出时刻=作息，须粗化 + §11 测试守）。
  - **随身三态（复核 SD2·C2 承重）**：单个 `Optional[companion]` 的 `None` **无法区分**"在线且被 game-data 看见但没带随身"（→"此刻未带出"）与"根本无 game-data 数据"（→不可断言没带）。而 `players`/`guilds_bases` **默认均关**、game-data 仅随 guilds_bases 命令轮询（§1.6）→ **默认部署下在线玩家 `shared_world.get(server_id)` 恒 None**，若按"companion is None→未带出"实现会对绝大多数在线玩家**谎称一个从未做出的观测**（C2 红线、且是常态非边界）。故 `companion_status`：仅当【会话在线（`get_open_session` 非空）**且** `shared_world` 有快照 **且** 找到该 Player actor 但无匹配 OtomoPal】→ `none_out`（"此刻未带出随身帕鲁"）；否则 → `no_data`（"随身数据暂不可用（需启用 guilds_bases）"，**绝不谎称没带**）；命中 OtomoPal → `shown`。复用 `world_summary` 的 `available = gd is not None` 范式。
- **视觉定稿（本轮 demo 敲定）**：两版「现代档案」——**C1 浅**（暖中性 + 青绿）/ **C3 暗**（暖炭底 + 琥珀），同一套档案骨架（名/性别/等级/公会 → 百分位 hero 大数字 → HP·在线 stat 卡 → 随身帕鲁行 → 页脚世界日/时）。**随身帕鲁头 = 自绘元素图标** `assets/element-icons/<element>.svg` 内联（原创、无 IP，9 元素齐；`fill="currentColor"` 按元素色着色、随浅/暗卡片自适应），非 emoji。**四状态**：满 / 无随身（虚线降级「此刻未带出随身帕鲁」）/ 离线（「● 此刻不在线」徽章 + 最近上线·累计在线，无实时血量·随身）/ 文字版兜底（emoji 标元素，永不依赖字体/图标）。
- presentation（**DTO 边界硬约束，隐私承重**）：
  - 文字路：`format_me(dto)` 富化（现有 str 路径）。
  - 图片路：`presentation/card_render.py::build_me_card_html(dto, icons, theme) -> str`——**纯函数：入参只有 DTO + 元素图标表(`dict[str,str]`) + 已解析主题(`light`/`dark`)；无快照、无时钟、无运行时 I/O**（严禁把 `CharacterActor`/`shared_world`/`auto`/绝对时间戳塞进来）。
    - **图标加载器落 adapters（复核 A1/A2·承重，import-linter 抓不到文件 I/O）**：新 `adapters/icon_repository.py`（或 metadata 式扩展）启动 `load()` 读 SVG；`container.py` 解析目录 = `Path(__file__).resolve().parent.parent / "assets" / "element-icons"`（与 `metadata_dir` 同源、**按包位置非 data_dir/CWD**），把 `dict[element→SVG串]` **注入 `Commands`**（照 `meta` 注入 QueryService 样式）。**按 `Element` 枚举名 allowlist 取 9 个 `<element>.svg`，不 glob 目录**（复核 P2：目录含 `elements-preview.html/png`，glob 会污染/破版）；缺文件→降级 emoji。`card_render` 只收注入好的 dict → presentation↛adapters 天然闭合。
    - **主题解析（复核 A3/A4/CT4）**：`theme` 入参**恒为已解析 `light`/`dark`**；`auto`→具体主题在 **`Commands.me_card_html`（presentation，已注入 `self._clock`+`self._cfg`）** 解析 = `datetime.fromtimestamp(self._clock.now(), ZoneInfo(server_timezone(self._cfg, world)))` 的当地小时、**`6 <= hour < 18 → light` 否则 dark**。**禁用宿主墙钟/UTC 小时**（`Clock.now()` 是 UTC epoch 无时区）；`server_timezone(cfg, world)` 为既有权威解析（report_service.py:25）。**theme 不入 `MeCardDTO`**（渲染期参数非数据投影）。auto 边界单测须注入固定 clock+tz（免 CI 时区抖动）。
    - **转义**：渲染前对玩家名/公会名（仅有的用户可控自由文本）做 HTML/Jinja 转义（M7：含 `{{`/`{%` 会被 `html_render` 二次解析破坏）。元素 SVG 是可信静态内容、**不转义**（已核 9 个 SVG 无 `{{`/`{%`、无 script/href/外链，内联安全）。
  - `main.py` `me` handler：图片模式 → `html = commands.me_card_html(...)`（`Commands` 内部完成 auto→light/dark 解析 + 转义 + 注入图标表后产纯 HTML）；`img = await self.html_render(html, {})`（第二参**恒 `{}`**，不透传 raw；AstrBot `Star.html_render(tmpl,data)→URL/路径` + `event.image_result(url)`）；`yield event.image_result(img)`。**降级**：`html_render` **抛异常或返回 None/空串**均 → `event.plain_result(文字卡)`（复核 M7）。
  - 单测：`build_me_card_html` 纯函数断言输出 HTML 串**不含坐标数字/instance_id/player_key/绝对时间戳(epoch/ISO datetime)**（复核 P1：离线卡时间字段也进"测试证实"网；对齐 `commands_me_bind_test.py:204` 先例）。
- 命令（复核 CT6：`card` 与 `hide/show` 是 **`me` 后单 token 互斥子命令**，非两个位）：`/pal me` → 文字（默认）；`/pal me card`（别名 `卡`/`图`）→ 图片；`/pal me hide|show` → 隐私开关。**记法统一 `me [hide|show|card|卡|图]`**（§10 同步）；多 token（如 `me hide card`）→ 帮助提示、**不静默退化**（否则 `arg.name="hide card"` 既不匹配 hide 也不匹配 card，hide 被吞）。
- **主题（管理员配置，非 per-call）**：新增 config `presentation.me_card_theme ∈ {light, dark, auto}`（默认 `light`）——固定 C1/C3，或 `auto` 按**服务器本地时钟**昼夜（`6<=hour<18→light`；真实时钟非 InGameTime，避游戏昼夜加速频翻）。该键**刻意新增**（推翻 M4"不引入"）。**完整贯通链（复核 CT1/CT2/CT3·新增顶层节波及多道自建关卡）**：
  1. `_conf_schema.json` 加 `presentation` 节 + `config.py` 新 `PresentationConfig` + `AppConfig` 字段 + `_one_of(...,{light,dark,auto},"light")`；
  2. **`presentation/config_view.py`（CT1·严重）**：`_TOP_KEYS`(:42) + 对象节形状校验元组(:169) + `_ENUMS`(:60) **都是写死白名单**，不加 `presentation` → 前端 `collectBody` 回传 `presentation` 键 → `validate_and_backfill` 首行 `issubset(_TOP_KEYS)` 失败 → **整页保存被 `invalid_shape` 拒（所有配置都存不进，非丢一键）**。三处均加 `presentation` / `presentation.me_card_theme:{light,dark,auto}`。AstrBot 递归回填救不了这道自建白名单。
  3. 前端 `schema.ts` OBJECT_SECTIONS 加节 + **`chapters.ts`（CT2）** 把 `'presentation'` 挂进某配置章 `blocks`（否则控件不渲染、管理员选不了，只能齿轮裸编辑）；
  4. `docs/configuration.md` + 设置页产物 no-drift；
  5. 测试（§11）：`config_view_validate_test`（presentation 被接受）、**前端 `schema.test.ts:34` 的"恰 8 个 object 节"断言 8→9**（CT3，否则响亮红）、`conf_schema_test` 补 `presentation.me_card_theme` 断言。

---

## 6. 功能② 据点车间现场 `扩 /pal guild base`

**玩法**：一屏播据点此刻谁在干嘛——`⛏12 挖矿 · ♨5 泡澡 · 🚬3 逃班` + **氛围徽章**（🔥热火朝天 / 😴集体摆烂）+ 一句吐槽 + 物种 top。

**分层**（feat_group `guilds_bases`，需解禁）：
- **硬前置**：§4.3 的 `ActionCategory.SLACKING`——`base_service.action_distribution` 按 `str(p.action)` 聚合，摸鱼类须先入枚举才能被区分与统计。
- application `query_guild` mixin（`_GuildBaseQueries`，复核确认归属正确）：`base(...)` 复用现成 `action_distribution` + 派生 **摸鱼率**（`slacking` 占比）+ 物种 top（`Class`→名）。
- application `dtos.py`：`BaseDetailDTO` 加 `mood`(标签)、`slacker_rate`、`species_top`。
- presentation `formatters.py`：`format_base` 富化（徽章 + 吐槽 + 分布 emoji）；`locale.py` 加徽章/吐槽模板。
- **工作图标（预备资产，本轮文字输出）**：本轮车间为**文字输出**，活动分布用 emoji 标记（⛏挖矿/♨泡温泉/🚬逃班…）。自绘工作类型图标（`assets/work-icons/`，与 `assets/element-icons/` 同套视觉）**已备**，供**未来把车间做成图片卡**时用（复用 me 卡的 `html_render` 管线）；图片化车间不在本轮范围，资产先落地。
- 命令：无新命令。C2：只报"此刻可见 N 只"非"共有"；据点标"(推导)/置信度"。

---

## 7. 功能③ 排行榜·飞升榜 `扩 /pal rank +climb`

**玩法**：现有 `today|total|level` + 新 **`climb` 飞升榜**（周窗 level 涨幅），末尾"你第 N，离前一位差 X"。

**分层**（feat_group `players`；**不依赖 game-data 解禁**，可阶段 1 先行）：
- application `query_players` mixin：`rank_climb(window="7d")`——**直算 `player_observations` 跨周 level 差**（决策已定，不建聚合表）。
- **窗与算法钉死（复核裁定 D4）**：窗 = `[now−7d, now]`；`baseline` = `observed_at ≤ window_start` 的**最新**观测，无则取**窗内最早**观测（新玩家）；`current` = 最新观测；`gain = max(0, current − baseline)`（LOW 置信度按名 hash 玩家可能同名换人/存档重置致等级下降，**负增量归零**）；`gain == 0` 不上榜；历史深度不足时诚实标"自 bot 记录以来"。口径"仅统计有快照记录的玩家"。
- domain/application：`RankEntryDTO` 加 climb 变体（gain 字段，落 `application/dtos.py`）。
- presentation：`rank` handler 加 `climb` 模式；`format_rank` 加飞升榜；`command_registry.py` `rank` 描述加 `climb`。

---

## 8. 功能④ 服务器图鉴 `新 /pal dex`

**玩法**：`/pal dex` = "本服已观测 N/总数 物种"进度总览（按元素分桶）。

**分层**（**扁平命令**，非命令组，复核 M5：group=null、参数内解析，与 `rank` 对齐；本轮仅进度总览，`rare/element/me` 留后续）：
- 持久化：§4.4 的 `observed_species` + `repo_dex` + ports；`ingest_game_data` 采集时 upsert（已脱敏 gd、仅帕鲁 UnitType、first_seen_name 仅明文名）。
- application：新 **`query_dex` mixin**——**须 `class _DexQueries(_PrivacyBase):`**（复核裁定 A2：非脊柱 mixin 用 `self._repo`/`self._meta` 会重蹈 Spec ② mypy attr-defined 炸），声明 `_meta: Any`（及实际用到的 `_cache`/`_clock`），并**加入 `query_service.py` 的 `QueryService(...)` 基类元组**。`dex_progress()` → `DexProgressDTO`。
- domain：`Element` 枚举（火/水/草/电/冰/龙/暗/地/无）→ `domain/enums.py`；`DexProgressDTO` → `application/dtos.py`。
- **降级自洽（复核裁定 D5）**：分母（物种总数）与"缺失清单"**绑同一前置**——roster 不完整/官方总数未知时，**两者一起降级**为仅"已观测 N 种" + 按元素分桶的**已点亮**列表，**不出"缺失"**。
- presentation：`format_dex`；`command_registry.py` 加 `dex` 扁平命令 + `command_permissions` 权限行（feat_group `guilds_bases`）；前端 PAL_TREE 加 `dex` 节点（`group=null`、跨端锚定 `frontend_pal_commands_test` 同步）。
- 口径：写死"**曾被观测到**"≠"服上存在全物种"；缺失只说"尚未被观测"（C2）。

---

## 9. 隐私与就近可见口径（跨切面·承重·全部以测试证实）

- **ip 红线（复核 P1/P2）**：normalizer 不读入模型；fixture 脱敏用 RFC5737 假 ip 且**显式带该字段**；把假 ip 加进 `privacy_test.py::RAW_PLAYER_IPS` 精确匹配元组；新增单测断言 `CharacterActor` 无 ip 属性 + DB 全表无该 ip + 正常/降级日志路径无该 ip。
- **observed_species（复核 P3/P4）**：`first_seen_name` 只取明文名、严禁回退 id；upsert 消费已脱敏 gd、置于 None 短路之后；strict 下 dex 仍只记物种/明文名、无坐标派生（加测试）。
- **me 图片卡（复核 P5）**：`build_me_card_html(dto)` 纯函数只吃 DTO、`html_render(html, {})` 第二参恒空；单测锁 HTML 无坐标/id/player_key。
- **坐标**：4 功能无一暴露精确坐标（复核已核实 presentation 全域无坐标渲染路径）；据点/公会只用派生量（计数/分布/置信度/mood）；strict 沿用现有清坐标+停据点（复核确认覆盖 4 功能，唯 dex 消费 redacted gd 一条须守）。
- **shared_world instance_id 不 hash**（复核 P6）：companion 匹配所必需的内存用途，不落库/不渲染；DTO 边界硬约束闭合外溢，无需 hash。
- **就近可见 C2 / 推导 C4**：me随身/base车间/dex 一律"此刻可见/当前快照/曾观测/推导"措辞，无"全服全量"。

---

## 10. 命令 / 权限 / 前端 / docs

```
world  status|overview|events|today            （overview 解禁后回归可配）
guild  info|base|bases                          base 扩→车间现场（🔥/😴徽章+吐槽+分布+摸鱼率）
player info|bind                                （不变）
me     [hide|show|card|卡|图]                    扩→百分位+随身帕鲁高光；文字/图片双路（互斥单 token）
rank   today|total|level|climb                   加 climb 飞升榜
dex                                              新扁平命令（group=null）：进度总览（feat_group guilds_bases）
```
- 权限：新 `dex` 行 feat_group `guilds_bases`；`climb` 随 `rank`（players）；`me` 图片模式无需新权限。
- 前端 PAL_TREE：解禁 5 节点 + 新增 `dex` 节点（`group=null`，跨端锚定 `frontend_pal_commands_test` 强制两端一致）。
- docs：README/commands.md/configuration.md 回收"暂不可用" + 增补 4 功能说明（含 C2/C4 口径与"词条不支持/需启用 guilds_bases 才有随身"预期管理）；`readme_test.py` 中文锚点同 commit。

---

## 11. 测试策略

- **normalizer 真数据锚点**：脱敏 ActorData fixture（含假 ip）→ 断言按 Type 分流、UnitType 分类、**ip 不入模型**、InGameDays/Time 解析、PalBox 抽取；fixture 落库前 grep 核验无真 IP/GUID。
- **redact 透传**：断言 redact 后 `in_game_days`/`in_game_time` 仍在。
- **元数据覆盖**：actions.json 对样本 token 命中率 + **SLACKING 归类**（InSpa/DodgeWork→slacking）；pals 映射命中 + 降级路径。
- **解禁反转**：lock §5A/§5B 镜像 + conftest `_wire_game_data` 处置 + localStorage 键回收。
- **逐功能**：me_card 百分位(`list_players_by_level`)/随身 join(**`player_userid==player_key` 直比、不重复 hash**)/**随身三态(shown·none_out·no_data；默认无快照部署判 no_data，不谎称"没带")**/图片 HTML 纯函数（无坐标/id/player_key/**绝对时间戳**）+ 图片失败(异常/None/空串)降级 + 名字转义 + **auto 主题两分支(注入固定 clock+tz、`6<=hour<18`)** + **图标 allowlist 取 9 个·缺则降级 emoji**；base 摸鱼率/徽章；rank climb 窗/baseline/gain=max(0)/负增量剔除；dex observed_species 只收帕鲁 UnitType/first_seen_name 仅明文名/进度聚合/降级自洽。
- **隐私**：ip-in-gamedata 不泄（模型/库/日志，RAW_PLAYER_IPS 精确匹配）；坐标不出 4 功能；**离线卡无绝对时间戳(作息)**；strict 覆盖 dex/base；first_seen_name 不含 id。
- **`me_card_theme` 配置贯通（复核 CT1/CT2/CT3）**：`config_view_validate_test`——含 `presentation` 的 body 被**接受**（不再 `invalid_shape`）、非法枚举被拒；前端 `schema.test.ts` object 节数 **8→9** + 新节字段与 schema 对齐；`conf_schema_test` 补 `presentation.me_card_theme` type/options/default；新节控件进设置页产物 no-drift。
- **前端**：解禁 vitest 反转 + dex 节点锚定 + CommandTree/SettingsPanel 横幅移除。
- **产物**：`pages/settings` 重建 no-drift。
- 基线：后端 `pytest -q`、`ruff check .`、`mypy palworld_terminal`；前端 `vitest run`、`typecheck`；`lint-imports` 契约（新 `repo_dex`/`query_dex`/`card_render` 守分层：query_dex↛repo_dex 经 ports、presentation↛adapters）。

---

## 12. 验收标准

1. 全套绿：后端 pytest/ruff/mypy/lint-imports、前端 vitest/typecheck、产物 no-drift。
2. **真数据语义**：normalizer 在脱敏真样本上产出非空且分类正确；`/pal guild base` 显真实行为分布+摸鱼徽章；`/pal me`（文字+图片）显百分位+随身（有 OtomoPal + guilds_bases 启用时）；`/pal rank climb` 显周窗涨幅；`/pal dex` 显已观测物种进度（分母不明时降级）。
3. **隐私（测试证实非口头）**：库/日志/命令输出/图片卡无 ip/原始 id/精确坐标/player_key；strict 覆盖新功能；first_seen_name 无 id。
4. **口径诚实**：输出用"此刻可见/当前快照/曾观测/推导/有记录玩家"，无"全服全量"；"词条/战力"禁区不出现；随身依赖 guilds_bases 的限制如实说明。
5. **图片卡**：`/pal me 卡` 出图；名字转义；渲染失败（异常/None/空）自动降级文字。
6. 元数据：样本真实动作（含摸鱼）/物种在重建后高命中；缺失走降级不炸。
7. 不 bump（沿 finishing 定版）；提交信息不含 Claude。

---

## 附：刻意不做（禁区拦截，防后续再提）
帕鲁词条/被动/IV/凝魂/亲密度（存档非 API）· 战力/配招评分 · 坐标雷达/藏宝图（隐私）· 财富/背包/建筑榜 · 击杀/PVP 战绩 · 亲密度/羁绊天数榜（无个体 ID，跨快照认不出同一只）· 离线公会/据点全量档案（C2）· 本轮不做：自动推送(push)/昼夜皮肤/world now/据点区域分布/新人归来/帕鲁小剧场/`output.me_card_default` 配置键等（留后续）。
