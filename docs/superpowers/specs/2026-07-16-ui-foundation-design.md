# 整体 UI 优化 · 阶段一「地基」设计（spec）

> 日期：2026-07-16　分支：`feat/ui-overhaul`　版本：不发版（纯前端样式层）
> 本文是「整体 UI 优化」三阶段的**第一阶段**设计文档。仅描述设计决策与约束，实现任务拆分见后续 writing-plans 产出的 plan。

## 0. 背景：整体 UI 优化的三阶段

现有设置页（Vue3 + reka-ui，构建产物入库 `pages/settings`）已有一套成熟且有辨识度的「观测台/终端」视觉系统（2026-07-13 重设计定稿）。问题集中在三处：token 体系只做了颜色+圆角（间距/字号/阴影/层级/动效全是散落魔法值）、后期批次组件未对齐定稿系统、无障碍与一致性缺口。

用户已确认方向：**保持观测台/终端视觉方向，做「系统化收敛 + 适度精修」**（观感明显提升但不改方向）。全部约 15 个工作块按依赖分为三阶段，每阶段独立 spec→plan→PR：

- **阶段一 · 地基（本文）**：token 体系补全、排版层级+间距节奏重新定标、`.mono` 全局化、首次尊重系统深浅色、focus-visible 全覆盖。
- **阶段二 · 对齐·破损·原语**：ModeOnboarding 主题化重做、AuditPanel 表格样式化、危险操作统一 `--danger`、抽共享对话框 + 加载/空/错误态原语、枚举值中文化。
- **阶段三 · 控件·模式·精修**：单/多模式 UI 控件复用收敛、UI 控件本身设计打磨、UX 细节（向导步骤指示器/保存反馈统一）、响应式中间带、个别文案直白化。

地基必须先行：后续所有组件对齐都消费本阶段定义的 token。

## 1. 目标与非目标

**目标**：把「样式定义层」从散落魔法值收敛为一套完整、成体系的设计 token，并据此把排版层级与间距节奏重新定标到更精致耐看的观感——**不改动任何组件的结构、逻辑、类名、`data-act` 钩子或中文文案**。

**非目标（明确留给后续阶段）**：ModeOnboarding 结构重做、AuditPanel 表格样式化、危险色统一、共享对话框/状态原语、枚举中文化（阶段二）；单/多模式控件复用、控件设计打磨、响应式中间带、文案直白化（阶段三）。本阶段只碰样式值，不碰模板与业务逻辑（唯一例外：App.vue 主题初始化，见 §4.6）。

## 2. 视觉基调（已通过可视化伴侣确认）

在浏览器实机样张上与用户敲定了三条**可见**决策：

1. **整体放大一档**——正文 14→15、章标题 21、组标题 17、品牌 24。用户确认「对劲了」。
2. **最小字号 = 13px**——用户在明暗底、11/12/13px×400/500 的清晰度诊断中选定 **13px/400**（D 档）。原因：系统字体受 CSP 限制不可替换，Windows 中文小字回退 Microsoft YaHei，11–12px 在 ClearType 下发虚；13px 起清晰。**所有小字（说明 hint、chip、`idx`、note、subline）不低于 13px**。
3. **组标题保持朴素，不加 eyebrow**——组标题维持现有结构（标题 + 右侧说明）。装饰性编号不符「结构即信息」，且现有组标题本就无 eyebrow，最克制、改动最小。

## 3. Type scale（16 个散落字号 → 6 级）

现状：`tokens.css` 及组件 scoped 样式散落 ~16 个字号（23/21/17/16/15/14.5/14/13.5/13/12.5/12/11.5/11/10.5/10/9.5），含大量半 px，无层级体系。

**新 type scale（6 级，最小 13）**，定义在 `tokens.css :root`：

| token | 值 | 字重 | 行高 | 用途 |
|---|---|---|---|---|
| `--fs-display` | 24px | 600 | `--lh-tight` | 品牌 CN（`.brand .cn`） |
| `--fs-title` | 21px | 600 | `--lh-tight` | 章标题（`.chapter-head h2`） |
| `--fs-heading` | 17px | 600 | `--lh-tight` | 组标题 `.t`、卡名 `.nm`、观测名 `.obs .nm` |
| `--fs-body` | 15px | 400 | `--lh-base` | 正文、字段值 `.cv`、控件文字、保存按钮 |
| `--fs-sm` | 14px | 400 | `--lh-base` | 次要文字、rail 项、读数 `.read` |
| `--fs-caption` | 13px | 400 | `--lh-snug` | 说明 hint、chip、`idx`、note、subline、eyebrow —— **下限 13** |

辅助 token：
- 字重：`--fw-regular:400` `--fw-medium:500` `--fw-semibold:600` `--fw-bold:700`（新增 500，供小标签在需要时增重而不增号）。
- 行高：`--lh-tight:1.18`（标题）`--lh-snug:1.4`（密集说明）`--lh-base:1.55`（正文）。
- 字距：`--track-brand:.04em`（品牌）`--track-eyebrow:.12em`（uppercase 小标/subline，从 .16 收窄减轻小字发虚）。
- 数字读数统一 `font-variant-numeric: tabular-nums`（读数、`idx`、数字输入、审计——由 `.mono`/`.read`/`.cv` 等承载）。

