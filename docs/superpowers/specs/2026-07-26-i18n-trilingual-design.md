# 中日英三语 i18n 设计（总纲 + Phase 1 详设）

> 状态：已过四棱镜对抗复核（31 发现：30 真全数落改，1 证伪弃）。基线 commit：dd3b048。
> 决策记录（2026-07-26 用户拍板）：①覆盖四面=聊天输出（含图片名片）+ 帕鲁名/词条元数据 + 设置页前端 + README/docs；②语言粒度=**全局一种**（不按群/不按服）；③前端语言=**跟随插件 locale**（onboarding 加语言选择步）；④分期=**按层三期**；⑤架构=方案 A（扩展现有 `L()` 全局机制，非注入式、非 gettext）。

## §1 背景与目标

插件当前为纯中文。`world.locale` 配置已存在但纯占位：`config.py:94/475` 定义并裸解析进 WorldConfig、三处白名单（`_conf_schema.json` options / 前端 schema.ts / `config_view._ENUMS`）锁定 `{zh-CN}`，运行时无任何消费分支。目标：服主在设置页选一种语言，聊天输出、图片名片、规则措辞、帕鲁名、设置页界面、文档全局切换为该语言。

**成功标准**：`world.locale=ja|en` 下，群聊任意命令输出、图片名片、`/pal help`、`/pal dex` 均为目标语言且无简中残留（帕鲁名走对应语言官方本地化名）；`zh-CN` 下**端到端输出**与现状逐字节相同（重构零回归，见 §6 两档锚的定义）。

## §2 现状勘探（ground truth，基线 dd3b048）

### 2.1 中文分布规模

> 口径注意：下表「行数」是**含注释/docstring 的中文行**，非可抽串数。可抽面以 T1/T2 的 tokenize 普查（区分 docstring/log/用户可见）为准——已知偏差：`read_commands` 37 行中硬编码中文串 ≈0（26 处已全走 `L()`）；`config_view` 44 行**全为注释/docstring，运行时零中文**（校验错误是稳定英文 code 契约，见 §3.5）。

| 层/面 | 规模 | 性质 |
|---|---|---|
| `presentation/locale.py` | **110 键** | 已抽键部分（`L(key, **kw)` 全局函数 + 公开 `MESSAGES` dict，**129 调用点**：admin_write_flow 40 / commands 30 / read_commands 26 / formatters 28 / command_support 5）。**3 个测试文件模块级 `import MESSAGES` 并断言内容**（locale_test / locale_rework_test / help_interception_redesign_test）；`locale_test.test_missing_key_raises` 锚定缺键抛 KeyError |
| `presentation/formatters.py` | 266 行含中文 | **大量硬编码**：标题、行模板、脚注 + **七张映射表**：`_ELEMENT_LABEL` / `_ACTION_CAT_LABEL` / `_RANK_TITLE` / `_CONF_LABEL` / `_PING_LABEL`（优秀/正常/偏高/未知）/ `_SKIP_REASON`（名称为空/重复/非法字符/缺凭据）/ `_GROUP_LABEL`+`_FLAT_LABEL`（help 组头：世界/公会/…/其他）+ 健康三档、状态点词等内联词组 |
| presentation 其余 | commands 60 / admin_write_flow 55 / card_render 53 / read_commands 37* / textkit 28 / event_wording 20 / command_support 20* | 硬编码措辞（*见口径注意） |
| `presentation/web_api.py` | 运行时中文仅 **2 处** | `:225` 迁移注记（**落盘数据**）、`:298` 清理警告串；其余为注释/路由描述（不译，§9） |
| **application 泄漏**（用户可见） | `query_status` 流畅度四档（"流畅/一般/卡顿/严重卡顿"——**两个消费方**：formatters + `config_view.status_rows:281`→web_api `/status/overview`→前端 StatusPanel **按中文字面着色**）；`query_support._RULES_SECTIONS`（**策展短标签**，与 settings.json `label_zh` 在 19 字段中 **14 个措辞不同**，另含四个节标题"模式/倍率/节奏/上限"）；`query_events._render_rule_value`（"N 小时/N 分钟"单位词 + 隐私注记，随 **RulesDTO 缓存 1800s**）；`report_service`（"平静的一天"、编辑部总结）；`name_resolver`（`BASE_FALLBACK="据点"`/`GUILD_FALLBACK="公会"`）；`admin_service`/`guild_service` 等待 T1 普查甄别 | **分层债** |
| **shared 泄漏** | `command_registry.py:109 HELP_TEXT`（~30 条命令描述中文）| 被 `formatters.format_help` 消费；**2 个测试文件顶层 `import HELP_TEXT`** 且 `formatters_hierarchy_test` 锚 `set(HELP_TEXT) ↔ PAL_COMMAND_STRINGS` 双向全等（防漂移锚） |
| `main.py` | log 警告（不译）+ AstrBot register 描述 + web_api 路由描述（207-223）| 大多不译（§9） |
| `metadata/` | `pals.zh-CN.json` **310 条**（双键族：137 条 `PalDataParameter/X` 前缀键 + 173 条裸键，约 137 物种双键重复收录，另 ~5 条英文名别名键；**独立物种 ~167**。已有 `name_zh`+`name_en`，无 `name_ja`）；`settings.zh-CN.json` 69 字段（字段名已是 `label_zh`；`enum_map` 键为**小写** "true"/"false" 及原始 token 如 "None"/"Item"）；`actions.json`（token→类别，无文案） | 文件名带 locale 后缀但实为单语 |
| 前端 `frontend/src` | schema.ts 153 行 + 组件 ~400 行 | 无 i18n 框架（Phase 2） |
| `_conf_schema.json` | 85 行中文描述 | AstrBot 原生页无 i18n 机制（§9 非目标） |
| README/docs | 全套中文 + readme_test 中文锚；`docs/configuration.md` 有"当前版本仅支持 zh-CN"句（无锚） | Phase 3（例外见 §3.4-5） |

