# 中日英三语 i18n 设计（总纲 + Phase 1 详设）

> 状态：定稿待对抗复核。范围：全插件三语（zh-CN / ja / en）。
> 决策记录（2026-07-26 用户拍板）：①覆盖四面=聊天输出（含图片名片）+ 帕鲁名/词条元数据 + 设置页前端 + README/docs；②语言粒度=**全局一种**（不按群/不按服）；③前端语言=**跟随插件 locale**（onboarding 加语言选择步）；④分期=**按层三期**；⑤架构=方案 A（扩展现有 `L()` 全局机制，非注入式、非 gettext）。

## §1 背景与目标

插件当前为纯中文。`world.locale` 配置已存在但纯占位（enum 仅 `zh-CN`，运行时零消费，唯一出现点 `config_view.py:64`）。目标：服主在设置页选一种语言，聊天输出、图片名片、规则措辞、帕鲁名、设置页界面、文档全局切换为该语言。

**成功标准**：`world.locale=ja|en` 下，群聊任意命令输出、图片名片、`/pal help` 均为目标语言且无中文残留（帕鲁名走对应语言官方本地化名）；`zh-CN` 下输出与现状**逐字节相同**（重构零回归）。

## §2 现状勘探（ground truth）

### 2.1 中文分布规模

| 层/面 | 规模 | 性质 |
|---|---|---|
| `presentation/locale.py` | 100 键 | 已抽键部分（`L(key, **kw)` 全局函数，~122 调用点：admin_write_flow 40 / commands 30 / formatters 24 / read_commands 24 / command_support 4） |
| `presentation/formatters.py` | 266 行含中文 | **大量硬编码**：标题、标签映射表（`_ELEMENT_LABEL`/`_ACTION_CAT_LABEL`/`_ACTION_CAT_EMOJI` 中 label 部分/`_RANK_TITLE`/`_CONF_LABEL`/`_SMOOTH_DOT` 键）、行模板、脚注 |
| presentation 其余 | commands 60 / admin_write_flow 55 / card_render 53 / web_api 47 / config_view 44 / read_commands 37 / textkit 28 / event_wording 20 / command_support 20 行 | 硬编码措辞 + 部分注释 |
| **application 泄漏**（用户可见，非注释） | `query_status` 流畅度四档（"流畅/一般/卡顿/严重卡顿"）；`query_support` 规则标签表（"模式/难度/硬核/死亡惩罚/倍率…"）；`report_service`（"平静的一天"、编辑部总结模板）；`name_resolver`（`BASE_FALLBACK="据点"`/`GUILD_FALLBACK="公会"`）；`admin_service`/`query_events`/`guild_service` 待 T1 普查甄别 | **分层债**：用户可见中文下沉到了 application |
| **shared 泄漏** | `command_registry.py:109 HELP_TEXT`（~30 条命令描述中文）| 被 `formatters.format_help` 消费 |
| `main.py` | log 警告（不译）+ AstrBot register 描述（146 行）+ web_api 路由描述（207-213）| 大多不译（见 §9） |
| `metadata/` | `pals.zh-CN.json`（290 条，已有 `name_zh`+`name_en`，**无 `name_ja`**）；`settings.zh-CN.json`（label_zh/unit/enum_map 全中文）；`actions.json`（token→类别，无文案） | 文件名带 locale 后缀但实为单语 |
| 前端 `frontend/src` | schema.ts 114 行 + 组件 ~400 行 | 无 i18n 框架，纯硬编码（Phase 2） |
| `_conf_schema.json` | 85 行中文描述 | AstrBot 原生页无 i18n 机制（见 §9 非目标） |
| README/docs | 全套中文 + readme_test 中文锚 | Phase 3 |

### 2.2 现有机制锚点

- `L(key, **kw)`：`locale.py` 模块级 dict + `str.format` 插值。签名保持不变是方案 A 的核心约束。
- `world.locale`：`_conf_schema.json` options `["zh-CN"]`、前端 schema.ts `options: ['zh-CN']`、`config_view._ENUMS["world.locale"]={"zh-CN"}` 三处白名单。
- `MetadataRepository`：`pal_name()` 读 `name_zh`；`setting_label()/setting_display()` 读 `label_zh`/`enum_map`（enum_map 值全中文）。
- 测试：1332 个测试大量以中文措辞为锚（`format_me_test`"此刻未带出随身帕鲁"等）——zh 抽键阶段的零回归证明就是它们全绿。

