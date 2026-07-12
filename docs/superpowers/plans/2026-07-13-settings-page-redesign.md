# 设置页重设计 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development 逐任务执行。步骤用 `- [ ]` 复选框跟踪。

**Goal:** 把设置/状态页从「两 tab + 平铺 8 节」重构为「左索引分章观测台」布局并落地定稿视觉系统，零后端契约改动。

**Architecture:** App 变为壳（报头 + 主题切换 + 左索引 rail + 章节路由 + 错误边界）；SettingsPanel v-show 常挂、按 `chapter` prop 分章渲染并持有全部状态与保存逻辑；StatusPanel v-if 按需挂载。条目卡片查看↔编辑两态。Field 降为纯控件，label/hint 归父级网格。tokens.css 整体重写为 pw-\* 类 + reka-ui `data-state`。

**Tech Stack:** Vue 3.5.39 + reka-ui 2.10.1 + Vite 7.3.6 + Vitest 3.2.7（不升级、不新增依赖）。

**参考真源：** 设计规格 `docs/superpowers/specs/2026-07-13-settings-page-redesign-design.md`（含 §0 demo 真源优先级、§2.4 控件类名映射、§7 不变量）；视觉基准 `docs/design/settings-redesign-demo.html`（视觉/交互示意，非数据/类名真源）。

## Global Constraints

- **只改前端表现层。** 绝不动 `lib/collect.ts`、`lib/bridge.ts`、`lib/errors.ts`、`lib/boot.ts`、`main.ts`、`global.d.ts`、任何 `.py`、`_conf_schema.json`、`vite.config.ts`。
- **`lib/schema.ts` 只增** `FieldSpec.hint?`/`ObjectSection.subtitle?` 两个可选属性 + 替换 label/hint 字符串；**严禁**改任何 `key`/`type`/`default`/`options`/`secret`/字段顺序。
- **demo 与生产冲突处以生产为准**：secret 判据读 `password_set`/`value_set` 布尔（非明文 `d.password`/`d.value`）；控件按 `.pw-switch`/`.pw-number-*`/`.pw-select-*` + `data-state` 写 CSS（非 demo 的 `.switch`/`.stepper`/`.dd`）；Select 定位沿用 reka-ui item-aligned（不追 demo 贴行 absolute）。
- **secret 红线**：`type=text` + `.pw-secret`(`-webkit-text-security:disc` 走类非内联) + 非受控不回显 + 占位据各自 `*_set`（ServerCard=password_set、HeaderCard=value_set）。
- **提交按钮**必须同时带 `commit` 与 `pw-save` 两个类。
- **主题**：只写自身 `document.documentElement` 的 `data-theme`；`localStorage` 全程 try/catch（含读路径）。
- **单文件产物**：不加 `import()`、不加第二 CSS 入口、不加依赖。
- **默认章 = `access`**，SettingsPanel v-show 常挂（错误边界前提）。
- **提交信息不得出现任何 Claude/AI/🤖 署名**。Python 用 `.\.venv\Scripts\python.exe`（`python` 被 Windows 拦截）；前端命令在 `frontend/` 下跑。

---

## File Structure

| 文件 | 动作 | 职责 |
|------|------|------|
| `frontend/src/lib/chapters.ts` | 新建 | `CHAPTERS` 常量 + `DEFAULT_CHAPTER`；章→blocks 映射 |
| `frontend/src/lib/chapters.test.ts` | 新建 | blocks 并集 = OBJECT_SECTIONS 全 8 键（不重不漏） |
| `frontend/src/lib/schema.ts` | 改 | 加 `hint?`/`subtitle?` + 打磨 label/hint |
| `frontend/src/styles/tokens.css` | 重写 | 新 tokens + 布局类 + pw-\* 控件重塑 |
| `frontend/src/components/Field.vue` | 改 | 剥离 label 包裹，只渲染控件（角色/emit 不变） |
| `frontend/src/components/Field.test.ts` | 改 | 去掉 enum 的 label 断言，其余保留 |
| `frontend/src/components/SectionForm.vue` | 改 | `.entry/.row` 排布 + 渲染 subtitle/hint |
| `frontend/src/components/ServerCard.vue` | 改 | 查看↔编辑两态 |
| `frontend/src/components/ServerCard.test.ts` | 改 | 两态 + secret 判据正向锁定 |
| `frontend/src/components/HeaderCard.vue` | 改 | 查看↔编辑两态（value_set） |
| `frontend/src/components/HeaderCard.test.ts` | 改 | 同上 |
| `frontend/src/components/StatusPanel.vue` | 改 | 观测卡外观（保文案锚点） |
| `frontend/src/components/SettingsPanel.vue` | 改 | `chapter` prop 分章渲染 + 卡片保存联动 |
| `frontend/src/components/SettingsPanel.test.ts` | 改 | 分章断言 + 保留契约断言 |
| `frontend/src/App.vue` | 改 | 报头 + rail + 主题切换 + 章节路由 |
| `frontend/src/App.test.ts` | 改 | rail 导航 + 错误边界 |

**任务顺序（依赖）：** 1 chapters → 2 schema → 3 tokens.css → 4 Field → 5 SectionForm → 6 ServerCard → 7 HeaderCard → 8 StatusPanel → 9 SettingsPanel → 10 App → 11 整合验收。

---

### Task 1: lib/chapters.ts + 一致性测试

**Files:**
- Create: `frontend/src/lib/chapters.ts`
- Test: `frontend/src/lib/chapters.test.ts`

**Interfaces:**
- Produces: `interface Chapter { id: string; label: string; group: '观测'|'配置'; kind: 'status'|'settings'; blocks?: string[] }`；`export const CHAPTERS: Chapter[]`；`export const DEFAULT_CHAPTER = 'access'`。

- [ ] **Step 1: 写失败测试** `frontend/src/lib/chapters.test.ts`

```ts
import { describe, it, expect } from 'vitest'
import { CHAPTERS, DEFAULT_CHAPTER } from './chapters'
import { OBJECT_SECTIONS } from './schema'

describe('chapters', () => {
  it('默认章为 access 且存在', () => {
    expect(DEFAULT_CHAPTER).toBe('access')
    expect(CHAPTERS.some((c) => c.id === 'access')).toBe(true)
  })
  it('配置章的 blocks 并集恰等于 OBJECT_SECTIONS 全 8 键（不重不漏）', () => {
    const union = CHAPTERS.flatMap((c) => c.blocks ?? [])
    expect(union.slice().sort()).toEqual(OBJECT_SECTIONS.map((s) => s.key).slice().sort())
    expect(new Set(union).size).toBe(union.length) // 无重复
  })
  it('恰一个 status 章', () => {
    expect(CHAPTERS.filter((c) => c.kind === 'status')).toHaveLength(1)
  })
})
```

- [ ] **Step 2: 跑测试确认失败** — Run: `cd frontend && npm run test:run -- chapters`。Expected: FAIL（模块不存在）。

- [ ] **Step 3: 写 `frontend/src/lib/chapters.ts`**

```ts
export interface Chapter {
  id: string
  label: string
  group: '观测' | '配置'
  kind: 'status' | 'settings'
  blocks?: string[] // 该配置章渲染的 OBJECT_SECTIONS 键
}

export const CHAPTERS: Chapter[] = [
  { id: 'status', label: '观测台', group: '观测', kind: 'status' },
  { id: 'access', label: '接入', group: '配置', kind: 'settings', blocks: ['routing'] },
  { id: 'cadence', label: '采集', group: '配置', kind: 'settings', blocks: ['polling'] },
  { id: 'world', label: '世界与据点', group: '配置', kind: 'settings', blocks: ['world', 'bases'] },
  { id: 'privacy', label: '隐私与留存', group: '配置', kind: 'settings', blocks: ['privacy', 'history'] },
  { id: 'feature', label: '功能分组', group: '配置', kind: 'settings', blocks: ['features', 'players'] },
]

export const DEFAULT_CHAPTER = 'access'
```

- [ ] **Step 4: 跑测试确认通过** — Run: `cd frontend && npm run test:run -- chapters`。Expected: PASS。
- [ ] **Step 5: 提交** — `git add frontend/src/lib/chapters.ts frontend/src/lib/chapters.test.ts && git commit -m "feat(fe): 章节结构常量 chapters.ts + blocks 覆盖一致性测试"`

---

### Task 2: schema.ts 增补展示属性 + 打磨文案

**Files:**
- Modify: `frontend/src/lib/schema.ts`

**Interfaces:**
- Produces: `FieldSpec` 加 `hint?: string`；`ObjectSection` 加 `subtitle?: string`。key/type/default/options/顺序/secret 不变。

- [ ] **Step 1: 确认现有测试基线** — Run: `cd frontend && npm run test:run -- schema`。Expected: PASS（改动前）。

- [ ] **Step 2: 改类型定义**（`frontend/src/lib/schema.ts` 顶部）

```ts
export interface FieldSpec {
  key: string
  type: FieldType
  label: string
  default: unknown
  options?: string[]
  secret?: boolean // password / value：不预填、走哨兵
  hint?: string // 仅展示：字段说明（不参与 collect/schema 对齐）
}
export interface ObjectSection { key: string; title: string; fields: FieldSpec[]; subtitle?: string }
```

- [ ] **Step 3: 替换 SERVER_FIELDS / HEADER_FIELDS 的 label 并加 hint**（**key/type/default/secret 一字不改**）