### 2.2 现有机制锚点

- `L(key, **kw)`：模块级 `MESSAGES` dict + `str.format` 插值，缺键抛 KeyError。签名保持不变是方案 A 的核心约束；**缺键行为将有意变更**（§3.1）。
- `world.locale` 三处白名单 + `config.py:475` 裸 `str()` 解析（**无 `_one_of`**，校验是新增不是"扩"）。
- `MetadataRepository`：`pal_name()` 读 `name_zh`；`setting_label()/setting_display()` 读 `label_zh`/`enum_map`。
- **dex 落库链**：`snapshot_service.ingest_game_data` 把 `pal_name()` 结果**落库**写 `observed_species.species_name`，`query_dex` 直接读 DB 列构桶（不经 meta）——该表永久累积不 prune，`ON CONFLICT` 仅再观测才刷新。
- 测试：**1333 个**，大量以中文措辞为锚。

## §3 架构设计（Phase 1）

### 3.1 locale 装载器与 fallback 链

```
palworld_terminal/presentation/locales/
  zh-CN.json    # 基线：现有全部措辞逐字迁入
  ja.json       # 键集与 zh-CN 严格相等（静态测试锁）
  en.json       # 同上
```

- `locale.py` 改造为装载器：`load_locale(locale: str) -> None` 按**包位置**解析（`Path(__file__).parent / "locales" / f"{locale}.json"`，绝不走 data_dir/CWD——铁律）。
- **`MESSAGES` 对外契约保留**：公开名 `MESSAGES` 恒驻 = **zh-CN 基线字典**（import 时装载、永不随 `load_locale` 重绑/变异，兼作 fallback 层）——3 个直接 `import MESSAGES` 断言内容的测试文件零改动仍绿。`load_locale` 只重绑私有 `_ACTIVE`。
- `L(key, **kw)` **签名不变**（129 调用点零改动）；**缺键行为有意变更**：抛 KeyError → fallback 链（`_ACTIVE` 缺键 → `MESSAGES`(zh) → key 字符串本身，永不抛）。牵动测试：`locale_test.test_missing_key_raises` 改锚 fallback 返回 key 本身（列入 §6 测试迁移面）。
- 非法/未知 locale 值 → `load_locale` 回落 zh-CN + 启动 warning（**唯一校验/回落/告警点**，config 层保持裸透传，见 §3.4）。
- container `start()` 中、构造任何服务之前调用 `load_locale(cfg.world.locale)`。
- 测试 fixture：conftest autouse reset（默认 zh-CN）；ja/en 用例显式装载 + teardown 复位。

### 3.2 application/shared 泄漏收编（T1，重构 + 测试锚迁移）

