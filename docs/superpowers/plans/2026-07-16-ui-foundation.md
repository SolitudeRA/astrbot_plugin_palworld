# 整体 UI 优化 · 阶段一「地基」Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把设置页的「样式定义层」从散落魔法值收敛为一套完整成体系的设计 token，并据此把排版层级与间距节奏重新定标到更精致的观感，不改动任何组件结构/逻辑/类名/`data-act`/文案。

**Architecture:** 单一全局样式表 `frontend/src/styles/tokens.css` 承载全部 token 与大部分规则；少数组件带 `<style scoped>`。本阶段先在 `tokens.css` 定义并落地全部 token（含 focus-visible 全覆盖、`.mono` 全局化），再把 5 个带 scoped 样式的组件对齐到 token，最后重建入库产物。唯一的 `<script>` 改动是 `App.vue` 首次读系统深浅色偏好。

**Tech Stack:** Vue 3 `<script setup>`、reka-ui、Vitest + @vue/test-utils + jsdom、Vite（单文件产物 + `normalize-eol`）。

## Global Constraints

_（每个任务的要求都隐含包含本节。数值逐字取自 spec `docs/superpowers/specs/2026-07-16-ui-foundation-design.md`。）_

- **CSP 系统字体**：不引入任何 web font；等宽用系统栈 `ui-monospace,"Cascadia Code",Consolas,"SFMono-Regular",monospace`。
- **最小字号 13px**：所有小字（hint/chip/idx/note/subline）不低于 13px。
- **iframe max-width 880**：放大字号后两栏（rail + pane）不得溢出/错位。
- **产物入库 + LF**：`pages/settings/*` 改动只经 `npm run build`（内置 `scripts/normalize-eol.mjs` 统一 LF），绝不手改产物。
- **不碰面**：任何 `template` 结构、类名、`data-act` 钩子、中文文案；`schema.ts` 数据；后端；README。唯一 `<script>` 改动 = `App.vue initialTheme()`。
- **测试断言面**：前端 `*.test.ts` 只断言类名/`data-act`/中文文案（已确认无像素/字号断言）——本阶段不触碰这些，现有前端测试须保持全绿。
- **版本不变**：阶段一纯样式收敛，不改 `metadata.yaml` / `__init__.py` / `_conf_schema.json` 版本号。

## File Structure

| 文件 | 责任 | 本阶段动作 |
|---|---|---|
| `frontend/src/styles/tokens.css` | 唯一全局样式表：全部 token + 大部分规则 | 新增全部 scale token；替换自身魔法值；focus-visible 全覆盖；`.mono` 全局；补 `--on-warn`/`--scrim`/`--mono`；暗色阴影 |
| `frontend/src/App.vue` | 外壳 + 主题初始化 | 仅 `initialTheme()` 读 `prefers-color-scheme` |
| `frontend/src/components/CommandTree.vue` | scoped：树/分段控件 | scoped 魔法值→token；按钮 focus-visible |
| `frontend/src/components/SettingsPanel.vue` | scoped：`.callout`/`.mode-badge` | scoped 魔法值→token |
| `frontend/src/components/ModeConfirmDialog.vue` | scoped：对话框 | backdrop→`--scrim`；魔法值→token；删重复 `.mono`；按钮 focus-visible |
| `frontend/src/components/OrphanCleanup.vue` | scoped：面板 | 魔法值→token；删重复 `.mono` |
| `frontend/src/components/TransferWizard.vue` | scoped：向导 | backdrop→`--scrim`；魔法值→token；删重复 `.mono`；按钮 focus-visible |
| `frontend/src/components/App.test.ts` | App 单测 | 新增主题默认用例 |
| `frontend/src/styles/tokens.drift.test.ts`（新建） | 防漂移静态测试 | 断言无半 px 字号 / 组件 scoped 无裸 hex |
| `pages/settings/*` | 入库构建产物 | `npm run build` 重建 |

---

## Task 1: App.vue 首次尊重系统深浅色

**Files:**
- Modify: `frontend/src/App.vue`（仅 `initialTheme()`，现 24-27 行）
- Test: `frontend/src/App.test.ts`

**Interfaces:**
- Consumes: 无（独立任务）
- Produces: 无下游代码依赖（行为改动，被 Task 5 实机验收）

**验证方式：** 真单测（jsdom 下 mock `matchMedia`）。

- [ ] **Step 1: 写失败测试**

