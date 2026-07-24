# game-data 上线娱乐向功能 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现。步骤用 checkbox（`- [ ]`）跟踪。
> **需求真源**：`docs/superpowers/specs/2026-07-24-gamedata-live-features-design.md`（两轮对抗复核定稿，42 处修讫）。每个任务的 brief 都随附该 spec 路径——**字段清单/确切值/口径以 spec 对应 §节为准**，本计划给任务边界、TDD 循环、承重测试与接口。

**Goal:** 修 normalizer 适配真实 game-data ActorData 契约、解禁 game-data 管线、重建元数据，并在验证过的数据上落地 4 个娱乐向功能（我的名片[文字/图片] · 据点车间现场 · 排行榜飞升榜 · 服务器图鉴），严守隐私/就近可见口径。

**Architecture:** 六边形分层（domain<shared<infra<app∥adapters<presentation；presentation↛adapters，import-linter 契约）。核心洞察：`GameDataSnapshot(characters[]+palboxes[])` 二桶结构不变，只改 normalizer 解析 → 下游零改动。QueryService 5-mixin 脊柱（新 mixin 须继承 `_PrivacyBase`）。图片卡走 AstrBot `Star.html_render`。

**Tech Stack:** Python（AstrBot 插件，相对导入）+ Vue3/reka-ui + Vitest/pytest + import-linter。

## Global Constraints（每任务隐含包含）

- 包内 Python 一律**相对导入**（有静态防回归测试 no_absolute_self_import）。
- **隐私红线（测试证实非口头）**：`ip` 永不入模型/库/日志；`userid` HMAC；精确坐标不出公共命令；离线卡无绝对时间戳。玩家名/公会名明文可。
- **就近可见 C2**：一切统计"此刻可见/当前快照/曾观测"口径，禁"全服全量"。**公会/据点推导 C4** 保留"推导/置信度"免责。
- **QueryService mixin 脊柱铁律**：新/改 mixin 用 `self._repo/_meta/_cache/_clock/_world_cache` 须在本 mixin 或共享基类声明注解，否则 mypy attr-defined 炸（Spec ② 教训）。
- **app↛adapters**：application 经 `ports.py` 端口访问持久化，不直导 `repo_*`；presentation 不导 adapters。
- **AstrBot schema 铁律**：`_conf_schema.json` 裁键落盘，严禁删 schema 键；新增顶层配置节须同步 `config_view.py` 的 `_TOP_KEYS`/形状元组/`_ENUMS` 三处白名单（否则整页存盘被 `invalid_shape` 拒）。
- **元数据/资产按包位置解析**（`Path(__file__).resolve().parent.parent / …`），**不用 data_dir/CWD**。
- 产物 `pages/settings` 只经 `cd frontend && npm run build`（内置 normalize-eol）重建。
- README/docs 中文用词改动与 `tests/unit/readme_test.py` 中文锚点**同 commit**。
- 版本号不 bump（沿 finishing 定版）；提交信息**不含 Claude**（正文与尾行均不提，无 Co-Authored-By）。
- 测试命令：后端 `./.venv/Scripts/python.exe -m pytest -q` + `ruff check .` + `./.venv/Scripts/python.exe -m mypy palworld_terminal` + `lint-imports`；前端 `cd frontend && npx vitest run` + `npm run typecheck`。

## 文件结构（本计划新建/改动）

| 层 | 文件 | 责任 |
|---|---|---|
| adapters | `normalizer.py`(改) | ActorData 解析（Type 分流/UnitType 类别/InGameDays·Time/ip 不入） |
| adapters | `metadata_repository.py`(改) | 载 actions.json/pals.zh-CN.json（真 token）；`icon_repository.py`(新) 载元素 SVG |
| adapters | `repo_dex.py`(新) | observed_species CRUD |
| domain | `models.py`(改·+2字段) `enums.py`(改·+SLACKING/Element) `privacy.py`(改·redact 透传) | |
| shared | `command_permissions.py`(改·清空常量) | 解禁 |
| infra | `migrations.py`(改·observed_species) | |
| application | `ports.py`(改·dex 方法) `snapshot_service.py`(改·dex upsert) `query_players.py`/`query_guild.py`/`query_dex.py`(新) `dtos.py`(改) `config.py`(改·PresentationConfig) | |
| presentation | `card_render.py`(新) `formatters.py`/`read_commands.py`/`command_registry.py`/`command_permissions? `/`config_view.py`/`locale.py`(改) | |
| 前端 | `schema.ts`/`permissions.ts`/`chapters.ts`/`CommandTree.vue`/`SettingsPanel.vue`(改) | 解禁 + dex 节点 + presentation 节 |
| 资产 | `assets/element-icons/*.svg`(已提交) `assets/work-icons/`(预备) | |

