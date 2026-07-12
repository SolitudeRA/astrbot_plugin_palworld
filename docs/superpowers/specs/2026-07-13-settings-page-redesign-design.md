# 设置页重设计（Settings Page Redesign）设计规格

**日期：** 2026-07-13
**分支：** `feat/settings-page-redesign`
**类型：** 前端表现层重设计（视觉 + 结构），零后端契约改动
**视觉基准：** `docs/design/settings-redesign-demo.html`（已与用户经 ~18 轮交互定稿）

---

## 0. demo 的定位与真源优先级（先读，防照抄踩坑）

`docs/design/settings-redesign-demo.html` 是**视觉与交互的示意**（配色、排布、控件形态、两态卡片手感），**不是数据形状、字段判据、DOM 类名的真源**。demo 是独立原型，用 fake 数据和手写 DOM，多处与生产实际不同。**真源优先级：后端契约 / 现网 reka-ui 产物 / 本规格 §7 不变量 > demo。** 凡冲突，一律以前者为准。已知 demo 与生产的三处关键背离（详见对应节）：

- **D1 · secret 判据**：demo 读 `d.password`/`d.value` 明文真值判「已设置」；生产经 `redact_config` 后这俩字段**恒为空串**，须改读 `password_set`/`value_set` 布尔（§5）。
- **D2 · 控件 DOM/类名**：demo 的 `.switch`/`.stepper`/`.dd` 是手写 DOM；生产是 reka-ui 产物，类名是 `.pw-switch`/`.pw-number`/`.pw-select-*`、状态属性是 `data-state`（非 demo 的 `aria-checked`/`aria-selected`）。tokens.css 重写以 **pw-\* 类名 + reka-ui `data-state`** 为准，demo 的控件类名/CSS 仅作外观参考、**不落地**（§2.4）。
- **D3 · 下拉定位**：demo `.dd-panel` 是行内 `absolute`；reka-ui Select 默认 `item-aligned`，外层 wrapper 的 `position:fixed` 由 JS 内联写死，**CSS 改不动**。下拉定位沿用 reka-ui 现状，只重塑触发器/面板/选项的配色（§2.4）。

---

## 1. 目标与范围

把 AstrBot 插件设置/状态页从「设置/状态两 tab + 平铺 8 节」重构为「左索引分章观测台」布局，落地定稿视觉系统（草甸绿亮色 / 黑灰暗色、全无衬线、样式化控件、两态条目卡片）。**只改前端表现层**——后端契约、`collect.ts`/`schema.ts` 数据形状、`bridge.ts` 三端点、错误分层、secret 安全红线、单文件产物硬约束全部不变（§7）。

### 范围内
- `App.vue`：报头（品牌 + 主题切换）+ 左索引分章导航 + 章节路由 + 错误边界（保留 `onErrorCaptured`）。
- `SettingsPanel.vue`：按 `chapter` prop 只渲染当前章内容；条目卡片保存联动；**全部现有逻辑原样保留**。
- `ServerCard.vue` / `HeaderCard.vue`：查看↔编辑两态；查看态只显已填字段。
- `SectionForm.vue`：换 `.entry/.row` 排布，渲染节副标题 + 字段提示；保留 `section.title` 与 Field 顺序。
- `StatusPanel.vue`：换观测卡外观；**逻辑与文案锚点原样保留**（§3.3 边界）。
- `Field.vue`：**模板不动**（保留 reka-ui 组件与角色契约）；仅靠 CSS 重塑外观。
- `styles/tokens.css`：整体重写为新设计系统（以 pw-\* 类 + reka-ui data-state 为准）。
- `lib/schema.ts`：**只加**可选展示属性（`hint?`/`subtitle?`）+ 打磨 label 文案；key/type/default/options/顺序/secret 一律不动。
- `lib/chapters.ts`（新增）：章节结构常量。
- 测试：改写 4 个受结构影响的组件测试（App/SettingsPanel/ServerCard/HeaderCard）；其余保持通过。

### 范围外（明确不做）
- 不改任何 `.py` 后端、`_conf_schema.json`、web bridge 协议。
- 不引入新 npm 依赖（保 vue 3.5.39 + reka-ui 2.10.1）。
- 不加 `import()` / 第二 CSS 入口（破单文件产物）。
- 不换控件库、不改 Field.vue 逻辑去追求 demo 下拉定位（会破 I5/Field.test）。
- 不做「保存后自动重载配置以回填新行 `__row_id`」（既有行为，见 §6.4）。