分层契约禁止 application/shared 向上取 `L()`。收编方向一律**下层改产稳定键，中文上提 presentation**：

| 泄漏点 | 收编方式 |
|---|---|
| `query_status` 流畅度四档 | DTO 改产稳定键 `smooth/moderate/laggy/very_laggy`。**两个消费方同步**：① formatters 处 `L(f"smoothness_{key}")` 渲染，`_SMOOTH_DOT` 改按稳定键索引；② **`config_view.status_rows:281` 同为 presentation 边界，就地经 `L(f"smoothness_{key}")` 渲染后下发**——设置页 API 契约保持本地化串，前端 StatusPanel（按中文字面着色）Phase 1 **零改动**；Phase 2 再议改发稳定键+前端映射。牵动测试：`query_service_status_test:80` 改锚稳定键；`config_view_status_test`/`web_api_read_test` 仍锚中文（服务端渲染后仍绿）；**新增一条非 mock 的 query_status→status_rows 贯通测试**（堵 mock 盲区） |
| `query_support._RULES_SECTIONS` 策展标签 | **不复用 settings.json `label_zh`**（14/19 措辞不同，复用即改 zh 输出）。策展短标签 + 四个节标题（模式/倍率/节奏/上限）作为 **presentation locale 键**（`rules_label_*`/`rules_section_*`）；`RuleSection` 结构改携带稳定字段键+原始值+kind，**值渲染（倍率/enum/小时/分钟）上提 formatters**；zh 键值与现行措辞逐字一致保 golden 锚 |
| `query_events._render_rule_value` 单位词 + 隐私注记 | 随上条一并上提 formatters（application 只产数值+kind）；RulesDTO 从此不含渲染串 |
| `report_service` "平静的一天"/编辑部总结 | DTO 改携带稳定键+计数（`summary_kind="quiet_day"` / counts）；formatters 渲染。牵动 report_service 相关测试改锚稳定键 |
| `name_resolver` `BASE_FALLBACK`/`GUILD_FALLBACK` | resolver 产 `None`/稳定键，presentation 渲染时 `L("fallback_base")` 兜底。牵动 name_resolver 测试改锚 |
| `shared/command_registry HELP_TEXT` | 文案迁 `locales/*.json`（键 `help_desc_<path>`，空格转下划线）；`HELP_TEXT` dict 从 registry 删除，`format_help` 经 `L()` 取。**牵动测试**：`formatters_hierarchy_test`/`formatters_admin_help_test` 顶层 `import HELP_TEXT`（删除即 collection ImportError）——双向全等防漂移锚**迁移重设计**为「zh-CN.json `help_desc_*` 键集 ↔ `PAL_COMMAND_STRINGS` 全等」静态测试 |
| `admin_service`/`guild_service` 等待甄别行 | T1 tokenize 普查（区分 docstring/log/用户可见），用户可见者逐一稳定键化；log 不译 |

**架构守卫**（收编完成后生效）：静态测试扫描 `application/`+`shared/` 全部字符串 token（排除 docstring/注释/`_log` 调用参数）**无中文**——防回流。

### 3.3 元数据多语（T5）

- `pals.zh-CN.json` → **`pals.json`**（单文件多语字段）：每条加 `name_ja`。**结构事实**：310 条 = 137 `PalDataParameter/` 前缀键 + 173 裸键（~137 物种双键重复）+ ~5 英文名别名键，**独立物种 ~167**。T5 按独立物种**去重研究**（paldb.cc 日文本地化页 `/ja/<英文名>`），研究后**扇出写回全部同物种键**（含前缀键/别名键），覆盖率测试加**同物种键值一致性断言**。分片：≤25 种/批 fan-out research + 逐条对抗验证（沿用 2026-07-25 中文名回填模式），批间合并后跑全量覆盖率。确查不到日名者（0.2 批自造占位种 ~4-5 条）进**显式豁免表**，运行时 fallback `name_ja → name_en → name_zh`。
- `settings.zh-CN.json` → **`settings.json`**：`label_zh` **已存在**，**新增** `label_ja`/`label_en`；`enum_map` 值拆三语——示例（键为**小写**/原始 token，与现数据及 `setting_display` 的 `key.lower()` 派生对齐）：`{"true": {"zh": "开", "ja": "オン", "en": "On"}, "None": {...}}`（或平行三 map，plan 定死取一）；`unit` 三语。
- `MetadataRepository` 构造注入 locale；`pal_name()`/`setting_label()`/`setting_display()` 签名不变，内部按 locale 选字段 + fallback。`actions.json` 不动。
- **dex 落库名修正（对抗复核 critical）**：`observed_species.species_name` 是 ingest 时落库的渲染名，切语言后历史行永不刷新 → 图鉴语言混杂。**修法**：`query_dex` 构桶改按 `species_class` 经 `meta.pal_name()` **查询时现解**；DB `species_name` 降级为「未知 class 兜底/调试字段」（ingest 照旧写入，不再作展示真相源）。§6 加「locale 切换后 dex 全目标语言」测试。
- 文件改名牵动（grep 实测）：`metadata_repository._read` 引用、`metadata_files_test`、**`metadata_seed_test`（4 处硬编码旧文件名）**、`enums.py` docstring、`docs/real-server-checklist.md` 两处引用；~~`metadata_pals_test`~~ 经 `MetadataRepository.load()` 间接读**无需改**。探针脚本（scratchpad）不阻塞。包内资源改名非 AstrBot 落盘 schema 键，无删键铁律风险。

