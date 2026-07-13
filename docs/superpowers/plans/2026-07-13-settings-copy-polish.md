# 设置页文案打磨 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans 逐任务执行。步骤用 `- [ ]` 复选框跟踪。

**Goal:** 按规格 `docs/superpowers/specs/2026-07-13-settings-copy-polish-design.md` §3 词表逐字替换设置页全部 UI 文案(全面直白基调),同步更新测试锚点。

**Architecture:** 纯字符串替换,零逻辑/契约改动。唯一的结构性微调:App.vue 删除两个 railcap 文本、在状态章与配置章之间加一条分隔线(tokens.css 加 `.rail-sep` 一条规则)。每个任务先改测试锚点(转红)再改源文案(转绿)。

**Tech Stack:** Vue 3.5.39 + Vitest 3.2.7(不动依赖)。

## Global Constraints

- **词表以规格 §3 为权威**,逐字实现,不即兴改词。
- `schema.ts` 只改 `label`/`hint`/`subtitle` 字符串;**key/type/default/options/secret/顺序一律不动**(schema.test 比 key 集)。
- `chapters.ts` 只改 `label` 字符串;id/kind/blocks/group 不动。
- 不动 `collect.ts`/`bridge.ts`/`errors.ts`/`boot.ts`/任何 `.py`/`_conf_schema.json`。
- 文案准则:label 名词短语无句号;hint 单句无句号、多句每句加;无人称;中英数字加半角空格;「稍候」=正在等、「稍后」+动词。
- 保留的锚点不许碰:`button.pw-save` 类、`input.pw-secret`、占位含「已设置」子串、「未登录」「请重新输入该服务器密码」「读取状态失败」「刷新」「在线 {N}」。
- 提交信息不得出现任何 Claude/AI 署名。前端命令在 `frontend/` 下跑;verify:bundle 从仓库根跑。

---

## File Structure

| 文件 | 动作 |
|---|---|
| `frontend/src/lib/schema.ts` | 改 label/hint/subtitle(§3.3) |
| `frontend/src/lib/chapters.ts` | 改 3 个章节 label(§3.2) |
| `frontend/src/components/SectionForm.test.ts` | 锚点「功能分组开关」→「功能开关」 |
| `frontend/src/components/SettingsPanel.vue` | 组名/按钮/提示/ERR/toast(§3.4) |
| `frontend/src/components/SettingsPanel.test.ts` | 锚点 4 处 |
| `frontend/src/components/ServerCard.vue` / `HeaderCard.vue` | 占位符 + 查看态 3 词(§3.5) |
| `frontend/src/components/StatusPanel.vue` | 章标题/chip/空态(§3.6) |
| `frontend/src/components/StatusPanel.test.ts` | 锚点「正在重载」→「正在应用新配置」 |
| `frontend/src/App.vue` | 副题/主题按钮/railcap 删除+分隔线(§3.1) |
| `frontend/src/App.test.ts` | 锚点「观测台」「接入」→「状态」「连接」 |
| `frontend/src/styles/tokens.css` | 加 `.rail-sep` 一条规则 |
| `pages/settings/` | 最后统一重建提交 |

任务顺序:1 分支+数据层(schema/chapters) → 2 SettingsPanel → 3 两卡片 → 4 StatusPanel → 5 App+分隔线 → 6 整合验收。

---

### Task 1: 分支 + schema.ts / chapters.ts 数据层文案

**Files:**
- Modify: `frontend/src/lib/schema.ts`、`frontend/src/lib/chapters.ts`、`frontend/src/components/SectionForm.test.ts`

**Interfaces:**
- Produces: 新 label 字符串被后续任务的测试锚点引用:「状态」「连接」「功能开关」「玩家查询」「访问控制」。

- [ ] **Step 1: 开分支**

```bash
git checkout main && git pull --ff-only && git checkout -b feat/settings-copy-polish
```

- [ ] **Step 2: 改 SectionForm.test 锚点(转红)** — `frontend/src/components/SectionForm.test.ts` 第 11 行:

```ts
    expect(w.text()).toContain('功能开关')
```
(原 `'功能分组开关'`;第 12 行遍历 `features.fields` 动态断言不用动。)