---

## 2. 视觉系统（design tokens）

全部落在 `styles/tokens.css`。**暗色继续挂 `[data-theme="dark"]`，选择器名不可改**（宿主注入 + 手动切换都写这个属性）。

### 2.1 亮色 `:root`
```
--paper:#E9EDE2; --card:#F4F7EE; --sink:#DCE3D3; --raise:#FAFCF5;
--ink:#182A20; --ink-2:#516359; --ink-3:#84918A;
--rule:#CFD9C4; --rule-2:#BDC9B0;
--amber:#D2891C; --amber-h:#B4720E; --amber-soft:#F0DBA8; --on-amber:#231704;
--flux:#2C9C4E; --flux-soft:#C6E6C8;
--danger:#CE4630; --warn:#B67F1C; --focus:#2E82BE;
--r:8px;
```
### 2.2 暗色 `[data-theme="dark"]`（黑灰中性）
```
--paper:#17181A; --card:#202225; --sink:#111214; --raise:#26282B;
--ink:#EAEAE5; --ink-2:#A1A3A1; --ink-3:#6F7173;
--rule:#2C2E31; --rule-2:#3B3E42;
--amber:#EAAE55; --amber-h:#F3BE6E; --amber-soft:#2C2410; --on-amber:#1E1608;
--flux:#57C070; --flux-soft:#16301F;
--danger:#E7745C; --warn:#D9A94E; --focus:#5BABE6;
```
### 2.3 排印与语义色
- 全无衬线，只 `--sans:system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif`。对齐数字列 `font-variant-numeric:tabular-nums`。（`--serif`/`--mono` 不再需要；若保留则别名到 sans。）**纯系统字体，无 `@font-face`/`url()`/`@import`/CDN**（受限 iframe CSP 全禁外链）。
- `--flux`(绿)=启用/在线/就绪/已保存 good；`--focus`(天蓝)=导航当前项/焦点/输入聚焦；`--amber`(金)=保存动作（commit/save-card/编辑态高亮）；`--danger`=移除/错误；`--warn`=数据缺失等次级警示。

### 2.4 控件重塑：demo 类名 → 现网 reka-ui 类名/状态（D2/D3）
`Field.vue` 模板不动，控件用的是 reka-ui 产物。tokens.css 重写**必须按下表以 pw-\* 类 + `data-state` 为选择器**，demo 的 `.switch/.stepper/.dd` 选择器**命中不到真实节点，严禁照抄**：

| demo（示意，不落地） | 现网真实选择器（据此写 CSS） | 状态属性 |
|----|----|----|
| `.switch` / `.switch[aria-checked="true"]` | `.pw-switch` / `.pw-switch[data-state="checked"]`（thumb=`.pw-switch-thumb`） | `data-state="checked"`（非 aria-checked） |
| `.stepper` / `.num` / 步进按钮 | `.pw-number` / `.pw-number-input` / `.pw-number-btn` | — |
| `.dd-trig` / `.dd-panel` / `.dd-opt` | `.pw-select-trigger` / `.pw-select-content` / `.pw-select-item` | 高亮 `[data-highlighted]`、选中 `[data-state="checked"]`（非 aria-selected） |

- **下拉定位（D3）**：reka-ui Select 默认 `item-aligned`，展开面板由 reka-ui 以 `position:fixed` + JS 内联坐标定位，**CSS 无法改成 demo 的贴行 `absolute`**。**只重塑触发器/面板背景边框圆角/选项 hover/选中配色，不追求 demo `.dd-panel` 的贴行绝对定位**。选中态 ✓ 指示可用 `.pw-select-item[data-state="checked"]::after{content:"✓"}` 纯 CSS 实现（不改 Field.vue）。交互（展开/选中/点外关闭/键盘）由 reka-ui 内建，CSS 只管外观。

