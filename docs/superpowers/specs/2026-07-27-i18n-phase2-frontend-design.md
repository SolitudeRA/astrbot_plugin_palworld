# 三语 i18n Phase 2 · 设置页前端 设计（spec）

**日期**：2026-07-27
**前置**：Phase 1（后端聊天/图片名片/元数据三语，PR #40 已合并入 main）。本 spec 是 i18n「按层分三期」的 Phase 2（设置页 Vue 前端），Phase 3（README/docs 平行文档）另立 spec。

## 目标

设置页 Dashboard（Vue3 + reka-ui + Vite 单文件产物，`frontend/` 源 → `pages/settings/` 产物）全部用户可见文案随语言渲染 zh-CN（默认）/ja/en，语言跟随全局 `world.locale`（与 bot 消息同一值，「全局一种语言」）。自建轻量 `t()` 机制（镜像后端 `L()`），组件模板/JS 串 + schema/chapters 数据层文案全覆盖，onboarding 加语言选择步、顶栏加语言切换器。

## 架构

自研 ~20-30 行 `t()`（`frontend/src/lib/i18n.ts`）：reactive `locale` ref + 三份**扁平** key→模板串词典（静态 import 进单文件 bundle）+ fallback 链 `dict[locale]→dict['zh-CN']→key`、永不抛 + `{var}` 插值；模块单例、Vue 上下文外可调。抽键分两套：组件内联串 `t()` 撒点；schema.ts/chapters.ts 数据层按稳定结构键派生键、结构不动、渲染经 `t()` 解析。zh-CN 词典值 = 现有中文串逐字节相同 → zh 渲染零回归。

## 非目标（scope 边界）

- **不译**：品牌名「帕鲁世界终端/PalWorldTerminal」；locale 选项母语名（简体中文/日本語/English，测试已锁恒定不译）；**后端已本地化下发的值**（status 的 smoothness_label、world rules 值、audit action/target——前端只展示，绝不重译）；**option 存储值**（enum 英文值恒不动，只译 optionLabels，否则 collect 往返破）。
- **不碰后端聊天 i18n**（Phase 1 已完成）；**不做** README/docs 平行文档（Phase 3）。
- **不引入** vue-i18n/intl 等第三方库（自建即可，与后端 `L()` 对等）。
- **AstrBot 面板域**（`_conf_schema.json` 齿轮页字段名、`register_web_api` 描述）**保持 zh**——那是 AstrBot Dashboard 而非本插件设置页，跨生态约定单语，范围外。

---

## §1 术语与单一真相源

- **UI locale**（本 spec 主体）= 设置页 Dashboard 的显示语言。
- **message locale** = `world.locale` 配置字段（现 schema.ts 标签「消息语言」），驱动后端 bot 命令输出 + 服务端渲染的 status/rules label。
- **决策（Phase 1 已定「前端跟随插件 locale」+「全局一种」）**：UI locale **复用同一个 `world.locale`**，不引入独立的第二语言概念。三处改语言入口最终都写同一个 `world.locale`：①onboarding 语言步 ②world 设置节的 locale 字段 ③顶栏语言切换器。

## §2 t() 机制契约（`frontend/src/lib/i18n.ts`）

```ts
// 三份扁平词典静态 import（键集必须完全一致，见 §6）
import zhCN from './locales/zh-CN'
import ja from './locales/ja'
import en from './locales/en'

const DICTS = { 'zh-CN': zhCN, ja, en } as const
export type Locale = keyof typeof DICTS
const SUPPORTED: Locale[] = ['zh-CN', 'ja', 'en']

export const locale = ref<Locale>('zh-CN')          // 应用级 reactive 单例
export function setLocale(l: string): void            // 非法值回落 zh-CN；只接受 SUPPORTED
export function guessLocale(): Locale                 // navigator.language.startsWith('ja'|'en') → 否则 zh-CN
export function t(key: string, vars?: Record<string, string | number>): string
```

- **fallback 链**：`DICTS[locale.value][key] ?? DICTS['zh-CN'][key] ?? key`——目标语缺键回退 zh 基线、再缺回退键名字面，**永不抛**（镜像后端 `L()` 的 `_ACTIVE→MESSAGES→key`）。
- **插值**：模板串含 `{name}`/`{n}` 占位，`t(key, {n: 3})` 做字面替换；缺参不抛（留原 `{x}` 或空——实现取「留原样」，便于测试发现漏参）。
- **Vue 上下文无关**：`locale` 是模块级 `ref`，`t()` 是纯函数——`boot.ts` 在 App 挂载前（`main.ts` fallback 渲染阶段）即可 `t()` 出错误文案。**`i18n.ts` 不得 import 任何组件、不依赖 setup 上下文。**
- `guessLocale()` 首帧初值；实际 locale 由 §3 的配置回灌校正。