- [ ] **Step 3: 跑测试确认失败** — Run: `cd frontend && npm run test:run -- SectionForm`。Expected: FAIL(源仍是「功能分组开关」)。

- [ ] **Step 4: 改 `chapters.ts`** — 仅 3 个 label:

```ts
  { id: 'status', label: '状态', group: '观测', kind: 'status' },
  { id: 'access', label: '连接', group: '配置', kind: 'settings', blocks: ['routing'] },
  // cadence/world/privacy 三行不动
  { id: 'feature', label: '功能开关', group: '配置', kind: 'settings', blocks: ['features', 'players'] },
```

- [ ] **Step 5: 改 `schema.ts`** — 按规格 §3.3 词表逐字替换。SERVER_FIELDS/HEADER_FIELDS 完整新值:

```ts
export const SERVER_FIELDS: FieldSpec[] = [
  { key: 'name', type: 'string', label: '名称', default: '', hint: '唯一标识，勿含空格 / 冒号 / @' },
  { key: 'enabled', type: 'bool', label: '启用', default: true },
  { key: 'base_url', type: 'string', label: '服务器地址', default: 'http://127.0.0.1:8212', hint: '填 IP 或域名，含端口（默认 8212）' },
  { key: 'username', type: 'string', label: '用户名', default: 'admin' },
  { key: 'password', type: 'string', label: '密码', default: '', secret: true, hint: '留空则不修改；更推荐用下方环境变量' },
  { key: 'password_env', type: 'string', label: '密码环境变量名', default: '', hint: '填环境变量名，启动时从中读取密码；与密码二选一' },
  { key: 'timeout', type: 'int', label: '连接超时（秒）', default: 10 },
  { key: 'verify_tls', type: 'bool', label: '校验 TLS 证书', default: true, hint: '关闭后不校验证书，仅建议自签名或内网环境使用' },
  { key: 'timezone', type: 'string', label: '时区', default: '', hint: 'IANA 名称，如 Asia/Tokyo；留空用默认时区' },
]

export const HEADER_FIELDS: FieldSpec[] = [
  { key: 'name', type: 'string', label: '名称', default: '', hint: '如 CF-Access-Client-Id' },
  { key: 'value', type: 'string', label: '值', default: '', secret: true, hint: '留空则不修改；敏感值更推荐用环境变量' },
  { key: 'value_env', type: 'string', label: '值环境变量名', default: '', hint: '填环境变量名，启动时从中读取值；与值二选一' },
  { key: 'servers', type: 'string', label: '限定服务器', default: '', hint: '多个用逗号分隔；留空 = 发给所有服务器' },
]
```

OBJECT_SECTIONS 完整新值(key/type/default/options 与现状逐一相同,只有 title/subtitle/label/hint 变):