### 2.5 保留的旧类名（安全 / 测试锚点，不可丢）
- **`.pw-secret`（安全红线）**：secret 输入的 `-webkit-text-security:disc` 遮罩**必须继续挂在 `.pw-secret` 类上**（不得改用 demo:215 的内联 `style`）；也是 ServerCard/HeaderCard.test 的 `input.pw-secret` 锚点。
- **`.pw-save`**：底部提交按钮**必须同时带 `commit` 与 `pw-save` 两个类**（demo 的 `.commit` 缺 pw-save）；SettingsPanel.test 用 `button.pw-save` 触发保存（见 I10）。
- **`.pw-fatal`**：boot / 致命错误兜底页（main.ts 与 App 错误边界共用）。

---

## 3. 页面结构（章节化布局）

```
.stage（全幅背景 + 圆点纹）
  .console（max-width:880px 居中）
    header：.mast[.brand「帕鲁纪事 / PalChronicle」 · .ghost 主题切换] / .dateline / .subline「世界纪事 · 只读观测台」
    .layout
      nav.rail（左索引，sticky）
        railcap「观测」→ 观测台（● live dot）
        railcap「配置」→ 接入 · 采集 · 世界与据点 · 隐私与留存 · 功能分组
      .pane：观测台→StatusPanel；配置各章→SettingsPanel[:chapter]
```

### 3.1 章节 → 内容映射（`lib/chapters.ts`）
| id | 章标题 | 组 | kind | blocks（OBJECT_SECTIONS 键） | 额外 |
|----|--------|----|----|------|------|
| `status` | 观测台 | 观测 | status | — | StatusPanel |
| `access` | 接入 | 配置 | settings | `['routing']` | 数据源卡 + 请求头卡 |
| `cadence` | 采集 | 配置 | settings | `['polling']` | — |
| `world` | 世界与据点 | 配置 | settings | `['world','bases']` | — |
| `privacy` | 隐私与留存 | 配置 | settings | `['privacy','history']` | — |
| `feature` | 功能分组 | 配置 | settings | `['features','players']` | — |

- **默认章 = `access`**（进页面即到「接入」配服务器；亦是 §3.2 挂载策略与 App 错误边界成立的前提）。
- 各 `blocks` 并集必须恰等于 `OBJECT_SECTIONS` 全 8 键（不重不漏）——§8 一致性测试守护。

### 3.2 挂载策略（关键，含错误边界前提）
- `SettingsPanel`：**`v-show`（`chapter !== 'status'` 时可见），始终挂载**——保证跨章切换 `state` 与未提交编辑不丢、只 load 一次。
- `StatusPanel`：**`v-if`（`chapter === 'status'` 时挂载）**——离开即卸载，其 `onUnmounted` 清 timer 语义保持有意义；每次进观测台拉新鲜状态。
- **错误边界前提**：App.test 的错误边界用例（stub SettingsPanel 在 setup 抛错 → App `onErrorCaptured` 兜底显 'boom-child'）依赖 **SettingsPanel 在默认渲染路径上被实际挂载**。`v-show` 常挂满足（v-show 仍 mount 元素、只切 display，stub 的 setup 仍同步抛出被捕获）。**红线：默认 chapter 必须 = `access`，SettingsPanel 必须 v-show 常挂；不得改用「会因默认章变化而不挂载」的 v-if**（否则该用例静默假绿）。

### 3.3 StatusPanel 表现层重塑边界（D3 类冲突：只换皮，不造数据）
- **只换外层 class（`.pw-status`→观测卡样式）与排布，渲染严格基于现有 `StatusResp` 字段**：`name / ready / online / smoothness_label / degraded / restarting`（对齐后端 `status_rows` 白名单）。
- **不得引入 demo `statusView` 里的 fps 数值 / 「第 N 天」/ 「最后更新 X 前」/ 「未授权本群 · /pal use 绑定」等文案**——这些是 demo 演示数据，`StatusResp` 无对应字段；引入即需硬编码假数据或加后端字段（破 §7 零后端改动）。
- **文本锚点必须保留**（StatusPanel.test 不改要保持绿）：`在线 {online}`、`{smoothness_label}`、`正在重载`、`读取状态失败`、`刷新` 按钮。chip 语义可用现有字段派生：`ready&&!degraded`→就绪(good)、`degraded`→数据缺失(warn)、`!ready`→未就绪(idle)。

---

## 4. 主题切换（生产决策：保留手动按钮）

`App.vue` 内实现，**不新建 JS 主题框架、不改选择器名**——只把 `data-theme` 写到 `document.documentElement`。