在 `frontend/src/App.test.ts` 增加（若文件已 import `mount`/`App` 则复用，勿重复 import）：

```ts
import { mount } from '@vue/test-utils'
import App from './App.vue'
import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest'

function stubMatchMedia(prefersDark: boolean) {
  vi.stubGlobal('matchMedia', (q: string) => ({
    matches: prefersDark && q.includes('dark'),
    media: q, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false,
  }))
}

describe('首次进入按系统深浅色', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })
  afterEach(() => vi.unstubAllGlobals())

  it('无存储值 + 系统偏好深色 → data-theme=dark', () => {
    stubMatchMedia(true)
    mount(App)
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('无存储值 + 系统偏好浅色 → data-theme=light', () => {
    stubMatchMedia(false)
    mount(App)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('已有存储值时忽略系统偏好（存储优先）', () => {
    localStorage.setItem('palworld-terminal-theme', 'light')
    stubMatchMedia(true)
    mount(App)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/App.test.ts -t "首次进入按系统深浅色"`
Expected: FAIL —— 第 1 例得到 `light`（现逻辑无存储时恒回退 light）。

- [ ] **Step 3: 最小实现**

把 `App.vue` 的 `initialTheme()` 改为（保持「存储 > 预设 data-theme > 系统偏好 > light」优先级）：

```ts
function initialTheme(): 'light' | 'dark' {
  const stored = readStored(); if (stored) return stored
  if (document.documentElement.getAttribute('data-theme') === 'dark') return 'dark'
  try {
    if (typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches) return 'dark'
  } catch { /* 受限 iframe / 老浏览器无 matchMedia：忽略，回退 light */ }
  return 'light'
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/App.test.ts`
Expected: PASS（含既有 App 用例）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/App.vue frontend/src/App.test.ts
git commit -m "feat(fe): 首次进入按系统 prefers-color-scheme 决定明暗（存储优先）"
```

---

## Task 2: tokens.css 收敛（定义全部 token + 落地值 + focus-visible + .mono）

**Files:**
- Modify: `frontend/src/styles/tokens.css`（整文件）

**Interfaces:**
- Consumes: 无
- Produces（下游 Task 3 消费）：
  - 排版：`--fs-display:24 --fs-title:21 --fs-heading:17 --fs-body:15 --fs-sm:14 --fs-caption:13`；`--fw-regular/medium/semibold/bold`；`--lh-tight:1.18 --lh-snug:1.4 --lh-base:1.55`；`--track-brand:.04em --track-eyebrow:.12em --track-wide:.14em`；`--mono`（等宽栈）
  - 间距：`--space-1:4 --space-2:8 --space-3:12 --space-4:16 --space-5:20 --space-6:24 --space-8:32 --space-10:40`
  - 其余：`--r-sm:6 --r:8 --r-lg:12 --r-pill:100`；`--shadow-sm/md/lg/btn`；`--z-sticky:10 --z-dropdown:30 --z-modal:50`；`--motion-fast:120ms --motion-base:180ms --motion-slow:240ms`；`--ease-out --ease-spring`
  - 配色补充：`--on-warn`、`--scrim`
  - 全局工具类：`.mono`；统一 `:focus-visible` 规则

**验证方式：** 前端回归全绿 + 锁值静态测试 + Task 5 实机目测（此任务无新行为断言面，属样式收敛）。

- [ ] **Step 1: 写「锁值」静态测试（先失败）**

新建 `frontend/src/styles/tokens.tokens.test.ts`：

```ts
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

const css = readFileSync(resolve(__dirname, 'tokens.css'), 'utf8')