```ts
export const OBJECT_SECTIONS: ObjectSection[] = [
  { key: 'routing', title: '访问控制', subtitle: '哪些群可以查询，以及默认查询哪台服务器', fields: [
    { key: 'access_mode', type: 'enum', label: '访问模式', default: 'restricted', options: ['restricted', 'open'], hint: 'restricted 需管理员授权；open 全开放' },
    { key: 'default_server', type: 'string', label: '默认服务器', default: '', hint: '群里没指定、也没绑定时查询它' },
  ]},
  { key: 'polling', title: '轮询间隔', subtitle: '每类数据多久从服务器拉取一次，单位：秒', fields: [
    { key: 'metrics_seconds', type: 'int', label: '性能指标', default: 30, hint: '帧率、在线人数等；对应 metrics 接口' },
    { key: 'players_seconds', type: 'int', label: '在线玩家', default: 30, hint: '玩家列表与状态；对应 players 接口' },
    { key: 'info_seconds', type: 'int', label: '服务器信息', default: 600, hint: '名称、版本等；对应 info 接口' },
    { key: 'settings_seconds', type: 'int', label: '服务器设置', default: 1800, hint: '对应 settings 接口' },
    { key: 'game_data_seconds', type: 'int', label: '世界数据', default: 120, hint: '仅「公会与据点」启用时拉取；对应 game-data 接口' },
    { key: 'jitter_ratio', type: 'float', label: '间隔随机波动', default: 0.10, hint: '按比例加随机偏移，避免所有请求同时发出' },
    { key: 'max_concurrency', type: 'int', label: '同时请求数上限', default: 6 },
  ]},
  { key: 'world', title: '世界与展示', subtitle: '时区与 FPS 流畅度分档', fields: [
    { key: 'timezone', type: 'string', label: '默认时区', default: 'Asia/Tokyo', hint: 'IANA 名称，如 Asia/Tokyo' },
    { key: 'locale', type: 'enum', label: '消息语言', default: 'zh-CN', options: ['zh-CN'] },
    { key: 'fps_smooth', type: 'int', label: 'FPS 流畅阈值', default: 50, hint: '≥ 此值为流畅' },
    { key: 'fps_moderate', type: 'int', label: 'FPS 一般阈值', default: 35, hint: '≥ 此值为一般' },
    { key: 'fps_laggy', type: 'int', label: 'FPS 卡顿阈值', default: 20, hint: '≥ 此值为卡顿，低于则为严重卡顿' },
  ]},
  { key: 'bases', title: '据点推导', subtitle: '仅在「公会与据点」启用时生效', fields: [
    { key: 'enabled', type: 'bool', label: '启用', default: true },
    { key: 'assignment_radius', type: 'int', label: '据点归属半径', default: 5000, hint: '玩家距据点多远以内算作驻守' },
    { key: 'ambiguity_ratio', type: 'float', label: '归属模糊比', default: 0.20, hint: '最近与次近据点距离之比超过此值时，暂不判定归属' },
    { key: 'confirmation_samples', type: 'int', label: '确认次数', default: 3 },
    { key: 'position_grid_size', type: 'int', label: '坐标网格边长', default: 2000 },
    { key: 'z_weight', type: 'float', label: '高度权重', default: 0.5, hint: '计算距离时高度（Z 轴）的权重' },
  ]},
  { key: 'privacy', title: '隐私与脱敏', subtitle: '决定玩家个人信息公开到什么程度', fields: [
    { key: 'mode', type: 'enum', label: '隐私模式', default: 'balanced', options: ['strict', 'balanced', 'advanced'], hint: 'strict 最保守；balanced 为默认' },
    { key: 'public_exact_ping', type: 'bool', label: '公开精确 Ping', default: false, hint: '关闭时只显示优秀 / 正常 / 偏高' },
    { key: 'public_positions', type: 'bool', label: '公开坐标', default: false },
    { key: 'ping_good_ms', type: 'int', label: 'Ping 优秀阈值', default: 60, hint: '≤ 此值为优秀（毫秒）' },
    { key: 'ping_ok_ms', type: 'int', label: 'Ping 正常阈值', default: 120, hint: '≤ 此值为正常，超过则为偏高（毫秒）' },
    { key: 'uncertain_timeout', type: 'int', label: '掉线判定时间（秒）', default: 900, hint: '超过此时长无响应即视为离线' },
  ]},
  { key: 'history', title: '数据保留', subtitle: '各类数据的保留天数，到期自动清理', fields: [
    { key: 'raw_metrics_days', type: 'int', label: '原始指标', default: 7 },
    { key: 'aggregate_days', type: 'int', label: '预聚合统计', default: 90 },
    { key: 'session_days', type: 'int', label: '玩家会话', default: 365 },
    { key: 'observation_days', type: 'int', label: '观察记录', default: 180 },
  ]},
  { key: 'features', title: '功能开关', subtitle: '关闭的功能不采集数据，相关命令会提示未开放', fields: [
    { key: 'report', type: 'bool', label: '日报 / 在线统计', default: true, hint: '/pal today' },
    { key: 'events', type: 'bool', label: '世界事件记录', default: true, hint: '/pal events' },
    { key: 'guilds_bases', type: 'bool', label: '公会与据点', default: false, hint: '依赖 /game-data；专用服务器暂不支持' },
    { key: 'players', type: 'bool', label: '玩家查询', default: false, hint: '排行 / 档案 / 自助绑定' },
  ]},
  { key: 'players', title: '玩家查询', subtitle: '「玩家查询」启用时生效', fields: [
    { key: 'rank_top_n', type: 'int', label: '排行榜人数', default: 5 },
    { key: 'exclude_names', type: 'string', label: '排除名单', default: '', hint: '逗号分隔；名单内玩家不进榜单、不可查询' },
  ]},
]
```