```
const THEME_KEY = 'palchronicle-theme'
function readStored(): 'light'|'dark'|null { try { const v = localStorage.getItem(THEME_KEY); return v==='light'||v==='dark' ? v : null } catch { return null } }
function writeStored(v: 'light'|'dark') { try { localStorage.setItem(THEME_KEY, v) } catch { /* 受限 iframe 不可用，忽略 */ } }
function initialTheme(): 'light'|'dark' {
  const stored = readStored(); if (stored) return stored
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
}
const theme = ref<'light'|'dark'>(initialTheme())
watchEffect(() => { document.documentElement.setAttribute('data-theme', theme.value) })
function toggleTheme() { theme.value = theme.value === 'dark' ? 'light' : 'dark'; writeStored(theme.value) }
```
- **初始优先级**：localStorage 记忆 → 宿主注入的 `data-theme` → `light`。按钮文案：`theme==='dark' ? '☀ 昼阅' : '☾ 夜观'`。
- **红线**：所有 `localStorage` 访问必须 `try/catch`——**含 `initialTheme` 的读路径**（boot/setup 阶段；App 的 `onErrorCaptured` 只捕**子组件**错、不捕自身 setup，未兜底会整页 boot 崩）。兜底后：切换在**会话内**照常生效（ref + data-theme 写入），仅「跨会话记忆」降级为 no-op。
- **已知降级（承认，不修）**：若宿主在运行时重注入 `data-theme`（宿主主题联动），会覆盖本会话内的手动选择，用户需再点一次切换；本次**不监听宿主 attr 变化去回夺控制权**（避免与宿主打架），视为可接受降级。
- `data-theme` 只写自身 `documentElement`（沙箱 iframe 对自身文档 DOM 写不受 `allow-same-origin` 门控），不触碰父文档/cookie/parent。

---

## 5. 条目卡片：查看↔编辑两态（ServerCard / HeaderCard）

两组件同构（**键集不同，判据键随字段而异，勿从 ServerCard 直接复制到 HeaderCard**）。**props/emits 在旧签名上只增不改**：

```
props:  { modelValue: Record<string,unknown>; indexLabel: string }   // indexLabel 例：'源 01' / '头 01'
emits:  {
  'update:modelValue': [v: Record<string,unknown>]   // 保留（合并后整行，__row_id 透传）
  delete: []                                          // 保留
  save:   []                                          // 新增（请求落库）
}
```
内部态：`mode: 'view' | 'edit'`。初始 `mode = modelValue.__row_id ? 'view' : 'edit'`（已加载行有真实 `__row_id`→查看；新增行 `__row_id===''`→编辑）。

### 5.1 查看态（view）—— secret 判据必须读 `*_set` 布尔（D1，勿抄 demo 明文位）
- `.card`（非 editing）。`.card-head`：`.idx`(indexLabel) + `.nm`(`modelValue.name || '（未命名）'`) +（server）启用/停用 `.hchip` + `.grow` + `[移除 .del]` `[修改 .edit]`。
- `.cbody`：**只显已填字段的摘要行**（`.crow` label|value）。**secret 判据（覆盖 demo）**：
  - **server**：地址(base_url) · 用户名(username) · **密码行 ⇔ `modelValue.password_set===true` 时显「已设置」**（`redact` 后 `modelValue.password` 恒为空串，**绝不读 `password`/`d.password` 判定**）· 密码变量(仅 password_env 非空) · 超时(timeout 秒) · 校验 TLS(是/否) · 时区(仅 timezone 非空)。
  - **header**：**值行 ⇔ `value_set ? 「已设置」 : (value_env ? 「用环境变量」 : 「未设置」)`**（读 `value_set`，**不读 `value`/`d.value`**）· 值变量(仅 value_env 非空) · 作用域(servers 有值→「限定 …」/空→「所有服务器」)。
- **secret 绝不显值**：查看态只显 `*_set` 布尔文案，永不回显密文。

### 5.2 编辑态（edit）
- `.card.editing`（琥珀高亮）。`.card-head`：`.idx` + `.editing-tag`「编辑」+ `.grow` + `[取消 .cancel-card]` `[保存 .save-card]`。
  - **`.editing-tag` 只承载固定文案「编辑」，绝不绑 `modelValue.name`**（demo:239 复用了 `.nm` 类，此处解耦：编辑态不把服务器名渲染到卡头）。