## §3 架构设计（Phase 1）

### 3.1 locale 装载器与 fallback 链

```
palworld_terminal/presentation/locales/
  zh-CN.json    # 基线：现有全部措辞逐字迁入
  ja.json       # 键集与 zh-CN 严格相等（静态测试锁）
  en.json       # 同上
```

- `locale.py` 改造为装载器：`load_locale(locale: str) -> None` 按**包位置**解析（`Path(__file__).parent / "locales" / f"{locale}.json"`，绝不走 data_dir/CWD——铁律）；装载进模块级 `_STRINGS`。`L(key, **kw)` 签名与语义不变。
- **fallback 链**：当前语言缺键 → `zh-CN` 字典 → key 字符串本身（防御性，永不抛）。zh-CN 字典恒常驻（作 fallback 层）。
- 非法/未知 locale 值 → 回落 `zh-CN` + 启动 warning（不炸）。
- container `start()` 中、构造任何服务之前调用 `load_locale(cfg.world.locale)`。
- 测试 fixture：conftest 提供 locale reset（默认 zh-CN）；ja/en 用例显式 `load_locale` 且 teardown 复位。

### 3.2 application/shared 泄漏收编（T1，纯重构）

分层契约 `domain<shared<infra<app∥adapters<presentation` 禁止 application/shared 向上取 `L()`。收编方向一律**下层改产稳定键，中文上提 presentation**：

| 泄漏点 | 收编方式 |
|---|---|
| `query_status` 流畅度四档 | 返回稳定键 `smooth/moderate/laggy/very_laggy`（DTO 字段类型不变仍 str）；formatters 处 `L(f"smoothness_{key}")` 渲染；`_SMOOTH_DOT` 映射表改按稳定键索引 |
| `report_service` "平静的一天"/编辑部总结 | DTO 改携带稳定键+计数（如 `summary_kind="quiet_day"` / counts dict）；formatters 渲染 |
| `query_support` 规则标签表 | 整表并入 `metadata/settings.json` 三语字段（本就是设置措辞的家，见 3.3）；application 只留字段名+类型结构 |
| `name_resolver` `BASE_FALLBACK`/`GUILD_FALLBACK` | 常量改哨兵语义：resolver 产 `None`/键，presentation 渲染时经 `L("fallback_base")` 兜底 |
| `shared/command_registry HELP_TEXT` | 文案迁 `locales/*.json`（键 `help_desc_<path>`，path 中空格转下划线）；`HELP_TEXT` dict 从 registry 删除，`format_help` 改经 `L()` 取。registry 只留命令结构（DISPATCH/FLAT_ACTIONS/门控元数据） |
| `admin_service`/`query_events`/`guild_service` 等待甄别行 | T1 用 tokenize 普查（区分 docstring/log/用户可见），用户可见者逐一稳定键化；log 不译 |

**架构守卫**（收编完成后生效）：静态测试扫描 `application/`+`shared/` 全部字符串 token（排除 docstring/注释/`_log` 调用参数）**无中文**——防回流。

### 3.3 元数据多语（T5）

- `pals.zh-CN.json` → **`pals.json`**（单文件多语字段）：每条 `{name_zh, name_en, name_ja, element_types, ...}`。**加 `name_ja`**，来源 paldb.cc 日文本地化页（`/ja/<英文名>`），Workflow 批量研究 + 逐条对抗验证（沿用 2026-07-25 中文名回填 25 种的成功模式）。290 条中确查不到日名者（如 0.2 批自造占位种）进**显式豁免表**（测试引用），运行时 fallback 链 `name_ja → name_en → name_zh`。
- `settings.zh-CN.json` → **`settings.json`**：`label` 拆 `label_zh/label_ja/label_en`；`enum_map` 值拆三语（结构 `{"True": {"zh": "开", "ja": "オン", "en": "On"}}` 或平行三 map，实现取其一并在 plan 定死）；`unit` 三语（"人/秒"等量词）。
- `MetadataRepository` 构造注入 locale（container 装配时传 `cfg.world.locale`，全局单语故一次性）；`pal_name()`/`setting_label()`/`setting_display()` 签名不变，内部按 locale 选字段 + 上述 fallback。`actions.json` 不动。
- 文件改名牵动：`metadata_repository._read` 引用、`metadata_files_test`/`metadata_pals_test` 路径、探针脚本（scratchpad，不阻塞）。**注意：这是包内资源改名，非 AstrBot 落盘 schema 键，无删键铁律风险。**