**收敛映射原则**（整体放大一档，旧值普遍上移一档——旧基准正文 14→新 body 15、旧次要 13.5→新 sm 14）：23→display24；21→title21；16/17→heading17；14/15→body15；13/13.5/14.5→sm14；9.5/10/10.5/11/11.5/12/12.5→caption13（就近上归到 13 下限）。半 px 全部消灭。

**已知取舍**：把 <13 的小标签（chip 原 10–10.5、`idx` 原 10、note 原 11–12）统一抬到 13，会使这些标签视觉变大、整体信息密度略降。**层级改由字重/颜色/透明度维持，而非字号**（如 chip 用 `--fw-medium` + 语义色，note 用 `--ink-3`）。这是清晰度优先的必然结果，符合用户「最小 13」决策。

## 4. 其余地基 token（技术性收敛，观感无争议）

### 4.1 Space scale（4px 基网格）
现状散落 2/3/5/6/9/10/11/13/14/18/22/26/28 等偏移值。定义：`--space-1:4` `--space-2:8` `--space-3:12` `--space-4:16` `--space-5:20` `--space-6:24` `--space-8:32` `--space-10:40`。归一原则：就近对齐 4px 网格（3/5→4，9→8，10/11/13→12，14→16，18→16 或 20，22→20 或 24，26/28→24 或 32）。极小的结构性偏移（如开关 thumb 的 2px 定位）作为局部常量保留，不入 scale。

### 4.2 Radius scale
`--r-sm:6`（吸收 4/5/7）`--r:8`（保留，默认）`--r-lg:12`（吸收 10）`--r-pill:100`。

### 4.3 Shadow scale（明暗各调）
`--shadow-sm`（`0 1px 3px`，开关 thumb）`--shadow-md`（`0 2px 14px`，卡片/editing）`--shadow-lg`（`0 8px 24px`，下拉/浮层）`--shadow-btn`（`0 1px 0 var(--amber-h)`，实心按钮底边）。暗色主题下 md/lg 改用更深的 `rgba(0,0,0,.45~.55)`，替代 `color-mix(ink)` 在暗底偏弱的问题。

### 4.4 Z-index scale
`--z-sticky:10`（savebar/rail sticky）`--z-dropdown:30`（select content）`--z-modal:50`（对话框 backdrop）。消除裸数字。

### 4.5 Motion scale
`--motion-fast:120ms`（hover 微反馈）`--motion-base:180ms`（一般过渡）`--motion-slow:240ms`（位移）；缓动 `--ease-out:cubic-bezier(.2,.7,.3,1)`、`--ease-spring:cubic-bezier(.3,1.3,.5,1)`（保留给开关 thumb 弹性）。`prefers-reduced-motion` 现有全局屏蔽保留。

### 4.6 Focus-visible 全覆盖
现状：仅 `.ghost/.pw-input/.pw-switch/.pw-select-trigger/.commit/.ct-gname/.seg` 有焦点态；rail 导航按钮、卡头按钮（`.headbtn/.edit/.del/.save-card/.cancel-card/.add`）、弹窗按钮（`.pw-primary` 等）**无 `:focus-visible`**，键盘焦点不可见。

定义统一约定 `--focus-ring`：`outline: 2px solid var(--focus); outline-offset: 2px`。给**所有交互元素**补 `:focus-visible`，包括一条 `button:focus-visible` 基线（使即便阶段一不重做的离群按钮也有可见焦点）。这是阶段一唯一的无障碍项；对话框语义/焦点陷阱属阶段二。

### 4.7 `.mono` 全局化
现状：`.mono` 仅在三个组件的 scoped 样式里定义，导致 `ServerCard/AdminCard/GroupCard/CommandTree`（无 scoped 块）里标注为 `mono` 的标识符**静默回退 sans**。将 `.mono { font-family: ui-monospace, "Cascadia Code", Consolas, "SFMono-Regular", monospace; font-variant-numeric: tabular-nums }` 提升到 `tokens.css` 全局（均为系统等宽字体，不违反 CSP）。同步删除三个组件里重复的 scoped `.mono` 定义。

### 4.8 首次尊重系统深浅色
现状：`App.vue initialTheme()` 无 localStorage 时恒回退 light，从不读系统偏好。改为：无存储值时读 `window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'`。用户手动切换后仍写入并锁定 localStorage（不引入「跟随系统」第三态，保持行为简单）。这是本阶段**唯一**的 `<script>` 逻辑改动。

### 4.9 补缺的 color / on-* token
- `--on-warn`：新增（暗底文字色），修复 `CommandTree.vue` 中 `var(--on-warn,#fff)` 的空引用。
- `--scrim`：新增对话框遮罩 token（light `rgba(0,0,0,.45)`、dark `rgba(0,0,0,.6)`），替换 `ModeConfirmDialog`/`TransferWizard` 中硬编码的 `rgba(0,0,0,.45)`（纯值替换，不动结构）。
- 说明：`ModeOnboarding` 的假 token `--pw-border`/`--pw-accent` 属其结构重做，**留阶段二**；本阶段只定义好真 token 供阶段二消费，不碰 ModeOnboarding。