```ts
export const SERVER_FIELDS: FieldSpec[] = [
  { key: 'name', type: 'string', label: '名称', default: '', hint: '唯一标识，勿含空格 / 冒号 / @' },
  { key: 'enabled', type: 'bool', label: '启用', default: true },
  { key: 'base_url', type: 'string', label: '服务器地址', default: 'http://127.0.0.1:8212', hint: '官方只读 REST 端点，含端口（默认 8212）' },
  { key: 'username', type: 'string', label: '用户名', default: 'admin' },
  { key: 'password', type: 'string', label: '密码', default: '', secret: true, hint: '留空则保持不变；更推荐用下方环境变量' },
  { key: 'password_env', type: 'string', label: '密码环境变量名', default: '', hint: '与密码二选一，更安全' },
  { key: 'timeout', type: 'int', label: '超时（秒）', default: 10 },
  { key: 'verify_tls', type: 'bool', label: '校验 TLS 证书', default: true, hint: 'http 地址不校验' },
  { key: 'timezone', type: 'string', label: '时区', default: '', hint: '如 Asia/Tokyo；留空用全局时区' },
]

export const HEADER_FIELDS: FieldSpec[] = [
  { key: 'name', type: 'string', label: '名称', default: '', hint: '如 CF-Access-Client-Id' },
  { key: 'value', type: 'string', label: '值', default: '', secret: true, hint: '留空则保持不变；敏感值更推荐用环境变量' },
  { key: 'value_env', type: 'string', label: '值环境变量名', default: '', hint: '与值二选一，更安全' },
  { key: 'servers', type: 'string', label: '限定服务器', default: '', hint: '多个用逗号分隔；留空 = 发给所有服务器' },
]
```

- [ ] **Step 4: 给 8 个 OBJECT_SECTIONS 加 subtitle + 字段 hint**（key/type/default/options/顺序不变；逐节替换）

```ts
export const OBJECT_SECTIONS: ObjectSection[] = [
  { key: 'routing', title: '路由与访问控制', subtitle: '群 ↔ 服务器 的寻址与授权', fields: [
    { key: 'access_mode', type: 'enum', label: '访问模式', default: 'restricted', options: ['restricted', 'open'], hint: 'restricted 需管理员授权 · open 全开放' },
    { key: 'default_server', type: 'string', label: '默认服务器', default: '', hint: '群里没指定、也没绑定时用它' },
  ]},
  { key: 'polling', title: '轮询间隔', subtitle: '每个端点多久拉取一次数据（秒）', fields: [
    { key: 'metrics_seconds', type: 'int', label: 'metrics 指标', default: 30 },
    { key: 'players_seconds', type: 'int', label: 'players 在线', default: 30 },
    { key: 'info_seconds', type: 'int', label: 'info 信息', default: 600 },
    { key: 'settings_seconds', type: 'int', label: 'settings 设置', default: 1800 },
    { key: 'game_data_seconds', type: 'int', label: 'game-data 世界快照', default: 120, hint: '仅「公会与据点」开启时才拉取' },
    { key: 'jitter_ratio', type: 'float', label: '抖动比例', default: 0.10, hint: '给间隔加随机抖动，避免整点齐发' },
    { key: 'max_concurrency', type: 'int', label: '并发上限', default: 6, hint: '同时进行的请求数上限' },
  ]},
  { key: 'world', title: '世界与展示', subtitle: '时区与 FPS 流畅度分档', fields: [
    { key: 'timezone', type: 'string', label: '全局时区', default: 'Asia/Tokyo', hint: 'IANA' },
    { key: 'locale', type: 'enum', label: '文案语言', default: 'zh-CN', options: ['zh-CN'] },
    { key: 'fps_smooth', type: 'int', label: 'FPS 流畅阈值', default: 50, hint: '≥ 此值 = 流畅' },
    { key: 'fps_moderate', type: 'int', label: 'FPS 一般阈值', default: 35, hint: '≥ 此值 = 一般' },
    { key: 'fps_laggy', type: 'int', label: 'FPS 卡顿阈值', default: 20, hint: '≥ 此值 = 卡顿，低于 = 严重卡顿' },
  ]},
  { key: 'bases', title: '据点推导', subtitle: '仅在「公会与据点」开启时生效', fields: [
    { key: 'enabled', type: 'bool', label: '启用据点推导', default: true },
    { key: 'assignment_radius', type: 'int', label: '归属半径', default: 5000 },
    { key: 'ambiguity_ratio', type: 'float', label: '模糊比阈值', default: 0.20, hint: '最近 / 次近距离差比' },
    { key: 'confirmation_samples', type: 'int', label: '确认次数', default: 3 },
    { key: 'position_grid_size', type: 'int', label: '坐标网格', default: 2000, hint: '坐标量化网格边长' },
    { key: 'z_weight', type: 'float', label: 'Z 轴权重', default: 0.5 },
  ]},
  { key: 'privacy', title: '隐私与脱敏', subtitle: '决定纪事如何收敛个体信息', fields: [
    { key: 'mode', type: 'enum', label: '隐私模式', default: 'balanced', options: ['strict', 'balanced', 'advanced'], hint: 'strict 最保守 · balanced 默认' },
    { key: 'public_exact_ping', type: 'bool', label: '公开精确 Ping', default: false, hint: '关 = 只显示优秀 / 正常 / 偏高' },
    { key: 'public_positions', type: 'bool', label: '公开坐标', default: false },
    { key: 'ping_good_ms', type: 'int', label: 'Ping 优秀阈值', default: 60, hint: '≤ 此值 = 优秀（毫秒）' },
    { key: 'ping_ok_ms', type: 'int', label: 'Ping 正常阈值', default: 120, hint: '≤ = 正常，超过 = 偏高（毫秒）' },
    { key: 'uncertain_timeout', type: 'int', label: '掉线判定超时', default: 900, hint: '多久无响应即判定离线（秒）' },
  ]},
  { key: 'history', title: '保留清理天数', subtitle: '各类数据的留存窗口（天）', fields: [
    { key: 'raw_metrics_days', type: 'int', label: '原始指标天数', default: 7 },
    { key: 'aggregate_days', type: 'int', label: '预聚合天数', default: 90 },
    { key: 'session_days', type: 'int', label: '会话天数', default: 365 },
    { key: 'observation_days', type: 'int', label: '观察天数', default: 180 },
  ]},
  { key: 'features', title: '功能分组开关', subtitle: '关掉的分组不采集数据，相关命令提示「未开放」', fields: [
    { key: 'report', type: 'bool', label: '日报 / 在线统计', default: true, hint: '/pal today' },
    { key: 'events', type: 'bool', label: '世界事件记录', default: true, hint: '/pal events' },
    { key: 'guilds_bases', type: 'bool', label: '公会与据点', default: false, hint: '依赖 /game-data；专用服务器暂不支持' },
    { key: 'players', type: 'bool', label: '玩家个体查询', default: false, hint: '排行 / 档案 / 自助绑定' },
  ]},
  { key: 'players', title: '玩家个体', subtitle: '「玩家个体查询」开启时生效', fields: [
    { key: 'rank_top_n', type: 'int', label: '排行榜人数', default: 5 },
    { key: 'exclude_names', type: 'string', label: '排除名单', default: '', hint: '逗号分隔，排除出榜 / 查询' },
  ]},
]
```

- [ ] **Step 5: 跑对齐测试确认仍绿** — Run: `cd frontend && npm run test:run -- schema collect` 与 `npm run typecheck`。Expected: PASS（key 集不变，hint/subtitle 为可选新增）。
- [ ] **Step 6: 提交** — `git add frontend/src/lib/schema.ts && git commit -m "feat(fe): schema 增可选 hint/subtitle 展示属性 + 打磨字段文案"`

---

### Task 3: tokens.css 整体重写（新设计系统）

**Files:**
- Modify（整体替换）: `frontend/src/styles/tokens.css`

**Interfaces:**
- 提供全部布局类（`.stage/.console/.mast/.brand/.ghost/.dateline/.subline/.layout/.rail/.railcap/.pane/.chapter-head/.group-head/.entry-head/.entry-title/.entry-role/.grouphint/.row/.rlabel/.rctl`）、卡片类（`.card/.card-head/.idx/.nm/.editing-tag/.grow/.hchip/.headbtn/.edit/.del/.save-card/.cancel-card/.savedflash/.cbody/.crow/.ck/.cv/.add`）、savebar（`.savebar/.commit/.receipt/.note`）、观测卡（`.obs/.chip/.stint`）、控件重塑（`.pw-input/.pw-secret/.pw-switch(-thumb)/.pw-number(-btn/-input)/.pw-select-trigger/-content/-item`）、状态（`.pw-settings/.pw-status/.pw-muted/.pw-error/.pw-fatal/.pw-primary`）。
- **按规格 §2.4：控件用 pw-\* 类 + reka-ui `data-state`（switch=`[data-state=checked]`、select 面板 `[data-highlighted]`/`[data-state=checked]`）。**

- [ ] **Step 1: 整体替换 `frontend/src/styles/tokens.css` 为：**