describe('tokens.css 定义了完整 scale', () => {
  const required = [
    '--fs-display:24px', '--fs-title:21px', '--fs-heading:17px',
    '--fs-body:15px', '--fs-sm:14px', '--fs-caption:13px',
    '--space-1:4px', '--space-4:16px', '--space-10:40px',
    '--r-sm:6px', '--r-lg:12px',
    '--shadow-md:', '--shadow-lg:', '--z-modal:50', '--motion-base:180ms',
    '--on-warn:', '--scrim:', '--mono:',
  ]
  it.each(required)('含 %s', (tok) => {
    expect(css.replace(/\s/g, '')).toContain(tok.replace(/\s/g, ''))
  })
  it('body 使用 --fs-body 而非硬编码 14px', () => {
    expect(/body\s*\{[^}]*font-size:\s*var\(--fs-body\)/.test(css)).toBe(true)
  })
})
```

- [ ] **Step 2: 跑确认失败**

Run: `cd frontend && npx vitest run src/styles/tokens.tokens.test.ts`
Expected: FAIL（token 尚未定义）。

- [ ] **Step 3: 替换 `:root` 与 `[data-theme="dark"]` 定义块**

把 `tokens.css` 顶部的 `:root{…}` 与 `[data-theme="dark"]{…}` 替换为（配色沿用原值，仅新增 scale + `--on-warn`/`--scrim`/`--mono` + 暗色阴影）：

```css
:root {
  /* 配色 */
  --paper:#E9EDE2; --card:#F4F7EE; --sink:#DCE3D3; --raise:#FAFCF5;
  --ink:#182A20; --ink-2:#516359; --ink-3:#84918A;
  --rule:#CFD9C4; --rule-2:#BDC9B0;
  --amber:#D2891C; --amber-h:#B4720E; --amber-soft:#F0DBA8; --on-amber:#231704;
  --flux:#2C9C4E; --flux-soft:#C6E6C8;
  --danger:#CE4630; --warn:#B67F1C; --on-warn:#2A1E06; --focus:#2E82BE;
  --scrim:rgba(0,0,0,.45);
  /* 排版 scale */
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  --mono:ui-monospace,"Cascadia Code",Consolas,"SFMono-Regular",monospace;
  --fs-display:24px; --fs-title:21px; --fs-heading:17px; --fs-body:15px; --fs-sm:14px; --fs-caption:13px;
  --fw-regular:400; --fw-medium:500; --fw-semibold:600; --fw-bold:700;
  --lh-tight:1.18; --lh-snug:1.4; --lh-base:1.55;
  --track-brand:.04em; --track-eyebrow:.12em; --track-wide:.14em;
  /* 间距 / 圆角 / 阴影 / 层级 / 动效 scale */
  --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px; --space-5:20px; --space-6:24px; --space-8:32px; --space-10:40px;
  --r-sm:6px; --r:8px; --r-lg:12px; --r-pill:100px;
  --shadow-sm:0 1px 3px rgba(0,0,0,.28);
  --shadow-md:0 2px 14px color-mix(in srgb,var(--ink) 9%,transparent);
  --shadow-lg:0 8px 24px color-mix(in srgb,var(--ink) 20%,transparent);
  --shadow-btn:0 1px 0 var(--amber-h);
  --z-sticky:10; --z-dropdown:30; --z-modal:50;
  --motion-fast:120ms; --motion-base:180ms; --motion-slow:240ms;
  --ease-out:cubic-bezier(.2,.7,.3,1); --ease-spring:cubic-bezier(.3,1.3,.5,1);
}
[data-theme="dark"] {
  --paper:#17181A; --card:#202225; --sink:#111214; --raise:#26282B;
  --ink:#EAEAE5; --ink-2:#A1A3A1; --ink-3:#6F7173;
  --rule:#2C2E31; --rule-2:#3B3E42;
  --amber:#EAAE55; --amber-h:#F3BE6E; --amber-soft:#2C2410; --on-amber:#1E1608;
  --flux:#57C070; --flux-soft:#16301F;
  --danger:#E7745C; --warn:#D9A94E; --on-warn:#1E1608; --focus:#5BABE6;
  --scrim:rgba(0,0,0,.6);
  --shadow-sm:0 1px 3px rgba(0,0,0,.5);
  --shadow-md:0 2px 14px rgba(0,0,0,.45);
  --shadow-lg:0 10px 30px rgba(0,0,0,.55);
}
```

- [ ] **Step 4: 按对照表替换 tokens.css 中所有规则的魔法值**

**字号（font-size）** 按此表逐处替换（覆盖现有全部 16 个值，含半 px）：

| 现值 | → token | 现值 | → token |
|---|---|---|---|
| 23 | `--fs-display` | 13.5 / 13 | `--fs-sm` |
| 21 | `--fs-title` | 12.5 / 12 / 11.5 / 11 / 10.5 / 10 / 9.5 | `--fs-caption` |
| 17 / 16 | `--fs-heading` | | |
| 15 / 14.5 / 14 | `--fs-body`（正文基准；次要文字用 `--fs-sm`）| | |

> 判断：正文/字段值/按钮主文字用 `--fs-body`；控件内文字、rail 项、读数等次要文字用 `--fs-sm`；一切标签/说明/chip/idx/note 用 `--fs-caption`（下限 13）。

**间距（padding/margin/gap）** 按四舍五入到 4px 网格：

| 现值 | → token | 现值 | → token |
|---|---|---|---|
| 2 | 保留 `2px`（结构性微偏移，如 thumb/border 定位） | 10 / 11 / 12 / 13 | `--space-3` |
| 3 / 4 / 5 | `--space-1` | 14 / 15 / 16 | `--space-4` |
| 6 / 7 / 8 / 9 | `--space-2` | 18 | `--space-5` |
| | | 22 / 26 / 28 | `--space-6` |
| | | 40 | `--space-10` |

**圆角** `8→--r`、`10→--r-lg`、`4/5/7→--r-sm`、`100→--r-pill`。
**阴影** 现有四种 → `--shadow-sm/md/lg/btn`。
**层级** `z-index:30→var(--z-dropdown)`、`50→var(--z-modal)`；给 `.savebar`/`.rail`(sticky) 补 `z-index:var(--z-sticky)`。
**动效** `.12s→var(--motion-fast)`、`.14s/.15s→var(--motion-fast)`、`.18s/.2s→var(--motion-base)`；`.pw-switch-thumb` 位移缓动用 `var(--ease-spring)`。
**行高** `1.5→var(--lh-base)`、`1.15→var(--lh-tight)`、`1.35/1.4→var(--lh-snug)`。
**字距** `.04em→var(--track-brand)`、`.16em→var(--track-eyebrow)`、`.14em→var(--track-wide)`。

代表性 before→after（照此模式处理其余每条规则）：

```css
/* body */
body { margin:0; background:var(--paper); color:var(--ink); font-family:var(--sans);
  font-size:var(--fs-body); line-height:var(--lh-base); }