- `.cbody`：全字段表单，逐字段 `.crow`（label + hint 的 `.ck` | 控件 `.cv`）：
  - 非 secret → `<Field :spec :model-value @update:model-value>`（reka-ui 控件，绑 draft）。
  - **secret → 保留现有非受控 `<input class="pw-input pw-secret" type="text">`**（`autocomplete/autocapitalize/autocorrect="off" spellcheck="false"`）：**遮罩走 `.pw-secret` 类**（非内联 style）；type 必须 `text`（非 password，绕受限 iframe 粘贴门控）；**不 bind 值、只 `@input` 写 draft**（不回显）。
  - **占位据各卡自己的 `*_set` 键**：**ServerCard 用 `modelValue.password_set`，HeaderCard 用 `modelValue.value_set`**（两卡同构≠同键；`password_set ? '已设置（留空保持不变）' : '未设置'`）。

### 5.3 编辑用 draft 副本与保存流
进编辑态时快照 `draft = { ...modelValue }`（secret 字段 draft 初值置 `''`，输入框非受控空白，明文永不进 DOM）。编辑期改动只写 `draft`，不逐键 emit 到父。
- **取消**：丢弃 draft，回查看态（不 emit；父 state 未被触碰）。
- **保存（即落库）**：① `emit('update:modelValue', { ...modelValue, ...draft })`（父 `state.servers[i]=v` 同步生效）；② `mode='view'` + 触发「已保存 ✓」flash（`.savedflash` hchip 插在 `.del` 之前，右锚按钮簇不位移）；③ `emit('save')`（父调 `save()`，同全局保存的 config/save 全量提交）。emit 同步，父先应用 update 再跑 save，`collectBody(state)` 读到合并后值。
- **乐观反馈与失败保障**：卡片先 view+flash 是乐观 UI；**落库失败（父捕获 BusinessError/Unauthorized/RequestFailed）时，flash 与错误 toast 不得同屏共存——失败即撤 flash，错误以父 toast 为唯一真相**。（secret 提交失败属敏感变更的「保存状态误判」面，须可辨。）

### 5.4 保留的 emit / secret 契约
`update:modelValue` 发合并后整行且 `__row_id` 透传；`delete` 由「移除」触发；secret 四条全保（非受控、不回显、type=text、`pw-secret` 类、占位据各自 `*_set`）。

---

## 6. SettingsPanel：分章渲染 + 保存联动

### 6.1 保留的逻辑（原样不动）
`state`（reactive）、`phase`（loading/error/ready）、`saving` 门、`notice` toast（3s 自清）、`load()`（apiGet config/get → 逐节浅拷）、`save()`（apiPost config/save + warnings 计跳过 + 错误分流）、`ERR`+`mapError`+`emptyRow`——全不动。

### 6.2 新增 + 分章
- `defineProps<{ chapter: string }>()`；由 `CHAPTERS` 查当前章 `blocks`/`label`；`currentSections = OBJECT_SECTIONS.filter(s => blocks.includes(s.key))`。
- `ready` 分支渲染：`.chapter-head > h2`（章标题）；`chapter==='access'` 时额外渲染数据源分组（`.group-head` + ServerCard v-for + `.add`「＋ 添加数据源」）与请求头分组（`.group-head` + `.grouphint` + HeaderCard v-for + `.add`「＋ 添加请求头」）；`SectionForm v-for currentSections`（双向绑 `state.sections[sec.key]`）；`.savebar`（`[保存本页设置 .commit.pw-save]` + `.receipt` + `.note`）。
- **卡片保存联动**：`@save` on 卡片 → 调 `save()`（与底部 commit 同一函数）；`@update:model-value`→`state.servers[i]=v`、`@delete`→`splice`（现映射不变）。
- **collectBody 始终全量**：`save()` 走 `collectBody(state)`，它**始终遍历全 8 节输出 body**（`collect.ts` 不改），**与当前渲染哪一章无关**。分章只影响渲染，不影响 body 形状——**严禁为「只提交当前章」去动 collect.ts**（破 I1/I9）。故即便 access 章只渲染 routing 节，`body.polling`/`body.features` 仍完整（state 由 load 全量填充）。

### 6.3 错误态与提交锚点
`credential_redirect` 等业务错误就地 toast、表单不塌整页（`phase` 保持 `ready`）；`config/get` 的 `Unauthorized`→整块错误态。**`.commit` 按钮必须同时带 `pw-save` 类**（保存触发锚点，见 I10）。