## §3 locale 来源与三入口切换

**初值（配置到达前的窗口）**：`i18n.ts` 模块加载即 `locale.value = guessLocale()`（navigator.language 猜）。覆盖 boot 早期文案、onboarding 未设置态（此时 config 里 world.locale 可能 undefined）。

**配置回灌（单一真相）**：`SettingsPanel.applyConfig`（现 :114）在每次 load/save 回配置后 `setLocale(state.sections.world.locale)`——UI 随之整体切换。`config/get`（web_api.py:18）响应 `{ok, config: redact_config(raw), page_version}`，`world` 是普通 object 节，`world.locale` 恒在响应里（无需后端改动）。空配置（首次）下 `world.locale` 为 undefined → `setLocale` 回落，保持 `guessLocale()` 初值。

**三入口写回 `world.locale`**：
1. **onboarding 语言步**：`ModeOnboarding` 现为隐式单步（选模式）。改两步：step1 语言选择（radiogroup，`guessLocale()` 默认，**选中即时 `setLocale` 切引导屏 UI**）→ step2 模式。`confirm` 事件带 `{locale, mode}`，`onConfirmMode`（SettingsPanel :182）一并写 `state.sections.world.locale + world_mode + setup_confirmed`，`save()` 落盘。多步范式参照成熟的 `TransferWizard`（STEPS/step ref/next/back）。
2. **world 设置节 locale 字段**：现有（schema.ts:53），保持——在设置页改即落库、`applyConfig` 回灌切 UI。
3. **顶栏语言切换器**：品牌头 mast（App.vue:48-51，与主题按钮同排）放语言下拉（选项标签 = 母语名，恒不译）。选中 `setLocale` 即时切 UI **并写 `world.locale` 落库**（走与 world 字段相同的 save 路径）。放 mast 而非左轨——首次引导态左轨隐藏（App.vue:56 `v-if=!onboarding`），mast 恒显。

**协同**：三入口皆最终改同一个 `world.locale`，`applyConfig` 回灌 `setLocale` 是唯一 UI 切换真相——不产生「UI 语言与配置值不一致」态。

## §4 抽键策略

### §4.1 组件内联串 `t()` 撒点（~265 串）
按区命名空间键：`app.*`（品牌口号/主题按钮/fatal）、`status.*`（观测标签/chip/空态/相对时间）、`audit.*`（表头/结果 chip/分页/空态）、`onboarding.*`、`transfer.*`（含向导多步/OrphanCleanup）、`err.*`（错误码表，见 §4.3）、`common.*`（查看编辑通用词：编辑/取消/完成/移除/修改/已暂存/（未命名）/（未填）/（无）/未设置/已设置/用环境变量——`common` 键组避免各卡片重复）。
- **插值串走带参 `t()`**：`t('saved_partial', {n})`（「已保存，{n} 条无效条目未生效」）、`t('audit_total', {n})`、相对时间/时长 `ago()/fmtUptime()` 的秒/分/时/天单位与「{n} 天 {h} 小时」——三语量词/复数不同，`t()` 接 count 参数按语言给完整句模板（**不用 `msg += ` 分段拼接**，改完整句模板 + 计数参，见 recon transfer notes）。
- **aria-label 也抽**（读屏可见）：章节索引/上一页/下一页/`{name} 详细信息`/`{label} 启用`——拼接型走带参 `t()`。
- **枚举中文化就地转**（组件内，非 schema）：`ServerCard` 的 enabled→启用/停用、verify_tls→是/否、`CommandTree` lockedLabel 恒开/仅管理员/所有人、模式徽章单/多服务器——独立 enum 键组。