---

# 阶段 0 · 数据地基（所有 game-data 功能的前提）

### Task 1: 解禁 game-data 管线（跨端原子）

**Files:**
- Modify: `palworld_terminal/shared/command_permissions.py`（`UPSTREAM_UNAVAILABLE_FEATURES` 清空）
- Modify: `palworld_terminal/config.py`（删上游分流 + `PermissionsConfig.upstream_ineffective_keys`）、`main.py`（删上游告警块）
- Modify: `frontend/src/lib/schema.ts`（5 节点删 unavailable + enableConfigurable 翻 true）、`frontend/src/lib/permissions.ts`（删 unavailable 首判）、`frontend/src/components/CommandTree.vue`（删暂不可用视觉）、`frontend/src/components/SettingsPanel.vue`（删横幅 + localStorage 键）
- Modify（docs）：`README.md`/`docs/commands.md`/`docs/configuration.md`/`_conf_schema.json`（回收"暂不可用"）
- Test（反转，spec §4.1 + lock spec §5A/§5B 镜像）：见下

**Interfaces:** Produces：`guilds_bases` 组恢复可配、`GAME_DATA` 端点可随 guild 命令激活、`overview` 归 guilds_bases 可配。

- [ ] **Step 1（红）**：改 `frontend_pal_commands_test.py` 断言（overview+guild×4 的 `unavailable` 期望消失、`enableConfigurable` 期望 true）→ 先跑现有测试确认红（两端未同步）。
- [ ] **Step 2（后端单点解禁）**：`command_permissions.py` 的 `UPSTREAM_UNAVAILABLE_FEATURES = frozenset()`（清空，**不删常量/函数/force-off 行**——保留休眠，被 enable_configurable 与跨端测试引用；spec §4.1）。
- [ ] **Step 3（lock 专属机件回收）**：删 `config.py` 上游分流收集器 + `PermissionsConfig.upstream_ineffective_keys` 字段 + `main.py` 上游告警块（spec §4.1 §7.4）。
- [ ] **Step 4（前端同提交）**：`schema.ts` 5 节点删 `"unavailable": true`、guild×4 + overview 的 `enableConfigurable` false→true（overview `defaultEnabled` 保持 false）；`permissions.ts` 删 `if (n.unavailable) return false` 两处；`CommandTree.vue` 删"暂不可用"锁定行/徽标；`SettingsPanel.vue` 删横幅块 + `dismissGdBanner` + `palworld-terminal-gd-banner-dismissed` 键。
- [ ] **Step 5（测试反转）**：照 lock spec §5A 清单翻回被反转的既有断言、删 §5B force-off/横幅专属测试；`tests/integration/conftest.py` 的 `_wire_game_data` 改用生产装配（guild 命令开）或删；`namespace_runtime_smoke_test` 注释复位。
- [ ] **Step 6（docs 同提交）**：README/commands.md/configuration.md/_conf_schema.json 回收"暂不可用"文案；跑 `readme_test.py`/`conf_schema_test.py` 绿。
- [ ] **Step 7**：`cd frontend && npm run build` 重建产物（no-drift）；全套绿（pytest+ruff+mypy+lint-imports、vitest+typecheck）。提交（`feat: 解禁 game-data 管线——清空上游不可用集 + 前端镜像 + 回收 lock 机件`）。

### Task 2: normalizer 适配真实 ActorData + 脱敏 fixture

**Files:**
- Modify: `palworld_terminal/adapters/normalizer.py`（`normalize_game_data`）、`palworld_terminal/domain/models.py`（`GameDataSnapshot` +`in_game_days:int`/`in_game_time:str`）、`palworld_terminal/domain/privacy.py`（`redact_game_data` 透传新字段）
- Create: `tests/fixtures/<新>/game-data.json`（脱敏真样本，见 Step 1）、`tests/unit/normalizer_actordata_test.py`
- Modify: `tests/unit/normalizer_game_data_test.py`（旧结构断言更新）