```css
:root {
  --paper:#E9EDE2; --card:#F4F7EE; --sink:#DCE3D3; --raise:#FAFCF5;
  --ink:#182A20; --ink-2:#516359; --ink-3:#84918A;
  --rule:#CFD9C4; --rule-2:#BDC9B0;
  --amber:#D2891C; --amber-h:#B4720E; --amber-soft:#F0DBA8; --on-amber:#231704;
  --flux:#2C9C4E; --flux-soft:#C6E6C8;
  --danger:#CE4630; --warn:#B67F1C; --focus:#2E82BE;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  --r:8px;
}
[data-theme="dark"] {
  --paper:#17181A; --card:#202225; --sink:#111214; --raise:#26282B;
  --ink:#EAEAE5; --ink-2:#A1A3A1; --ink-3:#6F7173;
  --rule:#2C2E31; --rule-2:#3B3E42;
  --amber:#EAAE55; --amber-h:#F3BE6E; --amber-soft:#2C2410; --on-amber:#1E1608;
  --flux:#57C070; --flux-soft:#16301F;
  --danger:#E7745C; --warn:#D9A94E; --focus:#5BABE6;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--paper); color: var(--ink); font-family: var(--sans); font-size: 14px; line-height: 1.5; }

/* ---- shell ---- */
.stage { min-height: 100vh; padding: 26px 18px 40px;
  background-image: radial-gradient(circle at 1px 1px, var(--rule) 1px, transparent 0); background-size: 22px 22px; background-position: -1px -1px; }
.console { max-width: 880px; margin: 0 auto; }
.mast { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.brand { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.brand .cn { font-size: 23px; font-weight: 600; letter-spacing: .04em; line-height: 1; }
.brand .en { font-size: 12px; letter-spacing: .34em; text-transform: uppercase; color: var(--ink-3); }
.ghost { font-size: 11px; text-transform: uppercase; color: var(--ink-2); background: none; border: 1px solid var(--rule); border-radius: var(--r); padding: 5px 10px; cursor: pointer; }
.ghost:hover { border-color: var(--rule-2); color: var(--ink); }
.ghost:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.dateline { height: 0; border-top: 1.5px solid var(--ink); border-bottom: 1px solid var(--rule-2); margin: 12px 0 2px; padding-top: 3px; }
.subline { display: flex; justify-content: space-between; align-items: center; gap: 12px; color: var(--ink-3); font-size: 11px; letter-spacing: .14em; text-transform: uppercase; }
.layout { display: flex; gap: 28px; margin-top: 22px; align-items: flex-start; }
.rail { flex: 0 0 156px; position: sticky; top: 16px; display: flex; flex-direction: column; gap: 1px; }
.railcap { font-size: 9.5px; letter-spacing: .22em; text-transform: uppercase; color: var(--ink-3); padding: 0 0 5px 12px; }
.rail button + .railcap { margin-top: 16px; }
.rail button { text-align: left; font-size: 13.5px; color: var(--ink-2); background: none; border: none; border-left: 2px solid transparent; cursor: pointer; padding: 8px 12px; border-radius: 0 var(--r) var(--r) 0; display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; transition: background .14s, color .14s; }
.rail button:hover { color: var(--ink); background: color-mix(in srgb, var(--focus) 8%, transparent); }
.rail button[aria-current="true"] { color: var(--ink); border-left-color: var(--focus); background: color-mix(in srgb, var(--focus) 13%, transparent); font-weight: 600; font-size: 14.5px; }
.rail .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--flux); flex: 0 0 auto; }
.pane { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 26px; }
.pw-settings, .pw-status { display: flex; flex-direction: column; gap: 22px; }
.chapter-head { display: flex; align-items: baseline; gap: 12px; }
.chapter-head h2 { font-size: 21px; font-weight: 600; margin: 0; letter-spacing: .01em; }
.group-head, .entry-head { display: flex; align-items: baseline; gap: 12px; padding-bottom: 9px; border-bottom: 1px solid var(--rule); margin-bottom: 6px; }
.group-head .t, .entry-title { font-size: 17px; font-weight: 600; letter-spacing: .01em; line-height: 1.15; }
.group-head .c, .entry-role { font-size: 12px; color: var(--ink-3); margin-left: auto; text-align: right; max-width: 56%; }
.grouphint { font-size: 12px; color: var(--ink-3); margin: 0 0 10px; padding-left: 2px; }

/* ---- object-section rows ---- */
.row { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,276px); align-items: center; gap: 14px; padding: 11px 2px; border-bottom: 1px dashed var(--rule); }
.row:last-child { border-bottom: none; }
.rlabel { font-size: 13.5px; color: var(--ink); }
.rlabel small { display: block; font-size: 11.5px; color: var(--ink-3); margin-top: 2px; line-height: 1.4; }
.rctl { justify-self: end; width: 100%; display: flex; justify-content: flex-end; }

/* ---- form controls (reka-ui, restyle by pw-* + data-state) ---- */
.pw-input { font-family: var(--sans); font-size: 13px; color: var(--ink); background: var(--sink); border: 1px solid var(--rule-2); border-radius: var(--r); padding: 8px 12px; width: 100%; max-width: 320px; transition: border-color .15s, box-shadow .15s; }
.pw-input::placeholder { color: var(--ink-3); }
.pw-input:hover { border-color: var(--ink-3); }
.pw-input:focus, .pw-input:focus-visible { outline: none; border-color: var(--focus); box-shadow: 0 0 0 3px color-mix(in srgb, var(--focus) 20%, transparent); }
/* secret 遮罩：type=text + text-security 绕受限 iframe(opaque origin) 对 password 的粘贴门控 */
.pw-secret { -webkit-text-security: disc; }
.pw-switch { position: relative; width: 46px; height: 26px; border-radius: 100px; border: 1px solid var(--rule-2); background: var(--sink); cursor: pointer; padding: 0; flex: 0 0 auto; transition: background .2s, border-color .2s; }
.pw-switch[data-state="checked"] { background: color-mix(in srgb, var(--flux) 28%, var(--sink)); border-color: var(--flux); }
.pw-switch-thumb { display: block; position: absolute; top: 2px; left: 2px; width: 20px; height: 20px; border-radius: 50%; background: var(--ink-3); box-shadow: 0 1px 3px rgba(0,0,0,.28); transition: transform .2s cubic-bezier(.3,1.3,.5,1), background .2s; }
.pw-switch[data-state="checked"] .pw-switch-thumb { transform: translateX(20px); background: var(--flux); }
.pw-switch:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.pw-number { display: inline-flex; align-items: center; border: 1px solid var(--rule-2); border-radius: var(--r); overflow: hidden; background: var(--sink); }
.pw-number-btn { font-size: 16px; line-height: 1; color: var(--ink-2); background: none; border: none; cursor: pointer; width: 32px; height: 36px; flex: 0 0 auto; transition: color .14s, background .14s; }
.pw-number-btn:hover { color: var(--amber); background: color-mix(in srgb, var(--amber) 13%, transparent); }
.pw-number-input { font-family: var(--sans); font-size: 13px; color: var(--ink); width: 66px; text-align: center; font-variant-numeric: tabular-nums; border: none; border-left: 1px solid var(--rule); border-right: 1px solid var(--rule); padding: 8px 4px; background: transparent; }
.pw-number-input:focus, .pw-number-input:focus-visible { outline: none; box-shadow: inset 0 -2px 0 var(--focus); }
.pw-select-trigger { font-family: var(--sans); font-size: 13px; color: var(--ink); background: var(--sink); border: 1px solid var(--rule-2); border-radius: var(--r); padding: 8px 11px; width: 100%; max-width: 200px; display: inline-flex; align-items: center; justify-content: space-between; gap: 8px; cursor: pointer; transition: border-color .15s, box-shadow .15s; }
.pw-select-trigger:hover { border-color: var(--ink-3); }
.pw-select-trigger[data-state="open"] { border-color: var(--focus); box-shadow: 0 0 0 3px color-mix(in srgb, var(--focus) 20%, transparent); }
.pw-select-content { background: var(--card); border: 1px solid var(--rule-2); border-radius: var(--r); padding: 4px; z-index: 30; box-shadow: 0 8px 24px color-mix(in srgb, var(--ink) 20%, transparent); }
.pw-select-item { font-family: var(--sans); font-size: 13px; color: var(--ink); border-radius: 5px; padding: 7px 10px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; gap: 8px; user-select: none; }
.pw-select-item[data-highlighted] { outline: none; background: color-mix(in srgb, var(--focus) 12%, transparent); }
.pw-select-item[data-state="checked"] { color: var(--flux); font-weight: 600; }
.pw-select-item[data-state="checked"]::after { content: "✓"; font-size: 12px; }

/* ---- entry cards ---- */
.card { background: var(--card); border: 1px solid var(--rule); border-radius: var(--r); overflow: hidden; transition: box-shadow .18s, border-color .18s; }
.card + .card { margin-top: 10px; }
.card.editing { border-color: color-mix(in srgb, var(--amber) 55%, var(--rule)); box-shadow: 0 2px 14px color-mix(in srgb, var(--ink) 9%, transparent); }
.card-head { display: flex; align-items: center; gap: 9px; padding: 10px 13px; border-bottom: 1px solid var(--rule); background: linear-gradient(var(--raise), var(--card)); }
.card-head .idx { font-size: 10px; letter-spacing: .16em; color: var(--amber); text-transform: uppercase; flex: 0 0 auto; }
.card-head .nm { font-size: 15px; font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-head .editing-tag { font-size: 12px; font-weight: 400; color: var(--amber); }
.card-head .grow { margin-left: auto; flex: 1 1 auto; }
.hchip { font-size: 10px; letter-spacing: .08em; text-transform: uppercase; padding: 2px 8px; border-radius: 100px; border: 1px solid; flex: 0 0 auto; }
.hchip.on { color: var(--flux); border-color: var(--flux); background: color-mix(in srgb, var(--flux) 10%, transparent); }
.hchip.off { color: var(--ink-3); border-color: var(--rule-2); }
.headbtn { font-size: 12px; border-radius: var(--r); padding: 5px 13px; cursor: pointer; flex: 0 0 auto; transition: background .14s, border-color .14s; }
.edit { color: var(--focus); background: none; border: 1px solid color-mix(in srgb, var(--focus) 45%, transparent); }
.edit:hover { background: color-mix(in srgb, var(--focus) 10%, transparent); }
.del { color: var(--danger); background: none; border: 1px solid color-mix(in srgb, var(--danger) 42%, transparent); padding: 5px 10px; }
.del:hover { background: color-mix(in srgb, var(--danger) 12%, transparent); }
.save-card { color: var(--on-amber); background: var(--amber); border: none; font-weight: 600; box-shadow: 0 1px 0 var(--amber-h); }
.save-card:hover { background: var(--amber-h); }
.cancel-card { color: var(--ink-2); background: none; border: 1px solid var(--rule-2); }
.cancel-card:hover { color: var(--ink); border-color: var(--ink-3); }
.savedflash { animation: sflash 1.9s ease forwards; }
@keyframes sflash { 0%,55% { opacity: 1; } 100% { opacity: 0; } }
.cbody { padding: 3px 15px 9px; }
.crow { display: grid; grid-template-columns: 128px minmax(0,1fr); gap: 16px; align-items: center; padding: 9px 0; border-bottom: 1px dashed var(--rule); }
.crow:last-child { border-bottom: none; }
.ck { font-size: 12.5px; color: var(--ink-2); }
.ck small { display: block; font-size: 11px; color: var(--ink-3); margin-top: 2px; line-height: 1.35; }
.cv { min-width: 0; font-size: 13px; color: var(--ink); word-break: break-word; display: flex; align-items: center; }
.cv .muted { color: var(--ink-3); }
.add { font-size: 13px; color: var(--amber); background: none; border: 1px dashed var(--rule-2); border-radius: var(--r); padding: 9px 14px; cursor: pointer; margin-top: 10px; width: 100%; transition: border-color .14s, background .14s; }
.add:hover { border-color: var(--amber); background: color-mix(in srgb, var(--amber) 7%, transparent); }

/* ---- save bar ---- */
.savebar { display: flex; align-items: center; gap: 14px; margin-top: 8px; padding: 18px 2px 8px; border-top: 1.5px solid var(--ink); position: sticky; bottom: 0; background: linear-gradient(transparent, var(--paper) 26%); }
.commit { font-size: 14px; font-weight: 600; color: var(--on-amber); background: var(--amber); border: none; border-radius: var(--r); padding: 11px 22px; cursor: pointer; box-shadow: 0 1px 0 var(--amber-h); }
.commit:hover { background: var(--amber-h); }
.commit:focus-visible { outline: 2px solid var(--focus); outline-offset: 3px; }
.commit:disabled { opacity: .55; cursor: not-allowed; }
.receipt { font-size: 12px; color: var(--flux); }
.note { font-size: 12px; color: var(--ink-3); margin-left: auto; max-width: 54%; text-align: right; }

/* ---- observatory ---- */
.obs { background: var(--card); border: 1px solid var(--rule); border-radius: var(--r); padding: 14px 16px; display: flex; align-items: center; gap: 14px; }
.obs + .obs { margin-top: 10px; }
.obs .nm { font-size: 16px; font-weight: 600; min-width: 0; }
.obs .read { font-size: 13px; color: var(--ink-2); margin-left: auto; display: flex; gap: 12px; font-variant-numeric: tabular-nums; flex-wrap: wrap; justify-content: flex-end; }
.obs .read b { color: var(--ink); font-weight: 600; }
.chip { font-size: 10.5px; letter-spacing: .12em; text-transform: uppercase; padding: 3px 9px; border-radius: 100px; border: 1px solid; white-space: nowrap; }
.chip.good { color: var(--flux); border-color: var(--flux); background: color-mix(in srgb, var(--flux) 10%, transparent); }
.chip.warn { color: var(--warn); border-color: var(--warn); background: color-mix(in srgb, var(--warn) 10%, transparent); }
.chip.idle { color: var(--ink-3); border-color: var(--rule-2); }
.stint { font-size: 12px; color: var(--ink-3); margin: 0; display: flex; align-items: center; gap: 10px; }

/* ---- states ---- */
.pw-muted { color: var(--ink-3); }
.pw-error { color: var(--danger); font-size: 12px; }
.pw-fatal { padding: 40px 24px; text-align: center; color: var(--danger); display: flex; flex-direction: column; align-items: center; gap: 12px; }
.pw-primary { font-size: 13px; color: var(--on-amber); background: var(--amber); border: none; border-radius: var(--r); padding: 8px 16px; cursor: pointer; }
.pw-primary:hover { background: var(--amber-h); }

@media (max-width: 620px) {
  .layout { flex-direction: column; gap: 14px; }
  .rail { flex-direction: row; position: static; overflow-x: auto; gap: 4px; border-bottom: 1px solid var(--rule); padding-bottom: 8px; top: 0; }
  .rail button { border-left: none; border-bottom: 2px solid transparent; white-space: nowrap; width: auto; border-radius: var(--r) var(--r) 0 0; }
  .rail button[aria-current="true"] { border-left: none; border-bottom-color: var(--focus); }
  .railcap { display: none; } .rail button + .railcap { margin-top: 0; }
  .row { grid-template-columns: 1fr; gap: 8px; } .rctl { justify-self: stretch; justify-content: flex-start; }
  .crow { grid-template-columns: 1fr; gap: 6px; }
  .entry-role, .group-head .c { display: none; } .note { display: none; }
  .obs { flex-wrap: wrap; } .obs .read { margin-left: 0; } .savebar { position: static; }
  .pw-select-trigger { max-width: none; }
}
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
```