/* .stage：26/18/40 → 24/16/40 */
.stage { min-height:100vh; padding:var(--space-6) var(--space-4) var(--space-10);
  background-image:radial-gradient(circle at 1px 1px,var(--rule) 1px,transparent 0);
  background-size:22px 22px; background-position:-1px -1px; }
/* .brand .cn：23 → display，字距 token */
.brand .cn { font-size:var(--fs-display); font-weight:var(--fw-semibold); letter-spacing:var(--track-brand); line-height:1; }
/* .chapter-head h2：21 → title */
.chapter-head h2 { font-size:var(--fs-title); font-weight:var(--fw-semibold); margin:0; letter-spacing:.01em; }
/* .card：圆角/阴影 token；editing 阴影 md */
.card { background:var(--card); border:1px solid var(--rule); border-radius:var(--r); overflow:hidden;
  transition:box-shadow var(--motion-base), border-color var(--motion-base); }
.card.editing { border-color:color-mix(in srgb,var(--amber) 55%,var(--rule)); box-shadow:var(--shadow-md); }
/* .commit：字号 body、圆角、按钮阴影 */
.commit { font-size:var(--fs-body); font-weight:var(--fw-semibold); color:var(--on-amber); background:var(--amber);
  border:none; border-radius:var(--r); padding:var(--space-3) var(--space-6); cursor:pointer; box-shadow:var(--shadow-btn); }
/* .savebar：sticky 补 z */
.savebar { display:flex; align-items:center; gap:var(--space-4); margin-top:var(--space-2);
  padding:var(--space-5) 2px var(--space-2); border-top:1.5px solid var(--ink);
  position:sticky; bottom:0; z-index:var(--z-sticky); background:linear-gradient(transparent,var(--paper) 26%); }