### §4.2 数据层抽键（schema.ts / chapters.ts ~164 串）
键**派生自现有稳定结构键**，schema/chapters 保留结构 + 稳定 key 不动，译文进扁平词典，渲染点（Field/SectionForm/CommandTree/App 左轨）经 `t()` 解析：
- 字段：`t('field.<section>.<fieldKey>.label')` / `.hint`（FieldSpec.label/hint，~52+36）
- 章节：`t('section.<key>.title')` / `.subtitle`（OBJECT_SECTIONS，~18）
- 选项：`t('opt.<field>.<value>')`（optionLabels，~13；**存储值不动**）
- 命令组：`t('group.<name>')`（GROUP_LABELS，5）
- 命令：`t('cmd.<path>')`（PAL_TREE 每条 label，30，path 去空格）
- 章标签：`t('chapter.<key>.label')`（CHAPTERS，8）+ 组名（观测/配置，2）
- **PAL_TREE 结构不可动**：仍是可 `json.loads` 的双引号数组（后端 `test_frontend_tree_matches_backend_meta` 跨端锚定 flag 列）——`label` 保留作默认/兜底，另按 `cmd.<path>` 键查表译，绝不重构条目。
- **SettingsPanel.vue:62 的 computed 覆写**（routing 段 title/subtitle='默认查询'/'群里没指定…'）是组件本地串非 schema，单独键化（`section.routing.title` 覆写形按需）。

### §4.3 错误码表三语（`err.<code>` 命名空间）
两张前端错误码表 code = 天然 i18n 键：`SettingsPanel.vue` ERR（9 码：save_in_progress/too_frequent/too_large/invalid_shape/invalid_field/credential_redirect/restart_failed_rolled_back/restart_failed/unauthorized）+ `transfer.ts` TRANSFER_ERR（13 码）。合并到单一 `t('err.<code>')`，未知码走 fallback → 通用「操作失败」。`mapError` 拼的 `：{path}` 冒号也随 locale（用 `t('err_path_sep')` 或 §4.1 标点键）。`errors.ts` 4 条 Error 类兜底 message 一并键化。

### §4.4 opt-out（恒定不译）
见「非目标」：品牌、locale 母语名、后端下发值、option 存储值。`t()` 不触碰这些；组件对后端下发值直接展示。

## §5 状态行稳定键化（跨期 bug 根治）

**问题**：Phase 1 令后端 `status_rows`（config_view.py:284）的 `smoothness_label` 经 `L(f"smoothness_{dto.smoothness_label}")` 按 `world.locale` 本地化下发；前端 `StatusPanel.fpsClass`（:57-59）硬比中文 `label === '流畅'/'一般'` 判色——`world.locale≠zh` 时 label 非中文 → fpsClass 恒失准。

**修**（后端 1 行 + 前端小改）：
- 后端 `config_view.status_rows`：`dto.smoothness_label` **本就是稳定键**（`smooth/moderate/laggy/very_laggy`，query_status 产），在 row dict 里**并行加** `"smoothness": dto.smoothness_label`（与 `"smoothness_label": L(...)` 并存）。
- 前端 `StatusPanel`：类型加 `smoothness?: string`；`fpsClass` 改签名收稳定键 `fpsClass(row.smoothness)`（`smooth→good/moderate→mid/laggy|very_laggy→bad`），不再比中文；`smoothness_label` 仍用于**显示**（后端本地化串，前端不译）。

## §6 零回归 & 测试策略

- **键集奇偶校验**（移植后端 `tests/unit/locale_parity_test.py` 到前端 `src/lib/i18n.test.ts`）：三词典键集**严格相等** + 每键占位符集相等（漏译/漏占位即红）。
- **t() 键存在守卫**：静态或运行时断言「代码里 `t('...')` 引用的每个字面键都存在于词典」（防抽键漏译）。
- **零回归（zh 字节）**：zh-CN 词典每值 = 抽键前该处中文串**逐字节相同** → 组件在 zh 下渲染不变；组件既有快照/文本断言（zh 默认）保持绿。
- **测试迁移（档二显式迁移面）**：按中文串断言的组件测试（ModeOnboarding/ModeTransfer/TransferWizard/CommandTree/schema.test 等）同 commit 迁移到经 `t()`/稳定键断言；**`schema.test.ts:57` 锁 locale optionLabels 母语恒定不译不可破**。
- **跨端 parity 不破**：PAL_TREE 数组仍 `json.loads`-able、后端 `test_frontend_tree_matches_backend_meta` 绿；`_conf_schema.json` 键与 schema.ts 键一致（**严禁删 schema 键**）。
- **状态稳定键回归**：后端加 `smoothness` 键后既有 status_rows 测试同步（加断言稳定键）；前端 StatusPanel 测试改按 `smoothness` 断言 fpsClass。
- **三语目检**：构建后设置页在 zh/ja/en 三态目视（Edge/浏览器），字段/按钮/onboarding/状态/审计无漏译、无 `{var}` 泄漏、无豆腐块。