- [ ] **Step 2: 构建自检**（CSS 无语法错、单文件产物不破）— Run: `cd frontend && npm run build && npm run verify:bundle`。Expected: build 成功 + verify:bundle PASS（恰 1 JS / ≤1 CSS / 无 import()）。
- [ ] **Step 3: 全测试基线**（确认 CSS 重写未破任何测试）— Run: `cd frontend && npm run test:run`。Expected: 现有测试仍按各自现状（Field/ServerCard/HeaderCard/App/SettingsPanel 仍是旧模板，尚未改；本步只验证 CSS 替换本身不引入测试失败——旧类名被删但测试多按 role/pw-secret/pw-save 断言，可能出现红。**若红仅限后续任务将改写的 App/SettingsPanel/ServerCard/HeaderCard，属预期**，记录待后续任务转绿）。
- [ ] **Step 4: 提交** — `git add frontend/src/styles/tokens.css && git commit -m "style(fe): tokens.css 整体重写为分章观测台设计系统（亮草甸/暗黑灰 + 样式化 reka-ui 控件）"`

> **给实现者**：Task 3 只换 CSS，后续 4–10 逐个把组件模板迁到新类名后测试才会全绿。本任务的验收是 build + verify:bundle 通过、且 CSS 语法无误；不要求此刻全测试绿。

---

### Task 4: Field.vue 降为纯控件

**Files:**
- Modify: `frontend/src/components/Field.vue`
- Modify: `frontend/src/components/Field.test.ts`

**Interfaces:**
- Consumes: `FieldSpec`（Task 2）。
- Produces: `<Field :spec :model-value @update:model-value>` 渲染**单个控件根节点**（enum→SelectRoot / bool→SwitchRoot / int·float→NumberFieldRoot / else→input.pw-input），**不再自渲 label**。角色/emit 契约不变（I5）。

- [ ] **Step 1: 改 `Field.test.ts`**——删掉 enum 用例第 33 行 `expect(w.text()).toContain('模式')`，其余全留：

```ts
  it('enum：渲染 SelectTrigger 离散节点（而非裸子串）', () => {
    const w = mountField({ key: 'mode', type: 'enum', label: '模式', default: 'a', options: ['a', 'b', 'c'] }, 'a')
    const triggers = w.findAll('[role="combobox"]')
    expect(triggers).toHaveLength(1)
    expect(triggers[0].attributes('aria-label')).toBe('mode')
    expect(triggers[0].element.tagName).toBe('BUTTON')
    expect(w.find('input[type="text"]').exists()).toBe(false)
  })
```
（string / bool / int 三个用例一字不改。）

- [ ] **Step 2: 改 `Field.vue` 模板为纯控件**（`<script setup>` 保持不变，仅去掉 `.pw-field` 外层与 `<label>`）：

```vue
<template>
  <SelectRoot v-if="spec.type === 'enum'" v-model="strVal">
    <SelectTrigger class="pw-select-trigger" :aria-label="spec.key"><SelectValue /></SelectTrigger>
    <SelectContent class="pw-select-content">
      <SelectViewport>
        <SelectItem v-for="opt in spec.options" :key="opt" :value="opt" class="pw-select-item">
          <SelectItemText>{{ opt }}</SelectItemText>
        </SelectItem>
      </SelectViewport>
    </SelectContent>
  </SelectRoot>

  <SwitchRoot v-else-if="spec.type === 'bool'" v-model="boolVal" class="pw-switch">
    <SwitchThumb class="pw-switch-thumb" />
  </SwitchRoot>

  <NumberFieldRoot v-else-if="spec.type === 'int' || spec.type === 'float'" v-model="numVal"
    :step="spec.type === 'float' ? 0.01 : 1" class="pw-number">
    <NumberFieldDecrement class="pw-number-btn">−</NumberFieldDecrement>
    <NumberFieldInput class="pw-number-input" />
    <NumberFieldIncrement class="pw-number-btn">+</NumberFieldIncrement>
  </NumberFieldRoot>

  <input v-else class="pw-input" type="text" v-model.trim="strVal" />
</template>
```

- [ ] **Step 3: 跑 Field 测试** — Run: `cd frontend && npm run test:run -- Field`。Expected: PASS（4 用例全绿）。
- [ ] **Step 4: typecheck** — Run: `cd frontend && npm run typecheck`。Expected: PASS。
- [ ] **Step 5: 提交** — `git add frontend/src/components/Field.vue frontend/src/components/Field.test.ts && git commit -m "refactor(fe): Field 降为纯控件，label/hint 归父级网格（角色/emit 契约不变）"`

---

### Task 5: SectionForm.vue 换 .entry/.row 排布

**Files:**
- Modify: `frontend/src/components/SectionForm.vue`

**Interfaces:**
- Consumes: `<Field>`（Task 4）、`ObjectSection`（含 subtitle/hint）。
- props/emits **不变**：`{ section: ObjectSection; modelValue: Record<string,unknown> }` / `update:modelValue`（合并后整节值）。