### 3.4 配置贯通（T3）

`world.locale` 枚举 `{zh-CN}` → `{zh-CN, ja, en}`，同步面：

1. `_conf_schema.json` `world.locale` options + description；
2. `config_view.py` `_ENUMS["world.locale"]`（三白名单铁律中本次仅 `_ENUMS` 需动）；
3. 前端 `schema.ts` world 节 locale `options` + `optionLabels`（**语言名用各自母语字面**：简体中文 / 日本語 / English，恒定不译）+ `npm run build` 重建产物；
4. `config.py:475` locale 解析**保持裸 `str()` 透传不加 `_one_of`**——`load_locale` 是唯一校验+回落+warning 点（避免 config 层静默归一让 §3.1 的 warning 永不触发）；
5. `docs/configuration.md` locale 行删除"当前版本仅支持 zh-CN"句、改三值说明（该句无 readme_test 锚，零风险，不算破 Phase 3 边界）。

### 3.5 文案抽键规则（T2）

- 键命名沿用现有风格（snake_case、语义前缀：`me_card_*`/`base_*`/`rank_*`/`help_desc_*`/`duration_*`/`smoothness_*`/`rules_*`…）。
- formatters **七张**映射表逐项成键：`_ELEMENT_LABEL`→`element_*`；`_ACTION_CAT_LABEL`→`action_*`；`_RANK_TITLE`→`rank_title_*`；`_CONF_LABEL`→`confidence_*`；`_PING_LABEL`→`ping_*`；`_SKIP_REASON`→`skip_reason_*`；`_GROUP_LABEL`/`_FLAT_LABEL`→`help_group_*`。健康三档/状态点词等内联词组归 T2 全量抽键。emoji/符号不属文案不抽。
- `textkit`：时长模板键（`duration_dh`="{d}天{h}时"、`duration_hm`、`duration_m`；en="{d}d {h}h" 风格、ja="{d}日{h}時間"）；`rel_date`（今天/昨天）；`fold` 尾行；量词（人/条/项）调用方改传键。**结构性比较修正（对抗复核）**：`formatters.format_events:299` 现以渲染串字面 `day == "今天"` 判"今天条目带 HH:MM"——rel_date 本地化后 ja/en 下永不命中。改语义判断（rel_date 返回结构化档位，或比较双方同经 `L("rel_today")`）；events 今天分支纳入 §6 ja/en 冒烟。
- `card_render`：内联中文全抽键；`_ELEMENT_ZH`/`_ACTION_ZH` 与 formatters 同键复用。`_esc` 转义边界不变。
- **`config_view` 无抽键面**（校验错误是稳定英文 code 契约，前端按 code 映射中文——Phase 2 处理其文案；config_view 本期仅 §3.4 动 `_ENUMS`）。**`web_api` 仅 2 处**：`:225` 迁移注记为**落盘数据**（data-at-rest）——**不译**（参照 §4 审计政策）；`:298` 清理警告抽键。
- `command_support._ME_CARD_TOKENS`（`card/卡/图` 输入别名）：**三语通收**（中文别名在任何 locale 下继续可用，输入别名非输出文案）+ 中文残留扫描豁免。
- ja/en 模板整句可重排（`{placeholder}` 位置自由），不引入 ICU：en 计数措辞用恒复数或 "{n} player(s)" 式回避。