- [ ] **Step 6: 跑测试确认通过** — Run: `cd frontend && npm run test:run -- SectionForm schema chapters collect`。Expected: 全 PASS(key 集未动)。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/lib/schema.ts frontend/src/lib/chapters.ts frontend/src/components/SectionForm.test.ts
git commit -m "docs(fe): schema/chapters 文案直白化（用途优先，术语退 hint）"
```

---

### Task 2: SettingsPanel 文案 + 测试锚点

**Files:**
- Modify: `frontend/src/components/SettingsPanel.vue`、`frontend/src/components/SettingsPanel.test.ts`

**Interfaces:**
- Consumes: Task 1 的「功能开关」「玩家查询」「访问控制」节标题(测试断言引用)。

- [ ] **Step 1: 改 SettingsPanel.test 锚点(转红)** — 4 处:

```ts
  it('feature 章渲染功能开关与玩家查询节', async () => {
    // …mountAt('feature') 不变…
    expect(w.text()).toContain('功能开关')
    expect(w.text()).toContain('玩家查询')
  })
  it('access 章渲染访问控制节 + 保存条', async () => {
    // …mountAt('access') 不变…
    expect(w.text()).toContain('访问控制')
    expect(w.text()).toContain('保存设置')
    expect(w.get('button.pw-save')).toBeTruthy()
  })
```
(credential_redirect 用例末行 `toContain('保存本页设置')` 同步改为 `toContain('保存设置')`;其余断言不动。)

- [ ] **Step 2: 跑测试确认失败** — Run: `cd frontend && npm run test:run -- SettingsPanel`。Expected: FAIL。

- [ ] **Step 3: 改 `SettingsPanel.vue` 字符串** — 逐处(规格 §3.4):

ERR 映射整块替换为:

```ts
const ERR: Record<string, string> = {
  save_in_progress: '保存进行中，请稍候', too_frequent: '保存过于频繁，请稍后再试',
  too_large: '配置内容过大，请精简后再保存', invalid_shape: '配置格式有误，请刷新页面后重试',
  invalid_field: '字段填写有误',
  credential_redirect: '修改了服务器地址，请重新输入该服务器密码',
  restart_failed_rolled_back: '保存未生效，已恢复原配置',
  restart_failed: '保存未生效且恢复失败，请检查后台日志',
  unauthorized: '未登录或登录已过期，请重新登录 Dashboard',
}
```

save() 内 toast 两处:

```ts
    if (skips.length) toast(`已保存，${skips.length} 条无效条目未生效`)
    else if (!opts.silent) toast('已保存，已生效')
```

catch 分支兜底两处 `'保存失败'` → `'保存失败，请重试'`(`e.message.includes('__unchanged__')` 分支不动)。

模板:
- `<span class="t">数据源</span><span class="c">要观测的 Palworld 服务器</span>` → `<span class="t">服务器</span><span class="c">要监测的 Palworld 服务器</span>`
- `:index-label="'源 ' + pad(i + 1)"` → `:index-label="'服务器 ' + pad(i + 1)"`
- `:index-label="'头 ' + pad(i + 1)"` → `:index-label="'请求头 ' + pad(i + 1)"`
- `＋ 添加数据源` → `＋ 添加服务器`
- grouphint → `含凭证的请求头建议填写「限定服务器」。留空会发给所有服务器，包括以后新增的。`
- `{{ saving ? '保存中…' : '保存本页设置' }}` → `{{ saving ? '保存中…' : '保存设置' }}`
- note → `服务器、请求头点各自的「保存」即生效；其余设置用这里保存`

- [ ] **Step 4: 跑测试确认通过** — Run: `cd frontend && npm run test:run -- SettingsPanel`。Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/SettingsPanel.vue frontend/src/components/SettingsPanel.test.ts
git commit -m "docs(fe): SettingsPanel 文案直白化（服务器/保存设置/错误提示重写）"
```