- [ ] **Step 1: 确认 SectionForm.test 基线语义** — 测试断言 `section.title` 文本 + 每个 `f.label` 文本 + `findAll('[role="switch"]')[2]` = guilds_bases。新排布须保留这三点。

- [ ] **Step 2: 改 `SectionForm.vue`**：

```vue
<script setup lang="ts">
import Field from './Field.vue'
import type { ObjectSection } from '../lib/schema'

const props = defineProps<{ section: ObjectSection; modelValue: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:modelValue': [v: Record<string, unknown>] }>()
const update = (key: string, v: unknown) => emit('update:modelValue', { ...props.modelValue, [key]: v })
</script>

<template>
  <section class="entry">
    <div class="entry-head">
      <span class="entry-title">{{ section.title }}</span>
      <span v-if="section.subtitle" class="entry-role">{{ section.subtitle }}</span>
    </div>
    <div v-for="f in section.fields" :key="f.key" class="row">
      <span class="rlabel">{{ f.label }}<small v-if="f.hint">{{ f.hint }}</small></span>
      <span class="rctl">
        <Field :spec="f" :model-value="modelValue[f.key]" @update:model-value="(v) => update(f.key, v)" />
      </span>
    </div>
  </section>
</template>
```

- [ ] **Step 3: 跑 SectionForm 测试** — Run: `cd frontend && npm run test:run -- SectionForm`。Expected: PASS（title/labels/role=switch[2] 都在）。
- [ ] **Step 4: 提交** — `git add frontend/src/components/SectionForm.vue && git commit -m "refactor(fe): SectionForm 换 .entry/.row 排布 + 渲染节副标题与字段提示"`

---

### Task 6: ServerCard.vue 查看↔编辑两态

**Files:**
- Modify: `frontend/src/components/ServerCard.vue`
- Modify: `frontend/src/components/ServerCard.test.ts`

**Interfaces:**
- Consumes: `<Field>`、`SERVER_FIELDS`。
- props: `{ modelValue: Record<string,unknown>; indexLabel: string }`。
- emits: `{ 'update:modelValue': [v: Record<string,unknown>]; delete: []; save: [done: (ok: boolean) => void] }`。
- **secret 判据读 `password_set`**；secret 输入非受控、`type=text`、`.pw-secret` 类、不回显。

- [ ] **Step 1: 改写 `ServerCard.test.ts`**（两态 + secret 判据正向锁定）：

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ServerCard from './ServerCard.vue'

const row = () => ({ __row_id: 'srv-0', name: 'a', enabled: true, base_url: 'http://x', username: 'admin',
  password: '', password_set: true, password_env: '', timeout: 10, verify_tls: true, timezone: '' })
const mountCard = (mv: Record<string, unknown>) => mount(ServerCard, { props: { modelValue: mv, indexLabel: '源 01' } })

describe('ServerCard', () => {
  it('查看态：password_set=true 显「已设置」，有修改/移除按钮', () => {
    const w = mountCard(row())
    expect(w.text()).toContain('已设置')
    expect(w.get('button.edit')).toBeTruthy()
    expect(w.get('button.del')).toBeTruthy()
    // 查看态不渲染 secret 输入
    expect(w.find('input.pw-secret').exists()).toBe(false)
  })
  it('查看态：password_set=false 不显「已设置」', () => {
    const w = mountCard({ ...row(), password_set: false })
    expect(w.text()).not.toContain('密码')
  })
  it('进编辑态：secret 用 text+text-security、不预填、占位显示已设置', async () => {
    const w = mountCard(row())
    await w.get('button.edit').trigger('click')
    const pw = w.get('input.pw-secret')
    expect(pw.attributes('type')).toBe('text')
    expect((pw.element as HTMLInputElement).value).toBe('')
    expect(pw.attributes('placeholder')).toContain('已设置')
  })
  it('即便上游传入非空 secret 也绝不回显（进编辑态后仍空）', async () => {
    const w = mountCard({ ...row(), password: 'p@ss' })
    await w.get('button.edit').trigger('click')
    expect((w.get('input.pw-secret').element as HTMLInputElement).value).toBe('')
  })
  it('移除按钮 emit delete', async () => {
    const w = mountCard(row())
    await w.get('button.del').trigger('click')
    expect(w.emitted('delete')).toBeTruthy()
  })
  it('编辑态改名后保存：emit 合并行(__row_id 保留) + emit save', async () => {
    const w = mountCard(row())
    await w.get('button.edit').trigger('click')
    await w.get('input.pw-input[type="text"]').setValue('beta') // name 字段（第一个文本输入）
    await w.get('button.save-card').trigger('click')
    const merged = w.emitted('update:modelValue')?.at(-1)?.[0] as Record<string, unknown>
    expect(merged.name).toBe('beta')
    expect(merged.__row_id).toBe('srv-0')
    expect(w.emitted('save')).toBeTruthy()
  })
  it('新增行(无 __row_id) 初始即编辑态', () => {
    const w = mountCard({ __row_id: '', name: '', enabled: true, base_url: '', username: '', password: '', password_env: '', timeout: 10, verify_tls: true, timezone: '' })
    expect(w.find('button.save-card').exists()).toBe(true)
  })
})
```

> 注：`input.pw-input[type="text"]` 选第一个文本输入=name（enabled 是 switch、base_url/username 也是文本，但 setValue 命中第一个 `.pw-input[type=text]`=name，因 name 是 SERVER_FIELDS 首个 string 字段）。若选择器命中多个，`w.get` 会抛——用 `w.findAll('input.pw-input[type=\"text\"]')[0]`。实现者按实际渲染顺序取 name 输入。

- [ ] **Step 2: 跑测试确认失败** — Run: `cd frontend && npm run test:run -- ServerCard`。Expected: FAIL（现为永远编辑态、无 .edit/.del/两态）。

- [ ] **Step 3: 改 `ServerCard.vue`** 为两态：

```vue
<script setup lang="ts">
import { ref, reactive } from 'vue'
import Field from './Field.vue'
import { SERVER_FIELDS } from '../lib/schema'

const props = defineProps<{ modelValue: Record<string, unknown>; indexLabel: string }>()
const emit = defineEmits<{
  'update:modelValue': [v: Record<string, unknown>]
  delete: []
  save: [done: (ok: boolean) => void]
}>()

const mode = ref<'view' | 'edit'>(props.modelValue.__row_id ? 'view' : 'edit')
const draft = reactive<Record<string, unknown>>({})
const flash = ref(false)

function enterEdit() {
  for (const k of Object.keys(draft)) delete draft[k]
  Object.assign(draft, props.modelValue)
  for (const f of SERVER_FIELDS) if (f.secret) draft[f.key] = '' // secret 不回填明文
  mode.value = 'edit'
}
function cancel() { mode.value = 'view' }
function setDraft(key: string, v: unknown) { draft[key] = v }
function saveCard() {
  emit('update:modelValue', { ...props.modelValue, ...draft })
  emit('save', (ok: boolean) => {
    if (!ok) return // 失败留在编辑态，父已 toast 错误（flash 不触发）
    mode.value = 'view'
    flash.value = true
    setTimeout(() => { flash.value = false }, 1900)
  })
}
</script>

<template>
  <!-- 查看态 -->
  <div v-if="mode === 'view'" class="card">
    <div class="card-head">
      <span class="idx">{{ indexLabel }}</span>
      <span class="nm">{{ (modelValue.name as string) || '（未命名）' }}</span>
      <span class="hchip" :class="modelValue.enabled ? 'on' : 'off'">{{ modelValue.enabled ? '启用' : '停用' }}</span>
      <span class="grow"></span>
      <span v-if="flash" class="hchip on savedflash">已保存 ✓</span>
      <button class="headbtn del" @click="emit('delete')">移除</button>
      <button class="headbtn edit" @click="enterEdit">修改</button>
    </div>
    <div class="cbody">
      <div class="crow"><span class="ck">地址</span><span class="cv">{{ modelValue.base_url }}</span></div>
      <div class="crow"><span class="ck">用户名</span><span class="cv">{{ modelValue.username }}</span></div>
      <div v-if="modelValue.password_set" class="crow"><span class="ck">密码</span><span class="cv"><span class="muted">已设置</span></span></div>
      <div v-if="modelValue.password_env" class="crow"><span class="ck">密码变量</span><span class="cv">{{ modelValue.password_env }}</span></div>
      <div class="crow"><span class="ck">超时</span><span class="cv">{{ modelValue.timeout }} 秒</span></div>
      <div class="crow"><span class="ck">校验 TLS</span><span class="cv">{{ modelValue.verify_tls ? '是' : '否' }}</span></div>
      <div v-if="modelValue.timezone" class="crow"><span class="ck">时区</span><span class="cv">{{ modelValue.timezone }}</span></div>
    </div>
  </div>

  <!-- 编辑态 -->
  <div v-else class="card editing">
    <div class="card-head">
      <span class="idx">{{ indexLabel }}</span>
      <span class="editing-tag">编辑</span>
      <span class="grow"></span>
      <button class="headbtn cancel-card" @click="cancel">取消</button>
      <button class="headbtn save-card" @click="saveCard">保存</button>
    </div>
    <div class="cbody">
      <template v-for="f in SERVER_FIELDS" :key="f.key">
        <div class="crow">
          <span class="ck">{{ f.label }}<small v-if="f.hint">{{ f.hint }}</small></span>
          <span class="cv">
            <input v-if="f.secret" class="pw-input pw-secret" type="text"
              autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false"
              :placeholder="modelValue.password_set ? '已设置（留空保持不变）' : '未设置'"
              @input="setDraft(f.key, ($event.target as HTMLInputElement).value)" />
            <Field v-else :spec="f" :model-value="draft[f.key]" @update:model-value="(v) => setDraft(f.key, v)" />
          </span>
        </div>
      </template>
    </div>
  </div>