## §7 构建约束（AstrBot 单文件产物铁律）

- **静态 import 词典**：`i18n.ts` 静态 `import` 三词典（Vite 内联进 `pages/settings/assets/index.js`）——**绝不运行时 fetch / 动态 `import()`**（撞 `verify-bundle.mjs` 的 `import(` 禁令 / 多资产）。
- **verify-bundle 绿**：产物仍恰好 1 个 .js（≤1 .css），词典内联使 index.js 变大但文件数不变。
- **no-drift**：`npm run build`（vite build + `normalize-eol.mjs` 统一 LF）后**重建并提交 `pages/settings` 产物**，保证提交物与构建逐字节一致（配 `.gitattributes pages/settings/** eol=lf`）。
- **vue-tsc typecheck** 归零；`vitest` 全绿。
- **词典文件 UTF-8 + LF**（含全角标点/emoji 箭头，同后端 locale JSON 铁律）。

## §8 执行边界（按层切任务，供 writing-plans）

1. **i18n 地基**：`lib/i18n.ts`（t/locale/setLocale/guessLocale）+ 三词典骨架（先只 zh-CN 全量 = 现有串迁移）+ `i18n.test.ts`（键集奇偶 + 键存在守卫）。
2. **数据层抽键**：schema.ts/chapters.ts 键派生 + Field/SectionForm/CommandTree/App 左轨消费经 `t()`；zh 词典补全数据层键。
3. **组件撒点（分批）**：App/SettingsPanel/HeaderCard/StatusPanel/AuditPanel/GroupCard/CommandTree/Field/ServerCard/AdminCard + 错误码表 `err.*` + `common.*`。
4. **onboarding 语言步 + 顶栏切换器**：ModeOnboarding 两步化 + confirm 带 locale + App mast 语言下拉写回。
5. **onboarding/transfer 流抽键**：ModeConfirmDialog/ModeTransfer/TransferWizard/OrphanCleanup/transfer.ts（完整句模板重构分段拼接）。
6. **状态行稳定键化**：后端 `status_rows` 加 `smoothness` 键 + 前端 fpsClass 改按键。
7. **ja/en 全量翻译**：三词典 ja/en 补齐（键集相等）。
8. **收口**：三语目检 + 全套闸（vitest/vue-tsc/build no-drift + 后端 pytest/ruff/mypy/lint-imports）。

仍走 SDD（全 opus 逐任务双评审，记账 `.superpowers/sdd/progress.md`）+ 全分支对抗终审 + finishing-a-development-branch → PR。

## §9 验收清单

1. zh/ja/en 三态：设置页所有用户可见文案（组件模板 + schema 字段/章节/选项/命令 + 错误 + onboarding + 转移向导 + 状态/审计骨架 + aria-label）为目标语言、无简中残留、无 `{var}` 泄漏、无漏译裸键；
2. `world.locale` 切换（三入口）UI 整体随切；onboarding 语言步 navigator.language 默认、选中即时切引导屏；顶栏切换器写回落库；
3. 后端下发值（smoothness_label/rules/audit）不被前端重译；option 存储值恒英文（collect 往返锁测试绿）；
4. 状态行 fpsClass 按稳定 `smoothness` 键、`world.locale≠zh` 下判色正确；
5. zh-CN 渲染逐字节不变（既有测试迁移后全绿）；键集奇偶/键存在守卫绿；PAL_TREE 跨端锚 + schema-`_conf_schema` 键一致不破；
6. 前端 `vitest` + `vue-tsc` + `verify:bundle` + build no-drift（`pages/settings` 产物提交）全绿；后端 `pytest`/`ruff`/`mypy`/`lint-imports`（状态键改动）全绿。

## §10 留后续（非目标/Phase 3）

- **Phase 3**：README.ja/en + docs 平行文档 + 语言切换链接（另立 spec）。
- 母语校对轮（Phase 1 遗留 en/ja 自然度 minor + Phase 2 前端译文一并校对）。
- AstrBot 面板域（`_conf_schema.json` 字段名/`register_web_api` 描述）单语，长期跟随 AstrBot 生态若开放面板 i18n 再议。