---

### Task 3: ServerCard / HeaderCard 占位与查看态词

**Files:**
- Modify: `frontend/src/components/ServerCard.vue`、`frontend/src/components/HeaderCard.vue`

**Interfaces:**
- 测试不改:占位新文案「已设置，留空则不修改」仍含「已设置」子串,两卡测试天然保持绿。

- [ ] **Step 1: 改 `ServerCard.vue`** — 3 处:
  - 编辑态占位:`'已设置（留空保持不变）'` → `'已设置，留空则不修改'`
  - 查看态 `<span class="ck">超时</span>` → `<span class="ck">连接超时</span>`
  - 查看态 `<span class="ck">密码变量</span>` → `<span class="ck">密码环境变量</span>`

- [ ] **Step 2: 改 `HeaderCard.vue`** — 2 处:
  - 编辑态占位:`'已设置（留空保持不变）'` → `'已设置，留空则不修改'`
  - 查看态 `<span class="ck">值变量</span>` → `<span class="ck">值环境变量</span>`

- [ ] **Step 3: 跑测试确认仍绿** — Run: `cd frontend && npm run test:run -- ServerCard HeaderCard`。Expected: 全 PASS(锚点是子串匹配)。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/ServerCard.vue frontend/src/components/HeaderCard.vue
git commit -m "docs(fe): 卡片占位与查看态用词打磨（留空则不修改/环境变量全称）"
```

---

### Task 4: StatusPanel 文案 + 测试锚点

**Files:**
- Modify: `frontend/src/components/StatusPanel.vue`、`frontend/src/components/StatusPanel.test.ts`

- [ ] **Step 1: 改 StatusPanel.test 锚点(转红)** — restarting 用例:

```ts
    expect(w.text()).toContain('正在应用新配置')
```
(原 `'正在重载'`;其余断言不动。)

- [ ] **Step 2: 跑测试确认失败** — Run: `cd frontend && npm run test:run -- StatusPanel`。Expected: FAIL。

- [ ] **Step 3: 改 `StatusPanel.vue` 模板** — script 不动,模板改为:

```vue
<template>
  <div class="pw-status">
    <div class="chapter-head"><h2>状态</h2></div>
    <p class="stint"><span>服务器实时状态</span><button class="ghost" @click="load">刷新</button></p>
    <p v-if="state === 'loading'" class="pw-muted">加载中…</p>
    <p v-else-if="state === 'error'" class="pw-error">读取状态失败，请重试</p>
    <template v-else>
      <p v-if="restarting" class="pw-muted">正在应用新配置…</p>
      <p v-if="!rows.length" class="pw-muted">尚未添加服务器，或数据尚未采集</p>
      <div v-for="row in rows" :key="row.name" class="obs">
        <span class="nm">{{ row.name }}</span>
        <span v-if="!row.ready" class="chip idle">未连接</span>
        <span v-else-if="row.degraded" class="chip warn">部分数据缺失</span>
        <span v-else class="chip good">正常</span>
        <span class="read">
          <template v-if="row.ready"><b>在线 {{ row.online }}</b><span>·</span><span>{{ row.smoothness_label }}</span></template>
          <span v-else>未连接</span>
        </span>
      </div>
    </template>
  </div>
</template>
```

- [ ] **Step 4: 跑测试确认通过** — Run: `cd frontend && npm run test:run -- StatusPanel`。Expected: PASS(空态行在有 rows 的用例中不渲染,不影响现断言)。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/StatusPanel.vue frontend/src/components/StatusPanel.test.ts
git commit -m "docs(fe): 状态页用词直白化（正常/未连接/部分数据缺失）+ 空态文案"
```

---

### Task 5: App 报头/主题按钮/railcap 删除 + 测试锚点

**Files:**
- Modify: `frontend/src/App.vue`、`frontend/src/App.test.ts`、`frontend/src/styles/tokens.css`