## 5. Token 组织与命名（tokens.css）

`tokens.css` 保持单一全局样式表。`:root` 分区：① 明色配色（现有，微调见 §4.3/4.9）② 明暗共享的排版/间距/圆角/阴影/层级/动效 scale（新增，§3–§4）③ `[data-theme="dark"]` 覆盖配色 + 暗色阴影。命名遵循现有 `--r` 风格：语义前缀 + 档位（`--fs-*`/`--space-*`/`--r-*`/`--shadow-*`/`--z-*`/`--motion-*`/`--fw-*`/`--lh-*`/`--track-*`）。所有既有规则的魔法值替换为对应 token 引用。

## 6. 改动边界

**碰**：
- `frontend/src/styles/tokens.css`——新增全部 scale token；替换自身所有魔法值；focus-visible 全覆盖；`.mono` 全局；补 `--on-warn`/`--scrim`；暗色阴影调整。
- `frontend/src/App.vue`——仅 `initialTheme()` 读 `prefers-color-scheme`（§4.8）。
- 各带 `<style scoped>` 的组件（`CommandTree`/`SettingsPanel`/`ModeConfirmDialog`/`OrphanCleanup`/`TransferWizard`）——scoped 样式里的字号/间距/圆角/阴影/backdrop 魔法值 → token；删除重复 `.mono`。**只改样式值，不动 template/script/类名/`data-act`/文案。**
- `pages/settings/*`——`npm run build`（含 `normalize-eol`）重建产物。

**不碰**：任何 template 结构、`data-act`、类名、中文文案；ModeOnboarding 结构；AuditPanel 表格；后端；`schema.ts` 数据（`PAL_TREE` 受 Python 测试锚定）；`docs`/README 文案（无字号相关锚点）。

## 7. 约束与不变量

- **CSP 系统字体**：type scale 不引入任何 web font；`.mono` 用系统等宽栈。
- **iframe max-width 880**：放大字号后须实机确认两栏（rail + pane）布局不溢出、不换行错位。正文 15 / 最小 13 比现状大，密度下降但 880 宽足够——实现时以 `/run` 或截图目测确认。
- **产物入库 + LF**：只用 `npm run build`（内置 `normalize-eol`），避免 CRLF 幻影脏。
- **测试断言面**：前端 `*.test.ts` 仅断言类名/`data-act`/中文文案（已 grep 确认无像素/字号断言），本阶段不触碰这些 → 现有前端测试应全绿。

## 8. 测试影响与验证

- **现有前端测试**：预期全绿（不改类名/钩子/文案）。若个别快照因类结构不变但样式变而无影响，无需改。
- **建议新增防漂移测试（可选，低成本）**：一条断言 `tokens.css` 不再含半 px 字号（正则扫 `\d+\.\d+px`）、且组件 scoped 样式不含裸 `#hex` 颜色的静态测试，锁住「魔法值不回潮」。是否纳入由 plan 决定。
- **产物 no-drift**：重建后 golden/no-drift 测试更新一次。
- **实机验证**：明暗两主题下逐章目测——排版层级清晰、小字 ≥13 不糊、焦点环全元素可见、`.mono` 标识符确实等宽、首次进入按系统深浅色、880 宽不溢出。

## 9. 风险与取舍

| 风险 | 缓解 |
|---|---|
| 全局放大 + 最小 13 使信息密度下降、小标签变大 | 层级改由字重/颜色维持而非字号；已获用户实测确认清晰度优先 |
| 收敛触碰 tokens.css 几乎每条规则，diff 面大 | 单文件、无逻辑、测试类名不动；逐块替换 + 实机截图核对 |
| 组件 scoped 魔法值遗漏未 token 化 | plan 中逐组件清点；可选防漂移测试兜底 |
| 放大后 880 iframe 内溢出/错位 | 实机 `/run` 明暗逐章目测，作为验收项 |
| 离群组件（ModeOnboarding）不吃新 token 显得更突兀 | 本就待修；阶段二重做时对齐；阶段一 button:focus-visible 基线已给其焦点态 |

## 10. 验收标准

1. `tokens.css` 含完整 6 类 scale token，`:root` 无散落魔法字号/间距；半 px 归零。
2. 明暗两主题实机观感与已确认样张一致：正文 15、章标题 21、组标题 17、最小 13px 不糊、组标题无 eyebrow。
3. 全部交互元素（含 rail、卡头按钮、弹窗按钮）键盘焦点可见。
4. `.mono` 标识符在所有卡片/树中确实等宽。
5. 首次进入按系统 `prefers-color-scheme` 决定明暗；手动切换后锁定。
6. 前端测试全绿；`pages/settings` 产物重建且 LF 干净；`ruff`/`mypy` 不涉及（纯前端）。