### 6.4 已知限制（记录，不修）
保存不回填新行 `__row_id`：现 `save()` 不重载，新增行 `__row_id` 恒 `''`，对同一新行连续保存两次后端按 `null` 视作新建 → 可能重复。此为**既有行为**，与表现层重设计正交，「即落库」不改变其性质。留待后续。

---

## 7. 不变量（绝不能破）

| # | 不变量 | 来源 |
|---|--------|------|
| I1 | `collect.ts` 完全不改：`collectBody` 顶层键集、逐字段形状、`SENTINEL`、`coerce` 强类型、**绝不含 `group_bindings`** | `lib/collect.ts` |
| I2 | `schema.ts` `OBJECT_SECTIONS` 键序 `['routing','polling','world','bases','privacy','history','features','players']`、各 `fields[].key/type/default/options`、`SERVER/HEADER_FIELDS` 字段集与 `_conf_schema.json` 对齐 | schema.ts + schema.test |
| I3 | `bridge.ts` 三端点 `config/get`/`config/save`/`status/overview`、`unwrap` 分流、签名不改 | bridge.ts |
| I4 | 错误四类 + `ERR` 码映射链路不改；`credential_redirect` 就地提示 | errors.ts + SettingsPanel |
| I5 | reka-ui 控件语义不变：bool→`[role=switch]`；enum→恰 1 `[role=combobox]`(BUTTON、`aria-label===key`)不回退文本框；int/float blur 提交 number；string emit string。**只改 CSS，不换组件、不改 Field.vue 逻辑** | Field.vue + Field.test |
| I6 | secret 输入：`type=text` + `pw-secret`(`-webkit-text-security:disc`，走类非内联) + 非受控不回显 + 占位据各自 `*_set` | ServerCard/HeaderCard |
| I7 | 暗色挂 `[data-theme="dark"]`；主题写自身 `document.documentElement`；`localStorage` 全程 try/catch（含 initialTheme 读路径） | tokens.css + App |
| I8 | 单文件产物：cssCodeSplit:false、inlineDynamicImports、无 `import()`、无第二 CSS 入口、不加依赖 | vite.config + verify-bundle |
| I9 | `collectBody` 输出 `servers/custom_headers/<8 sections>`，`__row_id` 透传，新行空 secret 不注哨兵 | collect.test |
| I10 | 底部提交按钮 class **必须同时含 `commit` 与 `pw-save`**（SettingsPanel.test 用 `button.pw-save` 触发保存；demo 的 `.commit` 缺 pw-save，实现须补） | SettingsPanel + tokens.css |

---

## 8. schema.ts 增补（只增展示属性，不动契约）

给 `FieldSpec` 加 `hint?: string`，给 `ObjectSection` 加 `subtitle?: string`，填 demo 定稿文案并把 SERVER/HEADER label 调成 demo 版。**护栏：仅新增这两个可选属性 + 替换 label/hint 字符串；严禁触及任何 `key`/`type`/`default`/`options`/`secret`/字段顺序**（`schema.test` 比 key 集、`collect` 读 key+type、`Field` 读 type/options——任一改动连锁破测）。移植时逐字段对齐现有 key，**hint 归 hint、role 归 subtitle，不混入 label；`world.locale.options=['zh-CN']` 等不可动**。

- **SERVER_FIELDS**（key 不变）：name「名称」/「唯一标识，勿含空格 / 冒号 / @」· enabled「启用」· base_url「服务器地址」/「官方只读 REST 端点，含端口（默认 8212）」· username「用户名」· password「密码」/「留空则保持不变；更推荐用下方环境变量」· password_env「密码环境变量名」/「与密码二选一，更安全」· timeout「超时（秒）」· verify_tls「校验 TLS 证书」/「http 地址不校验」· timezone「时区」/「如 Asia/Tokyo；留空用全局时区」。
- **HEADER_FIELDS**：name「名称」/「如 CF-Access-Client-Id」· value「值」/「留空则保持不变；敏感值更推荐用环境变量」· value_env「值环境变量名」/「与值二选一，更安全」· servers「限定服务器」/「多个用逗号分隔；留空 = 发给所有服务器」。
- **8 节 subtitle + 字段 hint**：照 demo `OBJ` 的 `role` 与各 field `hint` 逐字移植（routing「群 ↔ 服务器 的寻址与授权」…等 8 节，详见 demo:261-292）。