</template>
```

- [ ] **Step 4: 跑测试确认通过** — Run: `cd frontend && npm run test:run -- ServerCard` 与 `npm run typecheck`。Expected: PASS。
- [ ] **Step 5: 提交** — `git add frontend/src/components/ServerCard.vue frontend/src/components/ServerCard.test.ts && git commit -m "feat(fe): ServerCard 查看↔编辑两态（secret 判据读 password_set、保存即落库联动）"`

---

### Task 7: HeaderCard.vue 查看↔编辑两态

**Files:**
- Modify: `frontend/src/components/HeaderCard.vue`
- Modify: `frontend/src/components/HeaderCard.test.ts`

**Interfaces:** 同 ServerCard，但用 `HEADER_FIELDS`、secret 判据读 **`value_set`**。props/emits 签名同 Task 6。

- [ ] **Step 1: 改写 `HeaderCard.test.ts`**：

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HeaderCard from './HeaderCard.vue'

const row = () => ({ __row_id: 'hdr-0', name: 'X-Api-Key', value: '', value_set: true, value_env: '', servers: '' })
const mountCard = (mv: Record<string, unknown>) => mount(HeaderCard, { props: { modelValue: mv, indexLabel: '头 01' } })

describe('HeaderCard', () => {
  it('查看态：value_set=true 显「已设置」，有修改/移除', () => {
    const w = mountCard(row())
    expect(w.text()).toContain('已设置')
    expect(w.get('button.edit')).toBeTruthy()
    expect(w.get('button.del')).toBeTruthy()
    expect(w.find('input.pw-secret').exists()).toBe(false)
  })
  it('查看态：value_set=false 且无 value_env 显「未设置」', () => {
    const w = mountCard({ ...row(), value_set: false })
    expect(w.text()).toContain('未设置')
  })
  it('进编辑态：secret 用 text+text-security、不预填、占位显示已设置', async () => {
    const w = mountCard(row())
    await w.get('button.edit').trigger('click')
    const pw = w.get('input.pw-secret')
    expect(pw.attributes('type')).toBe('text')
    expect((pw.element as HTMLInputElement).value).toBe('')
    expect(pw.attributes('placeholder')).toContain('已设置')
  })
  it('即便上游传入非空 secret 也绝不回显', async () => {
    const w = mountCard({ ...row(), value: 'secret' })
    await w.get('button.edit').trigger('click')
    expect((w.get('input.pw-secret').element as HTMLInputElement).value).toBe('')
  })
  it('移除按钮 emit delete', async () => {
    const w = mountCard(row())
    await w.get('button.del').trigger('click')
    expect(w.emitted('delete')).toBeTruthy()
  })
  it('编辑态改名后保存：emit 合并行(__row_id 保留) + emit save', async () => {
    const w = mountCard(row())
    await w.get('button.edit').trigger('click')
    await w.findAll('input.pw-input[type="text"]')[0].setValue('X-Renamed') // name
    await w.get('button.save-card').trigger('click')
    const merged = w.emitted('update:modelValue')?.at(-1)?.[0] as Record<string, unknown>
    expect(merged.name).toBe('X-Renamed')
    expect(merged.__row_id).toBe('hdr-0')
    expect(w.emitted('save')).toBeTruthy()
  })
})
```

- [ ] **Step 2: 跑测试确认失败** — Run: `cd frontend && npm run test:run -- HeaderCard`。Expected: FAIL。

- [ ] **Step 3: 改 `HeaderCard.vue`**（结构同 ServerCard，替换字段集与判据键）：

```vue
<script setup lang="ts">
import { ref, reactive } from 'vue'
import Field from './Field.vue'
import { HEADER_FIELDS } from '../lib/schema'

const props = defineProps<{ modelValue: Record<string, unknown>; indexLabel: string }>()
const emit = defineEmits<{
  'update:modelValue': [v: Record<string, unknown>]
  delete: []
  save: [done: (ok: boolean) => void]
}>()

const mode = ref<'view' | 'edit'>(props.modelValue.__row_id ? 'view' : 'edit')
const draft = reactive<Record<string, unknown>>({})
const flash = ref(false)

function enterEdit() {
  for (const k of Object.keys(draft)) delete draft[k]
  Object.assign(draft, props.modelValue)
  for (const f of HEADER_FIELDS) if (f.secret) draft[f.key] = ''
  mode.value = 'edit'
}
function cancel() { mode.value = 'view' }
function setDraft(key: string, v: unknown) { draft[key] = v }
function saveCard() {
  emit('update:modelValue', { ...props.modelValue, ...draft })
  emit('save', (ok: boolean) => {
    if (!ok) return
    mode.value = 'view'
    flash.value = true
    setTimeout(() => { flash.value = false }, 1900)
  })
}
</script>

<template>
  <div v-if="mode === 'view'" class="card">
    <div class="card-head">
      <span class="idx">{{ indexLabel }}</span>
      <span class="nm">{{ (modelValue.name as string) || '（未命名）' }}</span>
      <span class="grow"></span>
      <span v-if="flash" class="hchip on savedflash">已保存 ✓</span>
      <button class="headbtn del" @click="emit('delete')">移除</button>
      <button class="headbtn edit" @click="enterEdit">修改</button>
    </div>
    <div class="cbody">
      <div class="crow"><span class="ck">值</span><span class="cv">
        <span class="muted">{{ modelValue.value_set ? '已设置' : (modelValue.value_env ? '用环境变量' : '未设置') }}</span>
      </span></div>
      <div v-if="modelValue.value_env" class="crow"><span class="ck">值变量</span><span class="cv">{{ modelValue.value_env }}</span></div>
      <div class="crow"><span class="ck">作用域</span><span class="cv">
        <template v-if="modelValue.servers">限定 {{ modelValue.servers }}</template>
        <span v-else class="muted">所有服务器</span>
      </span></div>
    </div>
  </div>

  <div v-else class="card editing">
    <div class="card-head">
      <span class="idx">{{ indexLabel }}</span>
      <span class="editing-tag">编辑</span>
      <span class="grow"></span>
      <button class="headbtn cancel-card" @click="cancel">取消</button>
      <button class="headbtn save-card" @click="saveCard">保存</button>
    </div>
    <div class="cbody">
      <template v-for="f in HEADER_FIELDS" :key="f.key">
        <div class="crow">
          <span class="ck">{{ f.label }}<small v-if="f.hint">{{ f.hint }}</small></span>
          <span class="cv">
            <input v-if="f.secret" class="pw-input pw-secret" type="text"
              autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false"
              :placeholder="modelValue.value_set ? '已设置（留空保持不变）' : '未设置'"
              @input="setDraft(f.key, ($event.target as HTMLInputElement).value)" />
            <Field v-else :spec="f" :model-value="draft[f.key]" @update:model-value="(v) => setDraft(f.key, v)" />
          </span>
        </div>
      </template>
    </div>
  </div>
</template>
```

- [ ] **Step 4: 跑测试确认通过** — Run: `cd frontend && npm run test:run -- HeaderCard` 与 `npm run typecheck`。Expected: PASS。
- [ ] **Step 5: 提交** — `git add frontend/src/components/HeaderCard.vue frontend/src/components/HeaderCard.test.ts && git commit -m "feat(fe): HeaderCard 查看↔编辑两态（secret 判据读 value_set）"`

---

### Task 8: StatusPanel.vue 观测卡外观

**Files:**
- Modify: `frontend/src/components/StatusPanel.vue`

**Interfaces:**
- `<script setup>` **逻辑全不动**（state/rows/restarting/timer/load/onMounted/onUnmounted）；仅换模板为观测卡。
- **保留文本锚点**：`在线 {online}`、`{smoothness_label}`、`正在重载`、`读取状态失败`、`刷新`。**只渲染 StatusResp 字段**，不引入 demo 的 fps 数值/天数/授权文案。

- [ ] **Step 1: 确认 StatusPanel.test 基线** — 断言 `alpha`、`在线 3`、`流畅`、`正在重载`、`读取状态失败`。改模板须保这五点。

- [ ] **Step 2: 改 `StatusPanel.vue` 模板**（script 段一字不改，只替换 `<template>`）：

```vue
<template>
  <div class="pw-status">
    <div class="chapter-head"><h2>观测台</h2></div>
    <p class="stint"><span>数据源实时状态</span><button class="ghost" @click="load">刷新</button></p>
    <p v-if="state === 'loading'" class="pw-muted">加载中…</p>
    <p v-else-if="state === 'error'" class="pw-error">读取状态失败，请重试</p>
    <template v-else>
      <p v-if="restarting" class="pw-muted">插件正在重载配置…</p>
      <div v-for="row in rows" :key="row.name" class="obs">
        <span class="nm">{{ row.name }}</span>
        <span v-if="!row.ready" class="chip idle">未就绪</span>
        <span v-else-if="row.degraded" class="chip warn">数据缺失</span>
        <span v-else class="chip good">就绪</span>
        <span class="read">
          <template v-if="row.ready"><b>在线 {{ row.online }}</b><span>·</span><span>{{ row.smoothness_label }}</span></template>
          <span v-else>未就绪</span>
        </span>
      </div>
    </template>
  </div>
</template>
```

- [ ] **Step 3: 跑 StatusPanel 测试** — Run: `cd frontend && npm run test:run -- StatusPanel`。Expected: PASS（五锚点全在）。
- [ ] **Step 4: 提交** — `git add frontend/src/components/StatusPanel.vue && git commit -m "style(fe): StatusPanel 换观测卡外观（只渲染 StatusResp 字段、保文案锚点）"`