```

> 22px 点阵网格尺寸、`-1px` 背景定位、`1.5px` dateline 描边等**特征常量**保留原值，不入 scale。

- [ ] **Step 5: 追加 focus-visible 全覆盖 + `.mono` 全局（tokens.css 末尾）**

```css
/* ---- 统一焦点环：全交互元素可见 ---- */
a:focus-visible, button:focus-visible, [tabindex]:focus-visible,
.rail button:focus-visible, .headbtn:focus-visible, .edit:focus-visible, .del:focus-visible,
.save-card:focus-visible, .cancel-card:focus-visible, .add:focus-visible, .pw-primary:focus-visible {
  outline: 2px solid var(--focus); outline-offset: 2px;
}
/* ---- 全局等宽：标识符确实等宽 ---- */
.mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }
```

> 保留现有各 `:focus-visible`（`.ghost`/`.pw-input`/`.pw-switch`/`.pw-select-trigger`/`.commit`/`.seg` 等有 box-shadow 型焦点的照旧，不被上面覆盖冲突——它们选择器已各自存在）。

- [ ] **Step 6: 跑锁值测试 + 全量前端回归**

Run: `cd frontend && npx vitest run`
Expected: PASS —— 锁值测试通过，且既有全部前端用例仍绿（未触碰类名/文案）。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/styles/tokens.css frontend/src/styles/tokens.tokens.test.ts
git commit -m "feat(fe): tokens.css 收敛为完整 scale 体系（type/space/radius/shadow/z/motion）+ focus-visible 全覆盖 + .mono 全局 + 补 --on-warn/--scrim"
```

---

## Task 3: 组件 scoped 样式对齐 token

**Files:**
- Modify: `frontend/src/components/CommandTree.vue`（`<style scoped>`）
- Modify: `frontend/src/components/SettingsPanel.vue`（`<style scoped>`，`.callout`/`.mode-badge`）
- Modify: `frontend/src/components/ModeConfirmDialog.vue`（`<style scoped>`）
- Modify: `frontend/src/components/OrphanCleanup.vue`（`<style scoped>`）
- Modify: `frontend/src/components/TransferWizard.vue`（`<style scoped>`）

**Interfaces:**
- Consumes: Task 2 Produces 的全部 token
- Produces: 无（Task 4 防漂移测试校验其无裸 hex；Task 5 实机验收）

**验证方式：** 前端回归全绿 + 防漂移测试（Task 4）+ 实机目测。**只改 `<style scoped>` 内的值，不动这些组件的 `<template>`/`<script>`/类名/`data-act`/文案。**

- [ ] **Step 1: 逐组件替换 scoped 魔法值 → token**

对每个组件的 `<style scoped>` 应用与 Task 2 相同的对照表（字号→`--fs-*`、间距→`--space-*`、圆角→`--r*`、阴影→`--shadow-*`、动效→`--motion-*`、行高/字距 token）。要点：

- **ModeConfirmDialog.vue / TransferWizard.vue**：backdrop 的硬编码 `rgba(0,0,0,.45)` → `var(--scrim)`；`z-index:50` → `var(--z-modal)`；模态标题 `<h3>` 的 15px → `--fs-heading`（17，提升对话框标题可读性）。
- **ModeConfirmDialog.vue / OrphanCleanup.vue / TransferWizard.vue**：**删除**各自 scoped 里重复的 `.mono { … }` 定义（改用 Task 2 的全局 `.mono`）。
- **CommandTree.vue**：`.dtag` 的 `var(--on-warn,#fff)` → `var(--on-warn)`（Task 2 已定义，去掉 fallback）；scoped 字号/间距→token。
- **对话框/向导按钮**（`.confirm`/`.danger-btn`/`.mt-switch`/`.ghost` 等 scoped 按钮）：补 `:focus-visible { outline:2px solid var(--focus); outline-offset:2px; }`（scoped 内 button 基线已由全局覆盖，此处为组件专有具名按钮补齐）。

- [ ] **Step 2: 跑全量前端回归**

Run: `cd frontend && npx vitest run`
Expected: PASS（未触碰类名/`data-act`/文案）。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/CommandTree.vue frontend/src/components/SettingsPanel.vue frontend/src/components/ModeConfirmDialog.vue frontend/src/components/OrphanCleanup.vue frontend/src/components/TransferWizard.vue
git commit -m "feat(fe): 5 个 scoped 组件对齐 token（backdrop→--scrim、删重复 .mono、字号/间距/圆角/阴影 token 化、按钮补 focus-visible）"
```

---

## Task 4: 防漂移静态测试

**Files:**
- Create: `frontend/src/styles/tokens.drift.test.ts`

**Interfaces:**
- Consumes: Task 2/3 的成果
- Produces: 无

**验证方式：** 测试本身即交付物——锁住「魔法值不回潮」。

- [ ] **Step 1: 写测试**

```ts
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

const styles = resolve(__dirname, 'tokens.css')
const css = readFileSync(styles, 'utf8')