### 3.4 配置贯通（T3）

`world.locale` 枚举 `{zh-CN}` → `{zh-CN, ja, en}`，三处同步：

1. `_conf_schema.json` `world.locale` options + description；
2. `config_view.py` `_ENUMS["world.locale"]`（三白名单铁律中本次仅 `_ENUMS` 需动——无新增顶层节，`_TOP_KEYS`/形状元组不碰）；
3. 前端 `schema.ts` world 节 locale 字段 `options: ['zh-CN','ja','en']` + `optionLabels`（**语言名用各自母语字面**：简体中文 / 日本語 / English——这三个词条本身不属于任何界面语言，恒定不译）+ `npm run build` 重建产物。

`config.py` 的 world.locale 解析处 `_one_of` 白名单同步扩。

### 3.5 文案抽键规则（T2）

- 键命名沿用现有风格（snake_case、语义前缀分组：`me_card_*`/`base_*`/`rank_*`/`help_desc_*`/`duration_*`…）。
- formatters 的映射表逐项成键：`_ELEMENT_LABEL` → `element_fire`…`element_unknown`；`_ACTION_CAT_LABEL` → `action_working`…；`_RANK_TITLE` → `rank_title_today`…；`_CONF_LABEL` → `confidence_high/medium/low`。emoji 部分（`_ACTION_CAT_EMOJI` 符号、状态点）**不属文案不抽键**。
- `textkit`：时长格式整体成模板键（`duration_dh`="{d}天{h}时" / `duration_hm` / `duration_m`；en="{d}d {h}h" 风格、ja="{d}日{h}時間"）；`rel_date`（今天/昨天）、`fold` 尾行（"…等共 {n} {unit}"）、量词（人/条/项）由调用方改传键。
- `card_render`：内联中文全部抽键；`_ELEMENT_ZH`/`_ACTION_ZH` 与 formatters 同键复用（消依赖重复表）。HTML/Jinja 转义边界不变（`_esc` 只作用于用户自由文本，locale 文案是可信静态）。
- `config_view`/`web_api` 校验错误消息（服主可见、API 返回）：抽键，归 Phase 1（后端串全收）。
- ja/en 模板整句可重排（`{placeholder}` 位置自由），**不引入 ICU/复数规则**：en 计数措辞用恒复数或"{n} player(s)"式回避。

### 3.6 图片名片字体（T6）

`card_render` font-family 按 locale 注入字形栈：zh 保持现状（PingFang SC/Microsoft YaHei）；ja 前置 `"Yu Gothic UI","Yu Gothic","Meiryo","Noto Sans JP"`；en 系统栈即可。`build_me_card_html` 纯函数签名不变（locale 由模板内部经已装载 `L()`/常量表取，或加可选参——plan 定死，倾向前者保签名）。

## §4 语言生效流

```
设置页「世界与展示」locale 下拉（简体中文/日本語/English）
  → 保存 → AstrBot 校验（config_view._ENUMS）→ 落盘 → 插件自动重载
  → container.start(): load_locale(cfg.world.locale) → MetadataRepository(locale)
  → 聊天输出 / 图片名片 / 规则措辞 / 帕鲁名 / help 全局切换
```

- 审计 `detail` 存**当时 locale** 的渲染串，不追溯翻译（历史记录允许混语言）。
- 语言切换后 TTLCache 内旧语言渲染物：查询 DTO 缓存与语言无关（渲染在 formatters 层每次现做）——**须在 T2 核实无"渲染后字符串被缓存"路径**；若有（如 help 缓存），重载本身已清一切内存态，天然无问题（缓存随容器重建）。

## §5 分期

### Phase 1（本 spec 详设）：后端聊天 + 图片卡 + 元数据

| # | 任务 | 性质 | 零回归证明 |
|---|---|---|---|
| T1 | application/shared 泄漏收编（稳定键化 + HELP_TEXT 迁移） | 纯重构 | 1332 测试全绿（中文锚原样） |
| T2 | presentation 全量抽键 → `locales/zh-CN.json`（含 textkit/card_render/config_view/web_api） | 纯重构 | 同上 + 无渲染缓存核实 |
| T3 | 装载机制 + fallback 链 + `world.locale` 三处枚举扩 + 前端产物重建 | 机制 | zh 默认行为不变 |
| T4 | ja/en 全量文案（Workflow 产出 + 对抗校对 + 键集相等测试红→绿） | 翻译 | 键集/参数集静态锁 |
| T5 | `pals.json` name_ja 回填（Workflow ~290 种）+ `settings.json` 三语 + MetadataRepository locale 化 | 数据+机制 | 覆盖率测试 + 豁免表 |
| T6 | 图片名片字体栈 + 三语端到端渲染验收（Edge headless 三语出图目检） | 收口 | 冒烟 + 无中文残留检测 |