---

### Task 9: SettingsPanel.vue 分章渲染 + 卡片保存联动

**Files:**
- Modify: `frontend/src/components/SettingsPanel.vue`
- Modify: `frontend/src/components/SettingsPanel.test.ts`

**Interfaces:**
- Consumes: `CHAPTERS`（Task 1）、`ServerCard`/`HeaderCard`（含 `save` emit、`indexLabel` prop）、`SectionForm`。
- props: `{ chapter: string }`。
- **保留**：`state`/`load`/`save`/`ERR`/`mapError`/`emptyRow`/`collectBody`；`collectBody` 始终全 8 节。
- **新增**：`save(opts?: { silent?: boolean; done?: (ok:boolean)=>void })`；`chapterMeta`/`currentSections`/`isAccess`/`pad`。

- [ ] **Step 1: 改写 `SettingsPanel.test.ts`**（分章 + 保留契约断言）：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SettingsPanel from './SettingsPanel.vue'

const cfg = () => ({ ok: true, config: {
  servers: [{ __row_id: 'srv-0', name: 'a', enabled: true, base_url: 'http://x', username: 'admin',
    password: '', password_set: true, password_env: '', timeout: 10, verify_tls: true, timezone: '' }],
  custom_headers: [],
  routing: { access_mode: 'restricted', default_server: '' },
  polling: { metrics_seconds: 30, players_seconds: 30, info_seconds: 600, settings_seconds: 1800,
    game_data_seconds: 120, jitter_ratio: 0.1, max_concurrency: 6 },
  world: { timezone: 'Asia/Tokyo', locale: 'zh-CN', fps_smooth: 50, fps_moderate: 35, fps_laggy: 20 },
  bases: { enabled: true, assignment_radius: 5000, ambiguity_ratio: 0.2, confirmation_samples: 3, position_grid_size: 2000, z_weight: 0.5 },
  privacy: { mode: 'balanced', public_exact_ping: false, public_positions: false, ping_good_ms: 60, ping_ok_ms: 120, uncertain_timeout: 900 },
  history: { raw_metrics_days: 7, aggregate_days: 90, session_days: 365, observation_days: 180 },
  features: { report: true, events: true, guilds_bases: false, players: false },
  players: { rank_top_n: 5, exclude_names: '' },
}, page_version: 1 })

beforeEach(() => {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn() }
})
const mountAt = (chapter: string) => mount(SettingsPanel, { props: { chapter } })

describe('SettingsPanel', () => {
  it('feature 章渲染功能分组与玩家个体节', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg())
    const w = mountAt('feature'); await flushPromises()
    expect(w.text()).toContain('功能分组开关')
    expect(w.text()).toContain('玩家个体')
  })
  it('access 章渲染路由节 + 保存条', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg())
    const w = mountAt('access'); await flushPromises()
    expect(w.text()).toContain('路由与访问控制')
    expect(w.text()).toContain('保存本页设置')
    expect(w.get('button.pw-save')).toBeTruthy()
  })
  it('config/get unauthorized → 整块错误态，不白屏', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue({ ok: false, error: 'unauthorized', detail: {} })
    const w = mountAt('access'); await flushPromises()
    expect(w.text()).toContain('未登录')
  })
  it('保存 apiPost body 不含 group_bindings 且类型正确（body 恒全量，与当前章无关）', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg());
    (window.AstrBotPluginPage!.apiPost as any).mockResolvedValue({ ok: true, warnings: {} })
    const w = mountAt('access'); await flushPromises()
    await w.get('button.pw-save').trigger('click'); await flushPromises()
    const [, body] = (window.AstrBotPluginPage!.apiPost as any).mock.calls[0]
    expect('group_bindings' in body).toBe(false)
    expect(typeof body.polling.metrics_seconds).toBe('number')
    expect(typeof body.features.report).toBe('boolean')
  })
  it('保存业务错误 credential_redirect → 就地提示，不塌整页', async () => {
    (window.AstrBotPluginPage!.apiGet as any).mockResolvedValue(cfg());
    (window.AstrBotPluginPage!.apiPost as any).mockResolvedValue({ ok: false, error: 'credential_redirect', detail: { path: 'servers[0].password' } })
    const w = mountAt('access'); await flushPromises()
    await w.get('button.pw-save').trigger('click'); await flushPromises()
    expect(w.text()).toContain('请重新输入该服务器密码')
    expect(w.text()).toContain('保存本页设置') // 表单/保存条仍在（未塌成整页错误）
  })
})
```

- [ ] **Step 2: 跑测试确认失败** — Run: `cd frontend && npm run test:run -- SettingsPanel`。Expected: FAIL（无 chapter prop、旧平铺结构）。

- [ ] **Step 3: 改 `SettingsPanel.vue`**：

```vue
<script setup lang="ts">
import { reactive, ref, onMounted, computed } from 'vue'
import { apiGet, apiPost } from '../lib/bridge'
import { Unauthorized, BusinessError } from '../lib/errors'
import { collectBody, type SettingsState } from '../lib/collect'
import { OBJECT_SECTIONS, SERVER_FIELDS, HEADER_FIELDS } from '../lib/schema'
import { CHAPTERS } from '../lib/chapters'
import ServerCard from './ServerCard.vue'
import HeaderCard from './HeaderCard.vue'
import SectionForm from './SectionForm.vue'

const props = defineProps<{ chapter: string }>()

const phase = ref<'loading' | 'error' | 'ready'>('loading')
const fatalMsg = ref('')
const saving = ref(false)
const notice = reactive<{ msg: string; error: boolean }>({ msg: '', error: false })
const state = reactive<SettingsState>({ servers: [], custom_headers: [], sections: {} })

const chapterMeta = computed(() => CHAPTERS.find((c) => c.id === props.chapter))
const chapterTitle = computed(() => chapterMeta.value?.label ?? '')
const currentSections = computed(() => OBJECT_SECTIONS.filter((s) => chapterMeta.value?.blocks?.includes(s.key)))
const isAccess = computed(() => props.chapter === 'access')

const ERR: Record<string, string> = {
  save_in_progress: '保存进行中，请稍候', too_frequent: '保存过于频繁，请稍候再试',
  too_large: '配置过大', invalid_shape: '配置结构不合法', invalid_field: '字段不合法',
  credential_redirect: '修改了服务器地址，请重新输入该服务器密码',
  restart_failed_rolled_back: '重载失败，已回滚到旧配置',
  restart_failed: '重载失败且回滚失败，请检查后台', unauthorized: '未登录或登录已过期',
}
const mapError = (e: BusinessError) => (ERR[e.code] ?? '保存失败') + (e.path ? `：${e.path}` : '')

function emptyRow(fields: typeof SERVER_FIELDS): Record<string, unknown> {
  const row: Record<string, unknown> = { __row_id: '' }
  for (const f of fields) row[f.key] = f.default
  return row
}
function pad(n: number) { return n < 10 ? '0' + n : '' + n }

async function load() {
  phase.value = 'loading'
  try {
    const r = await apiGet<{ config: Record<string, any> }>('config/get')
    const c = r.config
    state.servers = (c.servers ?? []).map((s: Record<string, unknown>) => ({ ...s }))
    state.custom_headers = (c.custom_headers ?? []).map((h: Record<string, unknown>) => ({ ...h }))
    state.sections = {}
    for (const sec of OBJECT_SECTIONS) state.sections[sec.key] = { ...(c[sec.key] ?? {}) }
    phase.value = 'ready'
  } catch (e) {
    fatalMsg.value = e instanceof Unauthorized ? '未登录或登录已过期，请重新登录 Dashboard' : '读取配置失败，请重试'
    phase.value = 'error'
  }
}
onMounted(load)

function toast(msg: string, error = false) {
  notice.msg = msg; notice.error = error
  setTimeout(() => { if (notice.msg === msg) { notice.msg = ''; notice.error = false } }, 3000)
}