### 3.6 图片名片字体（T6）

`card_render` font-family 按 locale 注入字形栈：zh 现状不变；ja 前置 `"Yu Gothic UI","Yu Gothic","Meiryo","Noto Sans JP"`；en 系统栈即可。`build_me_card_html` 纯函数签名不变（字体栈经模板内部按已装载 locale 取；隐私/转义断言不涉）。

## §4 语言生效流

```
设置页「世界与展示」locale 下拉（简体中文/日本語/English）
  → 保存 → AstrBot 校验（config_view._ENUMS）→ 落盘 → 插件自动重载
  → container.start(): load_locale(cfg.world.locale) → MetadataRepository(locale)
  → 聊天输出 / 图片名片 / 规则措辞 / 帕鲁名 / help / 设置页状态行 全局切换
```

- **缓存事实修正（对抗复核）**：RulesDTO（TTL 1800s）与 StatusDTO.detail.rules（15s）**确实缓存渲染串**——语言一致性由「保存 locale → 插件重载 → 全部内存缓存随容器重建」保证，而非"缓存与语言无关"。T1 收编后 RulesDTO 不再含渲染串（§3.2），残余渲染串缓存以重载清空兜底。
- 审计 `detail` 与 web_api `:225` 迁移注记等**落盘串**：存当时 locale 渲染（或既有中文），不追溯翻译。
- 开发者日志（`_log.*`）不译。

## §5 分期

### Phase 1（本 spec 详设）：后端聊天 + 图片卡 + 元数据

| # | 任务 | 性质 | 验证门（见 §6 两档锚） |
|---|---|---|---|
| T1 | application/shared 泄漏收编（稳定键化 + HELP_TEXT 迁移 + smoothness 双消费方） | 重构+锚迁移 | 端到端输出锚原样全绿；**测试迁移面**（§6）同步改锚稳定键 |
| T2 | presentation 全量抽键 → `locales/zh-CN.json`（含七映射表/textkit/card_render/web_api:298） | 重构 | 同上 + 中文残留全仓扫描（presentation 运行时串零中文，注释/输入别名豁免） |
| T3 | 装载机制 + fallback 链 + `world.locale` 枚举扩（§3.4 五项） + 前端产物重建 | 机制 | zh 默认行为不变；`locale_test` 缺键锚迁移 |
| T4 | ja/en 全量文案（**按语言分两次** Workflow 产出 + 对抗校对；键集相等测试红→绿） | 翻译 | 键集/参数集静态锁 |
| T5 | `pals.json` name_ja（**~167 独立物种去重研究、≤25/批分片、扇出同物种键**）+ `settings.json` 三语 + MetadataRepository locale 化 + **dex 现解改造** | 数据+机制 | 覆盖率+一致性+豁免表；dex 切语言测试 |
| T6 | 图片名片字体栈 + 三语端到端渲染验收（Edge headless 三语出图目检） | 收口 | 冒烟 + 残留检测 |

### Phase 2：设置页前端（另立 spec）
自研 ~20 行 `t()` + 前端三语 JSON + onboarding 语言选择步（navigator.language 猜初值）+ schema.ts/组件抽键 + 设置页状态行稳定键化再议（§3.2①遗留）+ config_view error code 的前端文案映射三语。

### Phase 3：文档（另立 spec）
README.ja.md / README.en.md + docs 平行文档 + 语言切换链接。readme_test 策略：zh 主 README 锚不动；平行文档结构性断言，不逐字锚。

## §6 测试策略（Phase 1）

**两档零回归锚（对抗复核修正）**：

- **档一·端到端输出锚（原样全绿）**：formatters/golden/集成测试对**渲染输出**的中文断言，T1-T3 期间逐字不变——这是"zh 逐字节相同"的证明主体。
- **档二·须随重构迁移的测试面（显式清单，同 commit 改锚）**：`locale_test.test_missing_key_raises`（KeyError→fallback 返 key）；`formatters_hierarchy_test`/`formatters_admin_help_test`（HELP_TEXT import + 双向全等锚→`help_desc_*` 键集全等）；`query_service_status_test:80`（中文四档→稳定键）；report_service/name_resolver/query_service_bases 等 application 层直断中文的单测（→稳定键）；`config_view_status_test`/`web_api_read_test`（服务端渲染后**仍锚中文仍绿**，不迁）；3 个 `import MESSAGES` 文件（MESSAGES 契约保留，**不迁**）。