### Phase 2：设置页前端（另立 spec）
自研 ~20 行 `t()` + 前端三语 JSON（与后端同构风格）+ onboarding 语言选择步（navigator.language 猜初值，选定写 `world.locale`）+ schema.ts 标签/hint/组件文案抽键。

### Phase 3：文档（另立 spec）
README.ja.md / README.en.md + docs 平行文档 + 顶部语言切换链接。readme_test 策略：**zh 主 README 锚不动**；平行文档结构性断言（章节对齐/链接有效），不逐字锚。

## §6 测试策略（Phase 1）

| 测试 | 断言 |
|---|---|
| 零回归锚 | T1-T3 期间现有 1332 测试中文锚原样全绿 |
| 键集相等（静态） | 三 JSON 键集严格相等；每键 `{placeholder}` 集相等（`string.Formatter().parse` 提取）；新增键漏译即红 |
| ja/en 冒烟 | 各装载渲染代表 formatter（status/me/base/dex/help/server 写回执），断言目标语措辞样例 + **中文残留检测**（CJK 统一表意文字区码点检测；ja 的汉字属日文语境豁免——检测器按"简中特有措辞词表"或 en-only 严格中文零容忍 + ja 白名单法，plan 定死） |
| 架构守卫 | application/shared 字符串 token 无中文（排 docstring/注释/log） |
| name_ja 覆盖率 | pals.json 全条目 name_ja 非空或在豁免表 |
| fallback | 缺键→zh、缺 name_ja→name_en→name_zh、非法 locale→zh+warning |
| fixture | locale reset（默认 zh-CN）；ja/en 用例显式装载+复位 |

## §7 风险与对策

| 风险 | 对策 |
|---|---|
| 翻译质量（~300 键 ×2 语） | Workflow 产出（棱镜：游戏术语官方对齐/语气一致/占位符完整）+ 对抗校对轮 + 交付你一份**关键措辞三语对照表**抽查 |
| 帕鲁日名准确性 | paldb.cc 日文本地化页为源 + 逐条对抗验证（同中文名回填成功模式）；查不到进豁免表不硬造 |
| 抽键遗漏（600+ 行） | T2 收尾跑"中文残留全仓扫描"（presentation 运行时串零中文，注释豁免）；ja/en 冒烟兜底 |
| 图片卡日文字体缺字 | 字形栈多级 fallback + T6 实渲目检（假名/汉字混排样例） |
| `settings.json` enum_map 结构变更破坏现有消费 | `setting_display` 单点消费，签名不变内部适配；`conf_schema_test`/`readme_test` 锚不涉 |
| 测试全局态串扰 | conftest autouse reset fixture |

## §8 非目标（明确不做）

- **按群/按服语言**：不做（全局一种已拍板）。locale JSON 与装载器设计不封死该路（将来加注入层即可），但本期零投入。
- **`_conf_schema.json` 描述串翻译**：AstrBot 原生设置页无 i18n 机制，静态文件无法随 locale 动态化——保持中文（服主主界面是插件自有设置页，Phase 2 覆盖）。
- **开发者日志（`_log.*`）**：不译。
- **审计历史追溯翻译**：不做。
- **AstrBot register 描述 / web_api 路由描述（main.py:146,207-213）**：AstrBot 平台侧展示，保持中文。
- **ICU MessageFormat / 复数引擎**：不引入。
- **metadata.yaml 市场描述**：不动。
- **README/docs**：Phase 3。

## §9 Phase 1 验收

1. `world.locale` 三值可选、保存重载后全局生效；
2. zh-CN 下全部输出与改造前逐字相同（1332 测试锚证明）；
3. ja/en 下：`/pal world status`、`/pal me`（文字+图片卡）、`/pal guild base`、`/pal dex`、`/pal help`、server 写回执均为目标语言、无中文残留（ja 汉字豁免）、帕鲁名为对应语言官方名；
4. 键集相等/架构守卫/覆盖率/fallback 测试全绿；`ruff`/`mypy`/`lint-imports`/前端 `vitest`+`typecheck`+产物 no-drift 全绿。