async function save(opts: { silent?: boolean; done?: (ok: boolean) => void } = {}) {
  if (saving.value) { opts.done?.(false); return }
  saving.value = true; notice.msg = ''; notice.error = false
  try {
    const res = await apiPost<{ ok: boolean; warnings?: Record<string, unknown[]> }>('config/save', collectBody(state))
    const w = res.warnings ?? {}
    const skips = [...((w.skipped_servers as unknown[]) ?? []), ...((w.skipped_headers as unknown[]) ?? [])]
    if (skips.length) toast(`已保存（${skips.length} 条被跳过）`)
    else if (!opts.silent) toast('已保存并重载')
    opts.done?.(true)
  } catch (e) {
    if (e instanceof BusinessError) toast(mapError(e), true)
    else if (e instanceof Unauthorized) toast('未登录或登录已过期', true)
    else if (e instanceof Error) toast(e.message.includes('__unchanged__') ? e.message : '保存失败', true)
    else toast('保存失败', true)
    opts.done?.(false)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="pw-settings">
    <p v-if="phase === 'loading'" class="pw-muted">加载中…</p>
    <div v-else-if="phase === 'error'" class="pw-fatal">{{ fatalMsg }}<button class="pw-primary" @click="load">重试</button></div>
    <template v-else>
      <div class="chapter-head"><h2>{{ chapterTitle }}</h2></div>

      <template v-if="isAccess">
        <section>
          <div class="group-head"><span class="t">数据源</span><span class="c">要观测的 Palworld 服务器</span></div>
          <ServerCard v-for="(s, i) in state.servers" :key="(s.__row_id as string) || i" :model-value="s" :index-label="'源 ' + pad(i + 1)"
            @update:model-value="(v) => state.servers[i] = v" @delete="state.servers.splice(i, 1)" @save="(done) => save({ silent: true, done })" />
          <button class="add" @click="state.servers.push(emptyRow(SERVER_FIELDS))">＋ 添加数据源</button>
        </section>
        <section>
          <div class="group-head"><span class="t">自定义请求头</span><span class="c">每次请求都会带上</span></div>
          <p class="grouphint">带凭证的请求头，记得用「限定服务器」缩小范围——留空会发给所有服务器（含以后新增的）。</p>
          <HeaderCard v-for="(h, i) in state.custom_headers" :key="(h.__row_id as string) || i" :model-value="h" :index-label="'头 ' + pad(i + 1)"
            @update:model-value="(v) => state.custom_headers[i] = v" @delete="state.custom_headers.splice(i, 1)" @save="(done) => save({ silent: true, done })" />
          <button class="add" @click="state.custom_headers.push(emptyRow(HEADER_FIELDS))">＋ 添加请求头</button>
        </section>
      </template>

      <SectionForm v-for="sec in currentSections" :key="sec.key" :section="sec"
        :model-value="state.sections[sec.key]" @update:model-value="(v) => state.sections[sec.key] = v" />

      <div class="savebar">
        <button class="commit pw-save" :disabled="saving" @click="() => save()">{{ saving ? '保存中…' : '保存本页设置' }}</button>
        <span v-if="notice.msg" :class="notice.error ? 'pw-error' : 'receipt'">{{ notice.msg }}</span>
        <span class="note">数据源、请求头点各自的「保存」即生效；这里保存本页其余设置</span>
      </div>
    </template>
  </div>
</template>
```

- [ ] **Step 4: 跑测试确认通过** — Run: `cd frontend && npm run test:run -- SettingsPanel` 与 `npm run typecheck`。Expected: PASS。
- [ ] **Step 5: 提交** — `git add frontend/src/components/SettingsPanel.vue frontend/src/components/SettingsPanel.test.ts && git commit -m "feat(fe): SettingsPanel 分章渲染 + 卡片保存即落库联动（collectBody 恒全量）"`

---

### Task 10: App.vue 报头 + 左索引 rail + 主题切换 + 章节路由

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/App.test.ts`

**Interfaces:**
- Consumes: `SettingsPanel`（:chapter）、`StatusPanel`、`CHAPTERS`/`DEFAULT_CHAPTER`。
- 挂载策略：`SettingsPanel v-show="chapter!=='status'"`（常挂）、`StatusPanel v-if="chapter==='status'"`。
- 主题：`data-theme` 写 documentElement，localStorage 全 try/catch。错误边界 `onErrorCaptured` 保留。

- [ ] **Step 1: 改写 `App.test.ts`**：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import App from './App.vue'

beforeEach(() => {
  window.AstrBotPluginPage = {
    ready: () => Promise.resolve(),
    apiGet: vi.fn().mockResolvedValue({ ok: true, config: {}, servers: [] }),
    apiPost: vi.fn().mockResolvedValue({ ok: true }),
  }
})

describe('App', () => {
  it('默认渲染报头与左索引，可切到观测台', async () => {
    const w = mount(App); await flushPromises()
    expect(w.text()).toContain('帕鲁纪事')
    const rail = w.findAll('.rail button')
    expect(rail.some((b) => b.text().includes('观测台'))).toBe(true)
    expect(rail.some((b) => b.text().includes('接入'))).toBe(true)
    const obs = rail.find((b) => b.text().includes('观测台'))!
    await obs.trigger('click'); await flushPromises()
    expect(w.text()).toContain('刷新') // 进入 StatusPanel
  })
  it('子组件抛错 → 错误边界兜底，不白屏', async () => {
    const Boom = { setup() { throw new Error('boom-child') }, template: '<div/>' }
    const w = mount(App, { global: { stubs: { SettingsPanel: Boom } } })
    await flushPromises()
    expect(w.text()).toContain('boom-child')
  })
})
```

- [ ] **Step 2: 跑测试确认失败** — Run: `cd frontend && npm run test:run -- App`。Expected: FAIL（现为 pw-tabs 两 tab）。

- [ ] **Step 3: 改 `App.vue`**：

```vue
<script setup lang="ts">
import { ref, watchEffect, onErrorCaptured } from 'vue'
import SettingsPanel from './components/SettingsPanel.vue'
import StatusPanel from './components/StatusPanel.vue'
import { CHAPTERS, DEFAULT_CHAPTER } from './lib/chapters'

const chapter = ref(DEFAULT_CHAPTER)
const fatal = ref('')
onErrorCaptured((err) => { fatal.value = (err as Error)?.message || '页面发生错误'; return false })

const THEME_KEY = 'palchronicle-theme'
function readStored(): 'light' | 'dark' | null {
  try { const v = localStorage.getItem(THEME_KEY); return v === 'light' || v === 'dark' ? v : null } catch { return null }
}
function writeStored(v: 'light' | 'dark') { try { localStorage.setItem(THEME_KEY, v) } catch { /* 受限 iframe 忽略 */ } }
function initialTheme(): 'light' | 'dark' {
  const stored = readStored(); if (stored) return stored
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
}
const theme = ref<'light' | 'dark'>(initialTheme())
watchEffect(() => { document.documentElement.setAttribute('data-theme', theme.value) })
function toggleTheme() { theme.value = theme.value === 'dark' ? 'light' : 'dark'; writeStored(theme.value) }

const observeChapters = CHAPTERS.filter((c) => c.group === '观测')
const configChapters = CHAPTERS.filter((c) => c.group === '配置')
</script>

<template>
  <div v-if="fatal" class="pw-fatal">{{ fatal }}<button class="pw-primary" @click="fatal = ''">重试</button></div>
  <div v-else class="stage">
    <div class="console">
      <header>
        <div class="mast">
          <div class="brand"><span class="cn">帕鲁纪事</span><span class="en">PalChronicle</span></div>
          <button class="ghost" @click="toggleTheme">{{ theme === 'dark' ? '☀ 昼阅' : '☾ 夜观' }}</button>
        </div>
        <div class="dateline"></div>
        <div class="subline"><span>世界纪事 · 只读观测台</span></div>
      </header>
      <div class="layout">
        <nav class="rail" aria-label="章节索引">
          <div class="railcap">观测</div>
          <button v-for="c in observeChapters" :key="c.id" :aria-current="chapter === c.id ? 'true' : 'false'" @click="chapter = c.id">
            {{ c.label }}<span v-if="c.kind === 'status'" class="dot" aria-hidden="true"></span>
          </button>
          <div class="railcap">配置</div>
          <button v-for="c in configChapters" :key="c.id" :aria-current="chapter === c.id ? 'true' : 'false'" @click="chapter = c.id">{{ c.label }}</button>
        </nav>
        <div class="pane">
          <SettingsPanel v-show="chapter !== 'status'" :chapter="chapter" />
          <StatusPanel v-if="chapter === 'status'" />
        </div>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 4: 跑测试确认通过** — Run: `cd frontend && npm run test:run -- App` 与 `npm run typecheck`。Expected: PASS。
- [ ] **Step 5: 提交** — `git add frontend/src/App.vue frontend/src/App.test.ts && git commit -m "feat(fe): App 换报头+左索引分章导航+手动主题切换（v-show 常挂 SettingsPanel、错误边界保留）"`

---

### Task 11: 整合验收（全绿 + 构建 + 单文件产物）

**Files:** 无新增；跑全套门槛。

- [ ] **Step 1: 全测试** — Run: `cd frontend && npm run test:run`。Expected: **全部 PASS**（11 组件/lib 测试 + 新 chapters 测试）。
- [ ] **Step 2: 类型检查** — Run: `cd frontend && npm run typecheck`。Expected: PASS（无 TS 报错）。
- [ ] **Step 3: 构建 + 单文件产物校验** — Run: `cd frontend && npm run build && npm run verify:bundle`。Expected: build 成功；verify:bundle PASS（恰 1 JS、≤1 CSS、无 `import()`/跨-chunk import）。
- [ ] **Step 4: 若有产物变更提交** — `git add frontend/pages/settings 2>/dev/null; git status --short`；如产物在版本库内则 `git commit -m "build(fe): 重设计后设置页产物"`，否则跳过（产物可能 gitignore）。
- [ ] **Step 5: 记账** — 在 `.superpowers/sdd/progress.md` 追加：本分支所有任务完成、全绿。

---

## Self-Review（对照规格）

- **规格覆盖**：§0 demo 真源优先级→Global Constraints + 各任务护栏；§2 tokens→Task 3；§2.4 控件映射→Task 3 CSS 按 pw-\*+data-state；§3 分章结构→Task 1/9/10；§3.2 挂载策略→Task 10 v-show/v-if；§3.3 StatusPanel 边界→Task 8；§4 主题→Task 10；§5 两态卡片→Task 6/7（secret 判据 password_set/value_set、遮罩走 .pw-secret、占位分键、乐观 flash 失败不触发）；§6 分章+联动→Task 9（collectBody 恒全量、commit 带 pw-save）；§7 不变量 I1–I10 全落到约束/护栏；§8 schema→Task 2；§9 测试影响→各任务测试步。
- **占位符扫描**：无 TBD/TODO；每步含完整代码与命令。
- **类型一致**：`save(opts)` 签名在 Task 9 定义、Task 6/7 卡片 `emit('save', done)` 与 Task 9 `@save="(done)=>save({silent:true,done})"` 对齐；`indexLabel` prop 在 Task 6/7 消费、Task 9 传入；`Chapter.blocks` 在 Task 1 定义、Task 9 消费。

## Execution Handoff

计划已存 `docs/superpowers/plans/2026-07-13-settings-page-redesign.md`。执行用 **superpowers:subagent-driven-development**（子代理全 opus）：逐任务 fresh 实现者 + 双裁定评审 + 修复循环，记账 `.superpowers/sdd/progress.md`，末尾整分支终审。