| 测试 | 断言 |
|---|---|
| 键集相等（静态） | 三 JSON 键集严格相等；每键 `{placeholder}` 集相等（`string.Formatter().parse`）；漏译即红 |
| ja/en 冒烟 | 各装载渲染代表 formatter（status/me/base/dex/help/server 写回执/**events 今天分支**），断言目标语措辞样例 |
| **中文残留检测（定案）** | **en：CJK 统一表意文字零容忍**（输入别名豁免）；**ja：检测 zh-CN.json 中长度 ≥4 的值片段残留于输出**（日文汉字合法、无法按字符集判，改按简中整句措辞残留判）+ T6 人工目检兜底 |
| 贯通测试（新增） | 非 mock 的 query_status→config_view.status_rows 贯通（smoothness 服务端渲染，堵 mock 盲区） |
| dex 语言切换 | ingest（zh）→ 切 ja 装载 → `dex_progress` 全目标语言名（历史行经现解覆盖） |
| 架构守卫 | application/shared 字符串 token 无中文（排 docstring/注释/log） |
| name_ja 覆盖率 | pals.json 全条目 name_ja 非空或在豁免表；**同物种多键值一致** |
| fallback | 缺键→zh→key；name_ja→name_en→name_zh；非法 locale→zh+warning（load_locale 处） |
| fixture | conftest autouse reset（默认 zh-CN） |

## §7 风险与对策

| 风险 | 对策 |
|---|---|
| 翻译质量（~350 键 ×2 语） | 按语言分两次 Workflow 产出（棱镜：游戏术语官方对齐/语气一致/占位符完整）+ 对抗校对轮 + 交付**关键措辞三语对照表**抽查 |
| **批量规模超上下文** | T4 按语言分片、T5 按 ≤25 物种/批 fan-out（310 条经 ~167 物种去重后扇出写回） |
| 帕鲁日名准确性 | paldb.cc 日文页为源 + 逐条对抗验证；查不到进豁免表不硬造 |
| 抽键遗漏 | T2 收尾中文残留全仓扫描 + ja/en 冒烟兜底 |
| 图片卡日文字体缺字 | 字形栈多级 fallback + T6 实渲目检（假名/汉字混排样例） |
| 测试全局态串扰 | conftest autouse reset fixture（当前测试套无 xdist 并行） |
| 设置页状态行回归（smoothness） | §3.2① 服务端渲染方案 + 贯通测试；前端零改动 |

## §8 非目标（明确不做）

- 按群/按服语言（全局一种已拍板；装载器设计不封死将来注入层）。
- `_conf_schema.json` 描述串翻译（AstrBot 原生页无机制；服主主界面是插件自有设置页，Phase 2 覆盖）。
- 开发者日志（`_log.*`）、审计历史追溯、web_api `:225` 落盘迁移注记翻译。
- AstrBot register 描述 / web_api 路由描述（main.py:146,207-223）。
- config_view 校验错误 code 的服务端本地化（code 契约保持，前端映射归 Phase 2）。
- ICU MessageFormat / 复数引擎；metadata.yaml 市场描述；README/docs（Phase 3，例外：§3.4-5 的 configuration.md 单句）。

## §9 Phase 1 验收

1. `world.locale` 三值可选、保存重载后全局生效；
2. zh-CN 下端到端输出与改造前逐字相同（§6 档一锚证明；档二清单为显式迁移非回归）；
3. ja/en 下：`/pal world status`、`/pal me`（文字+图片卡）、`/pal guild base`、`/pal dex`（**含 locale 切换前的历史观测行**）、`/pal help`、`/pal world rules`、server 写回执均为目标语言、无简中残留（§6 检测定案口径）、帕鲁名为对应语言官方名；设置页状态行流畅度词随 locale；
4. 键集相等/贯通/架构守卫/覆盖率/fallback/dex 切换测试全绿；现有全部测试（迁移面按 §6 档二处理后）全绿；`ruff`/`mypy`/`lint-imports`/前端 `vitest`+`typecheck`+产物 no-drift 全绿。