**Interfaces:** Consumes：无。Produces：真数据下 `GameDataSnapshot` 非空、按 UnitType 正确分类；`in_game_days/in_game_time` 可用。

- [ ] **Step 1（脱敏 fixture，隐私承重 spec §4.2/§11）**：沉淀实测真样本——`ip`→`203.0.113.x`（RFC5737）、`userid`/`InstanceID`/`NickName`/`GuildID`→假值（`steam_00001`/`INST-P1`/`Akari`；InstanceID 保 `<hex> : <hex>` 形用假 hex）；**显式带一个假 `ip` 字段**。落库前 `grep` 核验无真 IP 网段/真 32hex GUID。
- [ ] **Step 2（红）**：`normalizer_actordata_test.py` 断言——顶层 `ActorData` 被读、`Type=="Character"`→CharacterActor 且 `unit_type` 取 `UnitType`（Player/BaseCampPal/WildPal/NPC 各命中）、`Type=="PalBox"`→PalBoxActor、`ip` 不在任何 CharacterActor 属性、`in_game_days==590`/`in_game_time=="17:44"`。跑 → 红。
- [ ] **Step 3（改 normalizer）**：读容器 `ci_get(raw,"actordata","actor_data")`（保留 characters/palboxes 旧候选防御回退）；遍历按 `Type` 分流（PalBox→PalBoxActor；否则 CharacterActor，`unit_type=ci_get(item,"unittype","unit_type","type")`——**UnitType 优先**）；顶层 `InGameDays`/`InGameTime` 填新字段；**`ip` 绝不读入模型**。`models.py` 加 `in_game_days:int=0`/`in_game_time:str=""`。
- [ ] **Step 4（redact 透传，架构 A1）**：`redact_game_data` 逐字段重建 `GameDataSnapshot` 处补拷 `in_game_days`/`in_game_time`；加断言"redact 后新字段仍在"。
- [ ] **Step 5**：全套绿；隐私测试 `privacy_test.py` 把假 ip 加进 `RAW_PLAYER_IPS`，断言模型/库/日志无该 ip。提交（`feat: normalizer 适配真实 ActorData 契约（Type 分流/UnitType 类别/游戏内时钟/ip 不入）+ 脱敏 fixture`）。

### Task 3: 元数据全量重建（SLACKING 枚举 + 动作/帕鲁名/元素）

**Files:**
- Modify: `palworld_terminal/domain/enums.py`（`ActionCategory` +`SLACKING`；`Element` 枚举新增）、`metadata/actions.json`、`metadata/pals.zh-CN.json`（BP_*_C→名+元素，复用 `element_types`）
- Test: `tests/unit/metadata_actions_test.py`/`metadata_pals_test.py`（覆盖/降级）

**Interfaces:** Consumes：Task 2 的真 token（fixture）。Produces：真动作→类（含摸鱼）、真 Class→中文名+元素。

- [ ] **Step 1（红）**：断言 `meta.action_category("BP_AIAction_Worker_Working")==WORKING`、`"BP_ActionIdleInSpa"`/`"BP_AIAction_BaseCamp_DodgeWork"`→`SLACKING`、`meta.pal_name("BP_ChickenPal_C")` 命中中文名、`meta.element("BP_LotusDragon_C")=="grass"`。跑 → 红。
- [ ] **Step 2**：`enums.py` `ActionCategory` 加 `SLACKING="slacking"`（spec §4.3 硬前置）；加 `Element` 枚举（火/水/草/电/冰/龙/暗/地/无 → fire/water/…/neutral）。
- [ ] **Step 3**：`actions.json` 按真 token 重建映射（Worker_Working/Mining/Harvesting/Deforest/GenerateEnergy/Feeding→working；InSpa/DodgeWork→slacking；Wait/RandomRest/WaitForWorkable→idle；Approach/Wandering→moving；WildLife/NPC_*→各归；spec §4.3）；保留 unknown 兜底。
- [ ] **Step 4**：`pals.zh-CN.json` 加 `BP_*_C → {中文名}` 映射（paldex 源构建 + strip BP_/_C 兼容 + 显式补缺；元素复用 `element_types`）；`metadata_repository` 加 `element(class)` 方法（未收录→unknown 降级）。
- [ ] **Step 5**：全套绿。提交（`feat: 元数据重建——ActionCategory.SLACKING + 真实 BP_ 动作/帕鲁名/元素映射`）。

