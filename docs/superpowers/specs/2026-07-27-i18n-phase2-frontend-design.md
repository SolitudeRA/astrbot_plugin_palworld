# 三语 i18n Phase 2 · 设置页前端 设计（spec · 对抗复核修订版）

**日期**：2026-07-27（修订：4 棱镜对抗复核 20 发现全数落改）
**前置**：Phase 1（后端 i18n，PR #40 已合并 main）。本 spec 为 i18n「按层分三期」的 Phase 2（设置页 Vue 前端）；Phase 3（README/docs）另立 spec。

## 目标

设置页 Dashboard（Vue3 + reka-ui 2.10.1 + Vite 单文件产物，`frontend/` 源 → `pages/settings/` 产物）全部用户可见文案随语言渲染 zh-CN（默认）/ja/en，语言跟随全局 `world.locale`（与 bot 消息同一值，「全局一种语言」）。自建轻量 `t()`（镜像后端 `L()`）；组件模板/JS 串 + schema/chapters 数据层文案全覆盖；onboarding 加语言选择步、顶栏加语言切换器。

## 架构

自研 ~30 行 `t()`（`frontend/src/lib/i18n.ts`）：reactive `locale` ref（默认 `'zh-CN'`）+ 三份**扁平** key→模板串词典（静态 import 进单文件 bundle）+ fallback 链 `dict[locale]→dict['zh-CN']→key`、永不抛 + `{var}` 插值；模块单例、Vue 上下文外可调。抽键两套：组件内联串 `t()` 撒点；schema.ts/chapters.ts 数据层按稳定结构键派生键、结构不动、渲染经 `t()` 解析。zh-CN 词典值 = 现有中文串逐字节相同 → zh 渲染零回归。

## 非目标（scope 边界）

- **不译**：品牌名「帕鲁世界终端/PalWorldTerminal」；locale 选项母语名（简体中文/日本語/English，测试已锁恒定不译）；**后端已经 `L()` 本地化下发的值**——status `smoothness_label`、world `rules` 值（前端只展示绝不重译）；**option 存储值**（enum 英文值恒不动，只译 optionLabels）；`CHAPTERS[].group`（'观测'/'配置' 是 rail 过滤的数据等值键、不渲染文本，恒定中文不译）。
- **注意（对抗复核修）**：**audit `action`/`error` 不是后端本地化值**——`audit_rows`（config_view.py:342）的 `action` 是 `r.get("action")` 裸英文枚举 token，`error` 混含 `L()` 串与原始 token；故 audit action **须前端翻译**（见 §4.3），不列入 opt-out。
- **不碰后端聊天 i18n**（Phase 1 完成）；**不做** README/docs（Phase 3）；**不引第三方 i18n 库**。
- **AstrBot 面板域**（`_conf_schema.json` 齿轮页字段名、`register_web_api` 描述）保持 zh，范围外。
- **dev-only 排除**：`frontend/src/dev/**`（main-dev.ts / mockBridge.ts）不产字典键、不纳入抽键面。

---

## §1 术语与单一真相源

- **UI locale** = 设置页 Dashboard 显示语言；**message locale** = `world.locale` 字段（驱动后端 bot 输出 + 服务端渲染的 status/rules label）。
- **决策（Phase 1 已定「前端跟随插件 locale」+「全局一种」）**：UI locale **复用同一个 `world.locale`**。三处改语言入口最终写同一个 `world.locale`：①onboarding 语言步 ②world 设置节 locale 字段 ③顶栏语言切换器。
- **副作用披露（对抗复核）**：因 `world.locale` 同驱 bot 输出，改语言（含顶栏切换器）会 **同时改变所有群的 bot 回复语言 + 触发插件 reload**（handle_config_save→apply_and_restart）。这是「全局一种语言」的固有语义，spec 采纳并显式披露；顶栏切换器按 §3.3 的稳健路径落地。

## §2 t() 机制契约（`frontend/src/lib/i18n.ts`）

```ts
import zhCN from './locales/zh-CN'
import ja from './locales/ja'
import en from './locales/en'
const DICTS = { 'zh-CN': zhCN, ja, en } as const
export type Locale = keyof typeof DICTS
const SUPPORTED: Locale[] = ['zh-CN', 'ja', 'en']

export const locale = ref<Locale>('zh-CN')      // 模块级 reactive 单例；默认 zh-CN（**不在模块顶层调 guessLocale**）
export function setLocale(l: unknown): void      // 见下：no-op 语义
export function guessLocale(): Locale            // navigator.language.startsWith('ja')→ja / 'en'→en / 否则 zh-CN
export function t(key: string, vars?: Record<string, string | number>): string
```