- [ ] **Step 1: 改 App.test 锚点(转红)**:

```ts
    expect(rail.some((b) => b.text().includes('状态'))).toBe(true)
    expect(rail.some((b) => b.text().includes('连接'))).toBe(true)
    const obs = rail.find((b) => b.text().includes('状态'))!
```
(原「观测台」「接入」;点击后 `toContain('刷新')` 不动。)

- [ ] **Step 2: 跑测试确认失败** — Run: `cd frontend && npm run test:run -- App`。Expected: FAIL。

- [ ] **Step 3: 改 `App.vue`**:
- 副题:`<span>世界纪事 · 只读观测台</span>` → `<span>Palworld 服务器监测 · 只读</span>`
- 主题按钮:`{{ theme === 'dark' ? '☀ 昼阅' : '☾ 夜观' }}` → `{{ theme === 'dark' ? '☀ 浅色' : '☾ 深色' }}`
- rail 模板(删两个 railcap,组间加分隔线):

```vue
        <nav class="rail" aria-label="章节索引">
          <button v-for="c in observeChapters" :key="c.id" :aria-current="chapter === c.id ? 'true' : 'false'" @click="chapter = c.id">
            {{ c.label }}<span v-if="c.kind === 'status'" class="dot" aria-hidden="true"></span>
          </button>
          <div class="rail-sep" aria-hidden="true"></div>
          <button v-for="c in configChapters" :key="c.id" :aria-current="chapter === c.id ? 'true' : 'false'" @click="chapter = c.id">{{ c.label }}</button>
        </nav>
```

- [ ] **Step 4: tokens.css 加分隔线规则**(放在 `.railcap` 规则附近;`.railcap` 两条规则已无使用者,一并删除):

```css
.rail-sep { height: 1px; background: var(--rule); margin: 10px 12px 10px 0; }
```
删除 `.railcap { … }` 与 `.rail button + .railcap { … }` 两条,及移动端媒体查询里的 `.railcap { display: none; } .rail button + .railcap { margin-top: 0; }`(改为 `.rail-sep { display: none; }`)。

- [ ] **Step 5: 跑测试确认通过** — Run: `cd frontend && npm run test:run -- App`。Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/App.vue frontend/src/App.test.ts frontend/src/styles/tokens.css
git commit -m "docs(fe): 报头副题直白化+主题按钮改浅色/深色+左索引去组名加分隔线"
```

---

### Task 6: 整合验收

- [ ] **Step 1: 全测试** — Run: `cd frontend && npm run test:run`。Expected: 全 PASS。
- [ ] **Step 2: typecheck** — Run: `cd frontend && npm run typecheck`。Expected: PASS。
- [ ] **Step 3: 构建 + 产物校验** — Run: `cd frontend && npm run build`,然后仓库根 `node frontend/scripts/verify-bundle.mjs`。Expected: OK。
- [ ] **Step 4: README 同步检查** — Run: `grep -nE "观测台|夜观|昼阅|数据源|功能分组|保存本页|世界纪事" README.md`。Expected: 无输出(README 是命令文档,预期不引用设置页文案);若有输出则逐处同步。
- [ ] **Step 5: 提交产物**

```bash
git add pages/settings && git commit -m "build(fe): 文案打磨后设置页产物"
```

- [ ] **Step 6: 记账** — `.superpowers/sdd/progress.md` 追加一行:文案打磨分支全任务完成、全绿。

---

## Self-Review

- **Spec 覆盖**:§3.1→Task 5;§3.2/§3.3→Task 1;§3.4→Task 2;§3.5→Task 3;§3.6→Task 4;§3.7 范围外→无任务(正确);§4 测试锚点→各任务 Step 1;§5 验收→Task 6。无缺口。
- **占位符扫描**:无 TBD/TODO;每步有确切字符串/代码/命令。
- **一致性**:「功能开关」(chapters label = features title)、「玩家查询」(features 开关 label = players 节 title)、「保存设置」(按钮 = 测试锚点)、「服务器」贯穿组名/indexLabel/添加按钮/stint。全角标点在 UI 字符串内统一(，；)与现有代码风格一致。