---

## 9. 测试影响

### 保持通过（不改，验证仍绿）
`lib/collect.test`、`lib/schema.test`、`lib/bridge.test`、`lib/boot.test`（契约/传输/引导，与视觉正交）；`Field.test`（Field.vue 模板不动）；`SectionForm.test`（保留 `section.title` 文本 + role=switch 顺序，只换外层 class）；`StatusPanel.test`（§3.3 保住文本锚点：`在线 {online}`、`{smoothness_label}`、`正在重载`、`读取状态失败`、`刷新`）。

### 须改写
- **`App.test`**：删两 tab 断言。新断言：默认渲染报头品牌「帕鲁纪事」+ 左索引含「观测台」「接入」；点「观测台」rail 按钮 → 文本含「刷新」（进 StatusPanel）。**保留**错误边界用例（stub SettingsPanel 抛错→显 'boom-child'）——断言前提：默认 `chapter==='access'`、SettingsPanel v-show 常挂（§3.2 红线）。
- **`SettingsPanel.test`**：「渲染 10 节」跨节文本断言改为分章——`mount(props:{chapter:'feature'})` 断言含「功能分组开关」「玩家个体」；`mount(props:{chapter:'access'})` 断言含「路由与访问控制」「保存本页设置」。**保留**：`config/get` unauthorized→「未登录」；保存 `apiPost` body 不含 `group_bindings` 且 `polling.metrics_seconds` 是 number、`features.report` 是 boolean（触发用 `button.pw-save`——I10 锚点，故用 `chapter:'access'` 或任一章 mount 均可，body 恒全量）；`credential_redirect` 就地提示且表单仍在。
- **`ServerCard.test` / `HeaderCard.test`**：卡片默认查看态。改写为：① 查看态显摘要 + 有 `.edit`/`.del`；**正向锁定 secret 判据**——传 `{password:'', password_set:true}`（header `{value:'', value_set:true}`）断言含「已设置」，传 `{password_set:false}`（`{value_set:false}`）断言不含（防 D1 回归）；② 点 `.del`「移除」emit delete；③ 进编辑态（点 `.edit`）后 `input.pw-secret` type=text、value 恒 ''、占位含「已设置」、非空 secret 不回显；改名后点 `.save-card`「保存」→ emit `update:modelValue`（`__row_id` 保留）+ emit `save`。

### 全绿门槛
`npm run test:run` + `npm run typecheck` + `npm run verify:bundle` 三关全过。

---

## 10. 架构小结与取舍

```
App（.stage>.console：报头 + 主题切换 + 左索引 rail + 错误边界）
├─ v-show(chapter!=='status')  SettingsPanel :chapter  （常挂，state 不丢）
│   ├─ ServerCard × N   （查看↔编辑两态，@save→save()）
│   ├─ HeaderCard × N
│   └─ SectionForm × 当前章 blocks（v-if，随换章卸载）
│        └─ Field（reka-ui，CSS 重塑）
└─ v-if(chapter==='status')    StatusPanel（观测卡，只渲染 StatusResp 字段）
lib/chapters.ts（CHAPTERS）· lib/schema.ts（+hint/+subtitle）· styles/tokens.css（整体重写，pw-* + data-state）
```

**取舍（写死，勿临场发挥）：**
- **换章丢未确认输入（可接受）**：SectionForm 随换章 v-if 卸载；用户在 reka-ui NumberField 键入**未 blur** 就点 rail 切章时，该未提交键入丢失（object 节不做 draft 快照，与卡片不同）。实务中点 rail 按钮会先触发输入框 blur→提交，故常态不丢；仅程序化切章等边缘可能丢。**不为此让 SectionForm 也常挂全 8 节**。
- **sticky/100vh 为渐进增强**：`.stage{min-height:100vh}`、`.rail{sticky}`、`.savebar{sticky bottom}` 在受限 iframe（宿主可能给固定高/内滚）里若产生双滚动条或 sticky 失效，**允许降级为普通 static**（保存按钮可见即可）；任何 iframe 环境下失效都不算回归。

数据流与后端契约零改动；视觉与结构是唯一变量。