describe('tokens.css 无半 px 字号漂移', () => {
  it('不含小数 px 字号', () => {
    const halfPx = css.match(/font-size:\s*\d+\.\d+px/g) ?? []
    expect(halfPx).toEqual([])
  })
  it('font-size 一律走 var(--fs-*)（除特征常量 line-height:1 外无裸 px 字号）', () => {
    const rawPx = css.match(/font-size:\s*\d+px/g) ?? []
    expect(rawPx).toEqual([])
  })
})

const COMPONENTS = [
  'CommandTree', 'SettingsPanel', 'ModeConfirmDialog', 'OrphanCleanup', 'TransferWizard',
]
describe('组件 scoped 无裸 hex 颜色', () => {
  it.each(COMPONENTS)('%s.vue scoped 内不含 #hex', (name) => {
    const src = readFileSync(resolve(__dirname, `../components/${name}.vue`), 'utf8')
    const scoped = src.split('<style').slice(1).join('<style')
    const hex = scoped.match(/#[0-9a-fA-F]{3,8}\b/g) ?? []
    expect(hex).toEqual([])
  })
})
```

> COMPONENTS 列表即 Task 3 触碰的 5 个组件。

- [ ] **Step 2: 跑确认通过**

Run: `cd frontend && npx vitest run src/styles/tokens.drift.test.ts`
Expected: PASS。若失败，回到 Task 2/3 补齐遗漏的裸值。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/styles/tokens.drift.test.ts
git commit -m "test(fe): 防漂移——锁 tokens.css 无半px/裸px字号、组件 scoped 无裸 hex"
```

---

## Task 5: 重建 pages/settings 产物 + 明暗实机验收

**Files:**
- Modify: `pages/settings/*`（构建产物）

**Interfaces:**
- Consumes: Task 1–4 全部成果
- Produces: 入库产物

**验证方式：** 构建 + 全套测试 + 明暗实机目测（对照 spec §10 验收标准）。

- [ ] **Step 1: 构建产物（含 LF 归一）**

Run: `cd frontend && npm run build`
Expected: 成功；`pages/settings/assets/index.js` + `style.css` + `index.html` 更新；`normalize-eol` 已跑。

- [ ] **Step 2: 跑全套测试（前端 + 后端 no-drift）**

Run（前端）: `cd frontend && npx vitest run` → Expected: 全绿。
Run（仓库根 no-drift/后端）: `python -m pytest -q` → Expected: 全绿（含 pages/settings golden/no-drift 用例吸收本次产物更新）。

- [ ] **Step 3: 明暗实机目测（用 `/run` 或加载设置页）**

逐项确认（spec §10）：
1. 明暗两主题观感与已确认样张一致：正文 15、章标题 21、组标题 17、最小 13px 不糊、组标题无 eyebrow。
2. 全部交互元素（rail 导航、卡头按钮、弹窗按钮）键盘 Tab 焦点环可见。
3. `.mono` 标识符（ServerCard/AdminCard/GroupCard/CommandTree 中）确实等宽。
4. 首次进入（清 localStorage）按系统 `prefers-color-scheme` 决定明暗。
5. 880 宽 iframe 内两栏不溢出/错位；必要时微调间距档位（回 Task 2/3，重跑 build）。

- [ ] **Step 4: 提交产物**

```bash
git add pages/settings
git commit -m "build(fe): 重建设置页产物（阶段一地基 token 收敛）"
```

---

## Self-Review（作者自查，已执行）

**1. Spec coverage：** ①token 补全→T2；②排版重新定标→T2（字号表）+ 实机 T5；③`.mono` 全局→T2/T3；④系统深浅色→T1；⑤focus-visible→T2（全局）+T3（scoped 按钮）；补 `--on-warn`/`--scrim`→T2/T3；防漂移测试→T4；产物重建→T5。spec §3–§9 均有落点。

**2. Placeholder scan：** 无 TBD/TODO；token 值、对照表、代表规则、测试代码均为实际内容。间距「就近网格」给了完整对照表（非「适当处理」）。

**3. Type consistency：** token 名在 T2 Produces 定义、T3/T4 一致引用（`--fs-*`/`--space-*`/`--scrim`/`--on-warn`/`--mono`）；`initialTheme()` 签名与现有一致；测试文件名/键名前后一致。

**已知裁量点（执行时以实机为准）：** 间距 padding/gap 的档位、`.stage`/`.brand` 等复合间距的具体档，允许在 Task 5 明暗目测后 ±1 档微调并回 T2/T3 重建；不影响 token 体系本身。