### Task 4: observed_species 表 + repo_dex + ports + ingest upsert

**Files:**
- Modify: `palworld_terminal/infrastructure/migrations.py`（`observed_species` 表）、`palworld_terminal/application/ports.py`（Read/Write 端口 dex 方法）、`palworld_terminal/adapters/sqlite_repository.py` 或新 `repo_dex.py`、`palworld_terminal/application/snapshot_service.py`（`ingest_game_data` upsert）
- Test: `tests/unit/repo_dex_test.py`、`tests/unit/snapshot_dex_test.py`

**Interfaces:** Produces：`ReadRepositoryPort.observed_species()`、`WriteRepositoryPort.upsert_observed_species(...)`；`ingest_game_data` 累积物种。

- [ ] **Step 1（红）**：断言——喂含 Player/NPC/PalBox/3 类帕鲁的脱敏 gd，`ingest_game_data` 后 `observed_species` **只含帕鲁 UnitType 物种**（无 `BP_Player_*`/NPC/`BP_BuildObject_*`）；`first_seen_name` 仅取明文名、**永不为 instance_id/userid**；strict 下仍只记物种/明文名。跑 → 红。
- [ ] **Step 2**：`migrations.py` 建表 `observed_species(species_class TEXT PK, species_name TEXT, element TEXT, first_seen_at INT, first_seen_name TEXT, observe_count INT)`（不 prune）。
- [ ] **Step 3**：`ports.py` `ReadRepositoryPort` 加 dex 读、`WriteRepositoryPort` 加 `upsert_observed_species`；`Repository` 结构化实现（`repo_dex.py` 或并入 sqlite_repository）。
- [ ] **Step 4（隐私+口径 spec §4.4）**：`ingest_game_data` 在 `redact_game_data` **之后**、消费已脱敏 `gd`、置于 `guilds/bases is None` 短路**之后**；仅 `UnitType ∈ {OtomoPal,BaseCampPal,WildPal}` upsert；`first_seen_name` 只取 `NickName`/`TrainerNickName`，取不到存 NULL（**严禁回退 id**）。
- [ ] **Step 5**：全套绿（含 lint-imports：snapshot_service 经端口）。提交（`feat: observed_species 表 + 端口 + ingest 累积（仅帕鲁物种/明文名/脱敏后）`）。

---

# 阶段 1 · 排行榜飞升榜（独立，不依赖 game-data 解禁，可并行阶段 0）

### Task 5: rank climb 飞升榜

**Files:**
- Modify: `palworld_terminal/application/query_players.py`（`rank_climb`）、`application/dtos.py`（RankEntry climb 变体）、`presentation/read_commands.py`（rank handler `climb` 模式）、`presentation/formatters.py`（`format_rank` 飞升榜）、`shared/command_registry.py`（rank 描述加 climb）、`presentation/command_support.py`（若列 rank 模式）
- Test: `tests/unit/rank_climb_test.py`、`tests/unit/commands_rank_test.py`

**Interfaces:** Consumes：`player_observations`（level+observed_at，现成）。Produces：`/pal rank climb`。

- [ ] **Step 1（红）**：断言 `rank_climb(window="7d")`——`baseline` = `observed_at ≤ window_start` 最新观测（无则窗内最早）、`current`=最新、`gain=max(0, current−baseline)`、`gain==0` 不上榜、负增量剔除（spec §7）；末尾"你第 N 差 X"。跑 → 红。
- [ ] **Step 2**：`query_players` 加 `rank_climb`（直算 observations 周窗、`gain=max(0,…)`）；`RankEntryDTO` 加 gain 变体；窗深不足措辞"自 bot 记录以来"。
- [ ] **Step 3**：rank handler 加 `climb` 模式解析；`format_rank` 加飞升榜渲染；`command_registry` rank 描述加 climb。
- [ ] **Step 4**：全套绿。提交（`feat: /pal rank climb 飞升榜——周窗 level 涨幅（baseline/gain=max0/负增量剔除）`）。

---

# 阶段 2 · 我的名片 + 据点车间（吃阶段 0）

### Task 6: 我的名片数据层（me_card → MeCardDTO）