- **`setLocale` 语义（对抗复核 C1/I 修，消歧义）**：`undefined`/`null`/空串/**非 `SUPPORTED`** 的值一律 **no-op**（保持 `locale.value` 当前值，不抛、不回落 zh-CN）；仅当参数 ∈ `SUPPORTED` 才切。这样 `applyConfig` 遇空配置 `world.locale===undefined` 不会覆写已猜初值。
- **初值链（对抗复核 C1 修，钉死测试期 zh）**：`i18n.ts` **不**在模块加载时调 `guessLocale()`——`locale` 恒以 `'zh-CN'` 起步。**仅 `main.ts`（真实浏览器入口，挂载前）调 `setLocale(guessLocale())`**。组件测试只 import 组件、不经 `main.ts` → `locale` 维持 `'zh-CN'`，§6 零回归前提成立。
- **fallback 链**：`DICTS[locale.value][key] ?? DICTS['zh-CN'][key] ?? key`，永不抛（镜像后端 `L()`）。
- **插值**：`{name}`/`{n}` 字面替换；缺参**留原样**（`{x}` 不替换，便于测试发现漏参）。
- **Vue 上下文无关**：`i18n.ts` 不 import 任何组件、不依赖 setup；`boot.ts`/`main.ts` 挂载前 fallback 渲染即可 `t()`。
- **reka-ui 关闭态触发器响应性（对抗复核 I 修）**：reka-ui/Radix `SelectValue` 触发器显示的是选中项挂载时登记的文本快照，`SelectContent` 默认仅展开时挂载 `SelectItemText`——live 切语言时下拉关闭，触发器标签会陈旧。**缓解写死**：`Field.vue` 的 `SelectRoot` 绑 `:key="locale"`（locale 变即强制重挂、重登记本地化文本）。所有 enum 字段触发器受此保护。

## §3 locale 来源与三入口切换

### §3.1 初值与配置回灌（单一真相）
- 浏览器：`main.ts` 挂载前 `setLocale(guessLocale())`（navigator.language 猜）。覆盖 boot 早期文案、onboarding 未设置态。
- **配置回灌**：`SettingsPanel.applyConfig`（:114）每次 load/save 后 `setLocale(state.sections.world.locale)`——`setLocale` 对 `undefined`（空配置）no-op、保持猜值；对合法值切换。
- `config/get`（web_api.py:18）响应 `{ok, config, page_version}`，`world.locale` 恒在（无需后端改）。

### §3.2 onboarding 语言步
- `ModeOnboarding` 由隐式单步改**两步**：**step1 语言选择** → **step2 模式**。step1 用 radiogroup，`guessLocale()` 默认，**选中即时 `setLocale`（仅切引导屏 UI，不落库）**；`confirm` 事件带 `{locale, mode}`，`onConfirmMode`（SettingsPanel:182）一并写 `world.locale + world_mode + setup_confirmed` 后 `save()` 落盘（唯一落库点）。
- **a11y（对抗复核 M 修）**：step1 **复用 `ModeOnboarding` 现有的自定义 `role=radiogroup` + roving-tabindex + `onKeydown` 方向键环绕**（不用 TransferWizard 的原生 radio），保证两步键盘交互一致；§6 保留/迁移既有方向键导航断言，防两步化回归 a11y。
- 多步骨架（step ref/next/back/进度）可参照 `TransferWizard` 的**结构**，但控件沿用 ModeOnboarding 自定义 radiogroup。

### §3.3 顶栏语言切换器（对抗复核 C2 稳健重设计）
放品牌头 mast（App.vue:48-51，与主题按钮同排），选项标签 = 母语名（恒不译）。
- **onboarding 态隐藏**：mast 切换器 `v-if="!onboarding"`（与左轨同条件），onboarding 阶段语言唯一交给 step1，避免同屏两个语言控件行为分叉。
- **持久化路径（不复用全量 save）**：切换器**不**走 `collectBody(state)` 全表单 save（那会夹带未保存草稿 + 触发 restart + credential_redirect 等失败）。改为**专用 locale-only patch**：新增轻量端点 `POST <api>/config/locale`（校验 `world.locale ∈ {zh-CN,ja,en}`、只写该字段、触发 reload 使 bot 输出同步，**不 collect 全表单**）。
- **乐观切 + 失败回滚**：切换器先乐观 `setLocale`（UI 即时切）→ 调 locale patch；**patch 失败则回滚 `setLocale` 到 applyConfig 快照值**，消除「UI=新/配置=旧」分叉。
- **禁用态**：`saving`（全表单在飞）或 patch 在飞期间禁用切换器，防竞态闪回。
- **跨组件通道（对抗复核 I 修）**：语言写回逻辑在 SettingsPanel，切换器在 App——`SettingsPanel` `defineExpose({ setLocaleAndPersist })`，App 经 template ref 调用；或把 `world.locale` 与 patch 动作提为 App 级共享。spec 采 `defineExpose` 通道。
- **披露**：经此切换会 reload 插件并改 bot 输出语言（§1 副作用）。

### §3.4 协同
三入口最终改同一 `world.locale`；`applyConfig` 回灌 `setLocale` 是稳态真相。乐观切换的瞬时不一致由「失败回滚 + 禁用态」消除。

## §4 抽键策略

### §4.1 组件内联串 `t()` 撒点（~265 串）
命名空间键：`app.*`（品牌口号/主题按钮/fatal）、`status.*`、`audit.*`、`onboarding.*`、`transfer.*`、`err.*`（§4.3）、`common.*`（查看编辑通用词，避免各卡片重复）。**显式覆盖以下易漏类别（对抗复核 I 修）**：
- **placeholder**（6 串）：ServerCard:83 / HeaderCard:82「已设置，留空则不修改」「未设置」；GroupCard:75,84 与 AdminCard:75,84「如 aiocqhttp:…」「备注，可选」——**示例技术字面（`aiocqhttp:GroupMessage:123456` 等）保留，仅译前缀「如」/「备注，可选」**。
- **title(tooltip)**（3 串）：CommandTree:147「危险命令：不随整组开关，需逐条开启」、:148「此命令已单独设置」；AuditPanel:81 `:title="r.error"`（见 §4.3 error 处理）。
- **aria-label**：章节索引/上一页/下一页/`{name} 详细信息`/`{label} 启用`（拼接型带参 `t()`）。
- **响应性硬约束（对抗复核 I 修）**：**凡在 `<script setup>`/模块作用域用 `const` 缓存的可见文案，必须改 `computed(()=>…)` / getter / 模板即时 `t()`，禁止把 `t()` 结果冻结进 const**。显式改造项：`SettingsPanel.DANGER_CMDS`（label/desc 10 串）、`SettingsPanel.ERR`（9 码）、`transfer.ts TRANSFER_ERR`（13 码）——否则 live 切语言这些串停在旧语言，§9#2 达不到。
- **插值/拼接（对抗复核 M 修，分两类）**：
  - **单句计数** → 完整句模板 + 计数参：`t('audit_total', {n})`、`ago()/fmtUptime()` 的秒/分/时/天与「{n} 天 {h} 小时」（三语量词/复数由各语言模板承载）。
  - **多可选子句**（ModeTransfer:69-75、OrphanCleanup:35-37 的 `msg +=` 组合追加，2^n 组合）→ **逐子句独立键 + 保留 concat**（`t('transfer.purged',{n})` 等，zh 下每片=原片字面）；连接标点单独键化（`punct.semicolon` 等）。**不强套单一完整句模板**（无法表达组合、易破 zh 字节等价）。
- **组件内枚举中文化就地转**（非 schema）：ServerCard enabled→启用/停用、verify_tls→是/否、CommandTree lockedLabel 恒开/仅管理员/所有人、模式徽章单/多服务器——独立 enum 键组。
- **早期文案显式落键**：boot.ts bootMessage 两串（「需要 AstrBot ≥ v4.24.1 的插件页面环境」/「初始化失败，请刷新」）、main.ts pw-fatal、App.vue「页面发生错误，请刷新重试」+「重试」。

### §4.2 数据层抽键（schema.ts / chapters.ts ~162 串）
键**派生自现有稳定结构键**，schema/chapters 保留结构 + 稳定 key 不动，渲染点经 `t()` 解析：
- 字段（对抗复核 I 修，补 SERVER/HEADER 伪 section 命名空间）：
  - OBJECT_SECTIONS 内字段：`t('field.<section>.<fieldKey>.label')` / `.hint`
  - **SERVER_FIELDS**（9，无 section）：`t('field.server.<key>.label')` / `.hint`
  - **HEADER_FIELDS**（4，无 section）：`t('field.header.<key>.label')` / `.hint`
  - **ServerCard/HeaderCard/AdminCard/GroupCard 查看态的独立短标签**（与编辑态 schema 标签不同的一套，如 ServerCard:49-63 地址/用户名/连接超时/校验 TLS/时区/已设置/未命名）归 `common.*` 或 `view.*` 命名空间显式撒点，勿与编辑态 schema 键混。
- 章节：`t('section.<key>.title')` / `.subtitle`（含 SettingsPanel:62 computed 覆写 routing 段「默认查询」等组件本地串，单独键化）
- 选项：`t('opt.<field>.<value>')`（optionLabels；**存储值不动**）
- 命令组：`t('group.<name>')`（GROUP_LABELS，5）
- 命令：`t('cmd.<path>')`（PAL_TREE 每条 label，30，path 去空格）
- 章标签：`t('chapter.<key>.label')`（CHAPTERS，8）
- **移除**（对抗复核 M 修）：`CHAPTERS[].group`（'观测'/'配置'）**不抽键**——是 App.vue:36-37 `filter(c=>c.group==='观测')` 的数据等值键、rail 不渲染文本；翻译会使过滤恒空、rail 崩。保持中文字面恒定。
- **PAL_TREE 结构不可动**：仍是可 `json.loads` 的双引号数组（后端 `test_frontend_tree_matches_backend_meta` 跨端锚定 flag 列）；`label` 保留作默认/兜底，另按 `cmd.<path>` 键查表译，绝不重构条目。
- **world.locale 字段标签语义扩张（对抗复核 M 修）**：`world.locale` 现标签「消息语言」→改「界面与消息语言」（zh 词典值随之更新，此处为**有意文案更新**非零回归项，须在测试迁移面标注涉及 schema 断言）。

### §4.3 错误码 & audit action 三语
- **错误码表**（`err.<code>`）：`SettingsPanel.ERR`（9 码）+ `transfer.ts TRANSFER_ERR`（13 码）合并到 `t('err.<code>')`，未知码 fallback→通用「操作失败」。`mapError` 拼的 `：{path}` 冒号随 locale（`punct.colon` 键）。`errors.ts` 4 条 Error 类兜底一并键化。ERR/TRANSFER_ERR 表须按 §4.1 响应性约束改 computed/getter。
- **audit action（对抗复核 I 修，移出 opt-out）**：`AuditPanel:76 {{r.action}}` 是裸英文 token → 前端 `t('audit.action.<code>')`，全枚举 `kick/ban/unban/announce/save/shutdown/stop/mode_transfer/orphan_purge`，未知码兜底原样。
- **audit error（tooltip）**：`r.error` 混含后端 `L()` 串与原始 token（如 `purge_failed:…`）——**前端只展示不译**（后端已本地化的走本地化、原始 token 作调试标识）；spec 明确此界，不抽键。

### §4.4 opt-out（恒定不译）
品牌；locale 母语名；后端 `L()` 本地化下发的 **status smoothness_label / world rules 值**（前端只展示）；option 存储值；`CHAPTERS[].group`；audit error tooltip（见 §4.3）。**audit action 不在此列**（须译）。

## §5 状态行稳定键化（跨期 bug 根治）

**问题**：Phase 1 令 `status_rows`（config_view.py:284）`smoothness_label = L(f"smoothness_{dto.smoothness_label}")` 按 `world.locale` 本地化；前端 `StatusPanel.fpsClass`（:57-59）硬比中文 `label==='流畅'/'一般'` → `world.locale≠zh` 时失准。

**修**（后端 1 行 + 前端小改）：
- 后端 `config_view.status_rows`：`dto.smoothness_label` **本就是稳定键**（`smooth/moderate/laggy/very_laggy`，query_status 产），row dict **并行加** `"smoothness": dto.smoothness_label`（与 `smoothness_label` 并存）。
- 前端 `StatusPanel`：类型加 `smoothness?: string`；`fpsClass(row.smoothness)` 按稳定键判色（`smooth→good / moderate→mid / laggy|very_laggy→bad`），不再比中文；`smoothness_label` 仍用于**显示**（后端本地化串，前端不译）。
- **live 切换窗口（对抗复核 M 修）**：顶栏 live 切语言后，后端服务端渲染值（smoothness_label/rules/audit）须待 reload + 面板重新拉取才更新；期间已加载值仍旧语言（有「正在应用新配置…」态兜底）。§6 目检须在 reload 完成后进行。

## §6 零回归 & 测试策略

- **测试期 locale 钉死 zh（对抗复核 C1 修，关键）**：jsdom 默认 `navigator.language='en-US'`。因 `i18n.ts` 不在模块顶层 `guessLocale()`（§2）、组件测试不经 `main.ts`，`locale` 天然维持 `'zh-CN'`。另在 `vitest.setup.ts` 显式 `setLocale('zh-CN')` + 每测试 `beforeEach` 复位，双保险。**修正措辞**：§9#5「zh-CN 渲染字节不变」以此为前提。
- **键集/占位符奇偶校验**（移植后端 `locale_parity_test`→前端 `i18n.test.ts`）：三词典键集严格相等 + 每键占位符集相等。
- **字面 t() 键存在守卫**：扫描代码 `t('literal')` 引用键存在于词典——**仅覆盖组件内联串**。
- **数据层键覆盖测试（对抗复核 I 修，补最大盲区）**：遍历 `OBJECT_SECTIONS/SERVER_FIELDS/HEADER_FIELDS/PAL_TREE/CHAPTERS/GROUP_LABELS`，**按与渲染点完全相同的派生规则**算出每个应存在的键（`field.*`/`cmd.*`/`opt.*`/`section.*`/`chapter.*`/`group.*`），断言存在于每份词典。字面扫描 + 此数据层覆盖 = 全键覆盖，堵住「派生键三词典同缺、奇偶仍绿、UI 渲染裸键」盲区。
- **零回归（zh 字节）**：zh-CN 词典每值 = 抽键前该处中文串**逐字节相同**；多子句 concat 每片模板 = 原片字面（§4.1）→ 组件 zh 渲染不变；既有快照/文本断言（zh 默认）保持绿。
- **测试迁移（档二显式迁移面）**：按中文串断言的组件测试同 commit 迁移到经 `t()`/稳定键断言。实测 **24 个 `*.test.ts` 含 CJK 断言**——ModeOnboarding/ModeTransfer/TransferWizard/CommandTree/StatusPanel/schema.test 等逐一迁移；**`schema.test.ts:57` locale optionLabels 恒定不译锁不可破**；**ModeOnboarding 方向键导航断言保留**（防两步化回归）。
- **状态稳定键回归（对抗复核 M 修，枚举两文件）**：后端加 `smoothness` 键须同步 **`tests/unit/config_view_status_test.py:26`** 与 **`tests/unit/web_api_read_test.py:73`**（两处全字典 `==` 断言各补 `"smoothness": "smooth"`）；`config_view_status_i18n_test.py` 用子集断言、安全。前端 StatusPanel 测试改按 `smoothness` 断言 fpsClass。
- **reka-ui 关闭态触发器随切**：§6 加断言/目检——切 locale 后 enum 字段**关闭态**触发器标签随之变（验证 `:key=locale` 缓解生效）。
- **跨端 parity**：PAL_TREE 数组仍 `json.loads`-able、`test_frontend_tree_matches_backend_meta` 绿；schema.ts 键与 `_conf_schema.json` 一致（**严禁删 schema 键**）。
- **三语目检**：构建后 zh/ja/en 三态目视（reload 完成后），字段/按钮/onboarding/状态/审计/placeholder/tooltip/aria 无漏译、无 `{var}` 泄漏、无豆腐块。

## §7 构建约束（AstrBot 单文件产物铁律）

- **静态 import 词典**：`i18n.ts` 静态 import 三词典（Vite 内联进 `pages/settings/assets/index.js`）——**绝不运行时 fetch / 动态 `import()`**（撞 `verify-bundle.mjs` 的 `import(` 禁令 / 多资产）。
- **verify-bundle 绿**：产物仍恰好 1 .js（≤1 .css）；词典内联使 index.js 变大但文件数不变。
- **no-drift**：`npm run build`（vite build + `normalize-eol.mjs` 统一 LF）后重建并提交 `pages/settings` 产物（配 `.gitattributes pages/settings/** eol=lf`）；CI `git diff --exit-code -- pages/settings`（ci.yml:75-82）须绿。词典 UTF-8 + LF（含全角标点/emoji）。
- **vue-tsc typecheck** 归零；`vitest` 全绿。`t(key: string)`（不收窄为 union；漏键交给 §6 数据层覆盖测试 + 字面守卫捕获——取舍：换取 schema/chapters 结构不必内联键类型）。
- **src/dev/** 排除**：dev-only，不产字典键。

## §8 执行边界（按层切任务，供 writing-plans）

1. **i18n 地基**：`lib/i18n.ts`（t/locale/setLocale[no-op 语义]/guessLocale，模块顶层不猜）+ 三词典骨架（zh-CN 全量 = 现串迁移）+ `i18n.test.ts`（键集/占位符奇偶 + 字面守卫）+ `vitest.setup.ts` 钉 zh-CN。main.ts 挂载前 `setLocale(guessLocale())`。
2. **数据层抽键 + 覆盖测试**：schema.ts/chapters.ts 键派生（含 field.server.*/field.header.*，移除 group 抽键）+ Field/SectionForm/CommandTree/App 消费经 `t()`（Field SelectRoot 绑 `:key=locale`）+ **数据层键覆盖测试**。world.locale 标签改「界面与消息语言」。
3. **组件撒点（分批）**：App/SettingsPanel/HeaderCard/StatusPanel/AuditPanel/GroupCard/CommandTree/ServerCard/AdminCard——含 placeholder/title/aria、查看态短标签、boot/main/App fatal；**DANGER_CMDS/ERR/TRANSFER_ERR 改 computed/getter**（响应性）；错误码 `err.*` + audit action `audit.action.*` + `common.*`。
4. **onboarding 两步化 + 顶栏切换器**：ModeOnboarding step1 语言（复用自定义 radiogroup a11y）+ confirm 带 locale；App mast 切换器（onboarding 态隐藏、乐观切 + 失败回滚 + saving 禁用）；**后端新增 locale-only patch 端点** + SettingsPanel `defineExpose` 通道。
5. **onboarding/transfer 流抽键**：ModeConfirmDialog/**ModeTransfer/OrphanCleanup**（多子句逐键 concat）/TransferWizard；transfer.ts TRANSFER_ERR 键化。
6. **状态行稳定键化**：后端 `status_rows` 加 `smoothness` 键（+ 改 config_view_status_test:26、web_api_read_test:73）+ 前端 fpsClass 改按键。
7. **ja/en 全量翻译**：三词典 ja/en 补齐（键集相等）。
8. **收口**：三语目检（reload 后）+ 全套闸（vitest/vue-tsc/verify:bundle/build no-drift + 后端 pytest/ruff/mypy/lint-imports）。

仍走 SDD（全 opus 逐任务双评审，记账 `.superpowers/sdd/progress.md`）+ 全分支对抗终审 + finishing-a-development-branch → PR。

## §9 验收清单

1. zh/ja/en 三态：设置页所有用户可见文案（组件模板 + schema 字段/章节/选项/命令 + 错误码 + **audit action** + onboarding + 转移向导 + 状态/审计骨架 + **placeholder/title/aria**）为目标语言、无简中残留、无 `{var}` 泄漏、无漏译裸键；
2. `world.locale` 切换（三入口）UI 整体随切（含 setup-scope const 持有串、reka-ui 关闭态触发器标签）；onboarding 语言步 navigator.language 默认、选中即时切引导屏、复用自定义 radiogroup 键盘导航；顶栏切换器 onboarding 态隐藏、乐观切 + 失败回滚 + saving 禁用、走 locale-only patch 不夹带表单；
3. 后端 `L()` 下发值（smoothness_label/rules）不被前端重译；option 存储值恒英文（collect 往返锁测试绿）；audit action 已译、audit error tooltip 按 §4.3 界处理；
4. 状态行 fpsClass 按稳定 `smoothness` 键、`world.locale≠zh` 下判色正确；
5. **测试期 locale 钉 zh-CN**；zh-CN 渲染逐字节不变（24 含 CJK 测试迁移后全绿）；键集/占位符奇偶 + 字面守卫 + **数据层键覆盖** 全绿；PAL_TREE 跨端锚 + schema-`_conf_schema` 键一致不破；
6. 前端 `vitest` + `vue-tsc` + `verify:bundle` + build no-drift（`pages/settings` 产物提交）全绿；后端 `pytest`/`ruff`/`mypy`/`lint-imports`（状态键 + locale patch 端点）全绿。

## §10 留后续（非目标/Phase 3）

- **Phase 3**：README.ja/en + docs 平行文档 + 语言切换链接。
- 母语校对轮（Phase 1 遗留 en/ja 自然度 minor + Phase 2 前端译文一并校对）。
- AstrBot 面板域（`_conf_schema.json` 字段名/`register_web_api` 描述）单语。
- 可选优化：locale patch 若能只 `load_locale` 热切而非全插件 restart（减轻改语言的重启代价），plan 期评估。