**Files:**
- Modify: `palworld_terminal/application/query_players.py`（`me_card` + `_world_cache:Any` 声明）、`application/dtos.py`（`MeCardDTO`/`CompanionView`）、`domain/enums.py`（`Element` 已在 T3）
- Test: `tests/unit/me_card_test.py`

**Interfaces:** Consumes：`shared_world`（脱敏快照）、`list_players_by_level`、`total_durations`、`link_companions`。Produces：`me_card(player_key)->MeCardDTO`。

- [ ] **Step 1（红，承重）**：断言——① 百分位用 `list_players_by_level`（超越有记录玩家 X%）；② **随身 join `Player.player_userid == player_key` 直比**（构造脱敏快照：Player.player_userid 已 hash == player_key，命中取 instance_id→OtomoPal，**不再套 hash**）；③ **三态**：会话在线+快照有+Player 在+无 OtomoPal→`none_out`；无快照→`no_data`（**不谎称没带**）；命中→`shown`；④ 离线（`get_open_session` 空）→ online=False + last_seen/total_seconds，无实时 HP/随身。跑 → 红。
- [ ] **Step 2**：`_RankProfileQueries` 加 `_world_cache:Any` 声明（防 mypy attr-defined）；实现 `me_card`——百分位 via `list_players_by_level`、随身 join 直比 + `link_companions`、`companion_status` 三态（复用 `available=gd is not None` 范式）、离线字段 via `PlayerIdentity.last_seen_at` + `total_durations()`。
- [ ] **Step 3**：`dtos.py` `MeCardDTO`（online/guild_name/hidden/last_seen_at/first_seen_at/total_seconds/today_seconds/percentile/online_seconds/companion/**companion_status**）+ `CompanionView(species_name,element,level,action_label,hp_ratio)`；**离线时间字段 application 层预粗化**（相对天，无绝对时间戳）。
- [ ] **Step 4**：全套绿（mypy 无 attr-defined）。提交（`feat: me_card 数据层——百分位/随身 join 直比/三态/离线字段（隐私预粗化）`）。

### Task 7: 我的名片文字版

**Files:** Modify `presentation/formatters.py`（`format_me` 富化）、`presentation/locale.py`；Test `tests/unit/format_me_test.py`

- [ ] **Step 1（红）**：断言 `format_me(dto)` 四状态文字——满（百分位+随身皮皮龙草 Lv48）/ none_out（"此刻未带出随身帕鲁"）/ no_data（"随身数据暂不可用"）/ 离线（"此刻不在线"+最近上线+累计在线，无 HP/随身）。跑 → 红。
- [ ] **Step 2**：`format_me` 富化（现有 str 路径，四状态分支）；locale 加文案。
- [ ] **Step 3**：全套绿。提交（`feat: /pal me 文字版富化——百分位+随身+四状态`）。

### Task 8: me_card_theme 配置全贯通 + 元素图标加载器

**Files:**
- Modify: `_conf_schema.json`、`palworld_terminal/config.py`（`PresentationConfig`）、`palworld_terminal/presentation/config_view.py`（`_TOP_KEYS`/形状元组/`_ENUMS` 三处）、`frontend/src/lib/schema.ts`（OBJECT_SECTIONS）、`frontend/src/lib/chapters.ts`（blocks）、`docs/configuration.md`
- Create: `palworld_terminal/adapters/icon_repository.py`；Modify `palworld_terminal/container.py`（解析 assets 目录 + 注入 Commands）
- Test: `tests/unit/config_view_validate_test.py`、`frontend/src/lib/schema.test.ts`（8→9）、`tests/unit/conf_schema_test.py`、`tests/unit/icon_repository_test.py`

**Interfaces:** Produces：`cfg.presentation.me_card_theme ∈ {light,dark,auto}`；`icons: dict[element→SVG]` 注入 Commands。

- [ ] **Step 1（红·配置贯通 CT1）**：`config_view_validate_test` 断言——含 `presentation` 的 body **被接受**（不 `invalid_shape`）、`me_card_theme` 非法枚举被拒。跑 → 红（`_TOP_KEYS` 无 presentation）。
- [ ] **Step 2**：`_conf_schema.json` 加 `presentation.me_card_theme`（enum options light/dark/auto，default light）；`config.py` 新 `PresentationConfig` + `AppConfig` 字段 + `_one_of(...,{light,dark,auto},"light")`；**`config_view.py` `_TOP_KEYS`(:42) + 形状元组(:169) + `_ENUMS`(:60) 三处都加 presentation**。
- [ ] **Step 3（前端）**：`schema.ts` OBJECT_SECTIONS 加 presentation 节；`chapters.ts` 把 `'presentation'` 挂进某配置章 `blocks`；`schema.test.ts:34` object 节数 **8→9** + 字段对齐；`conf_schema_test` 补断言。
- [ ] **Step 4（图标加载器 A1/A2/P2）**：`icon_repository.py` `load()` 按 `Element` 枚举名 allowlist 读 `assets/element-icons/<element>.svg`（**不 glob**，缺→降级 emoji）；`container.py` 解析 `Path(__file__).resolve().parent.parent / "assets" / "element-icons"`、`load()` 后注入 `Commands`。`icon_repository_test` 断言 9 元素齐 + 不读 preview.html/png。
- [ ] **Step 5**：`cd frontend && npm run build` no-drift；全套绿（前端 vitest 9 节绿）。提交（`feat: me_card_theme 配置全贯通（含 config_view 三白名单）+ 元素图标加载器（adapters 注入）`）。

### Task 9: 我的名片图片版（card_render + 主题解析 + handler）

**Files:**
- Create: `palworld_terminal/presentation/card_render.py`；Modify `presentation/read_commands.py` 或 commands（`me_card_html`）、`main.py`（handler 图片分支）、`shared/command_registry.py`（me 描述）
- Test: `tests/unit/card_render_test.py`、`tests/unit/commands_me_card_test.py`

**Interfaces:** Consumes：Task 6 DTO、Task 8 icons+cfg。Produces：`/pal me card` 出图。

- [ ] **Step 1（红·纯函数 + 隐私 spec §5/§9-P5）**：`card_render_test` 断言——`build_me_card_html(dto, icons, "light"/"dark")` 输出 HTML **不含坐标/instance_id/player_key/绝对时间戳(epoch/ISO)**；玩家名/公会名转义（含 `{{`/`{%` 的名字被转义）；C1/C3 两主题各出对应结构；四状态渲染。跑 → 红。
- [ ] **Step 2**：`card_render.py` `build_me_card_html(dto, icons, theme)` 纯函数（C1/C3 内联 CSS 模板 + 内联元素 SVG[从 icons] + 转义名字/公会名；无快照/无 I/O/无时钟）。
- [ ] **Step 3（主题解析 A3/A4/CT4）**：`Commands.me_card_html(...)`——`auto`→`datetime.fromtimestamp(self._clock.now(), ZoneInfo(server_timezone(self._cfg, world)))` 当地小时、`6<=hour<18→light` 否则 dark；把已解析 light/dark 传 `build_me_card_html`；auto 边界单测注入固定 clock+tz。
- [ ] **Step 4（handler M7 降级）**：`main.py` me handler——`card`/`卡`/`图` 单 token → `html=commands.me_card_html(...)`；`img=await self.html_render(html,{})`（第二参恒 `{}`）；**抛异常或 None/空串 → `event.plain_result(文字卡)`**；`me hide card` 多 token → 帮助提示（不静默）。
- [ ] **Step 5**：全套绿（lint-imports：card_render↛adapters）。提交（`feat: /pal me card 图片卡——C1/C3 双主题 + auto 时区解析 + 元素图标 + 失败降级`）。

### Task 10: 据点车间现场

**Files:** Modify `application/query_guild.py`（`base` 富化）、`application/dtos.py`（`BaseDetailDTO` +mood/slacker_rate/species_top）、`presentation/formatters.py`（`format_base`）、`presentation/locale.py`；Test `tests/unit/base_workshop_test.py`

**Interfaces:** Consumes：Task 3 SLACKING + 元素、`action_distribution`。

- [ ] **Step 1（红）**：断言 `base(...)` 派生 `slacker_rate`（`slacking` 占比）+ `species_top`（Class→名）；`format_base` 出氛围徽章（🔥热火朝天/😴集体摆烂）+ 摸鱼行 + 分布 emoji；C2 措辞"此刻可见 N 只"。跑 → 红。
- [ ] **Step 2**：`query_guild.base` 富化（复用 `action_distribution` + slacker_rate + species_top）；`BaseDetailDTO` 加字段；`format_base` 徽章/吐槽；locale 模板。
- [ ] **Step 3**：全套绿。提交（`feat: /pal guild base 车间现场——行为分布+摸鱼率+氛围徽章`）。

---

# 阶段 3 · 服务器图鉴（吃阶段 0）

### Task 11: 服务器图鉴 /pal dex

**Files:** Create `palworld_terminal/application/query_dex.py`；Modify `application/query_service.py`（基类元组加 `_DexQueries`）、`application/dtos.py`（`DexProgressDTO`）、`presentation/read_commands.py`（dex handler）、`presentation/formatters.py`（`format_dex`）、`shared/command_registry.py`（dex 扁平命令）、`shared/command_permissions.py`（dex 权限行 feat_group guilds_bases）、`frontend/src/lib/schema.ts`（PAL_TREE dex 节点 group=null）；Test `tests/unit/query_dex_test.py`、`frontend_pal_commands_test.py`（dex 节点）

**Interfaces:** Consumes：Task 4 observed_species + Task 3 元素/总数。Produces：`/pal dex`。

- [ ] **Step 1（红）**：断言 `dex_progress()`——已观测 N / 总数（分母已知时）、按元素分桶；**分母未知 → 分母+缺失清单一起降级**为仅"已观测 N 种"+已点亮列表（不出"缺失"，spec §8 SD5）；口径"曾被观测"。跑 → 红。
- [ ] **Step 2（mixin 脊柱 A2）**：`query_dex.py` `class _DexQueries(_PrivacyBase):` + 声明 `_meta:Any`（及用到的 `_cache`/`_clock`）；`dex_progress()`；`query_service.py` `QueryService(...)` 基类元组加 `_DexQueries`。
- [ ] **Step 3**：`DexProgressDTO`；`format_dex`；`command_registry` dex 扁平命令（group=null，参数内解析，与 rank 对齐）；`command_permissions` dex 权限行 feat_group `guilds_bases`。
- [ ] **Step 4（跨端锚定）**：`schema.ts` PAL_TREE 加 dex 节点（group=null）；`frontend_pal_commands_test` 断言两端一致。
- [ ] **Step 5**：`npm run build` no-drift；全套绿。提交（`feat: /pal dex 服务器图鉴——观测物种进度（脊柱 mixin + 分母/缺失同降级）`）。

---

## Self-Review

- **Spec 覆盖**：§4.1→T1；§4.2→T2；§4.3→T3；§4.4→T4；§7→T5；§5(me 数据/文字/图片/主题/图标)→T6/T7/T8/T9；§6→T10；§8→T11；§9 隐私分散入各 TDD 红步 + T2/T4/T6/T9 承重；§10 命令/权限/前端分散；§11 测试逐任务。无缺口。
- **占位符扫描**：核心承重逻辑（join 直比/三态/auto 时区/config_view 三白名单/图标 allowlist）在步骤内点明；确切字段清单/枚举值引 spec §节（brief 随附 spec）。
- **类型/接口一致**：`me_card(player_key)->MeCardDTO`、`build_me_card_html(dto,icons,theme:light|dark)->str`、`dex_progress()->DexProgressDTO`、`rank_climb(window)`、`upsert_observed_species(...)`/`observed_species()` 前后一致；`companion_status ∈ {shown,none_out,no_data}`；`ActionCategory.SLACKING`/`Element` 枚举 T3 定义、T6/T9/T10/T11 消费。
- **依赖/阶段**：阶段 0（T1-4）为阶段 2/3 前提；阶段 1（T5）独立可并行；T8 配置贯通先于 T9 图片；T6 数据先于 T7/T9；T3 元数据先于 T6/T9/T10/T11。
- **待补（不阻塞 plan，实现中途补）**：OtomoPal 实测样本（校准 T6 随身 join/T9 满态）；工作图标（§6 车间图片化为未来，本轮文字）。

## Execution Handoff

计划保存于 `docs/superpowers/plans/2026-07-24-gamedata-live-features.md`。两种执行方式：
1. **Subagent-Driven（推荐）**——每任务派 fresh subagent + 两阶段评审，快迭代（REQUIRED SUB-SKILL: superpowers:subagent-driven-development）。
2. **Inline**——本会话批量执行 + 检查点（superpowers:executing-plans）。
