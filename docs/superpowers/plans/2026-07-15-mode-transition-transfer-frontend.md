# 有条件模式互转 + 转移引导（Phase 2B 前端）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在自定义设置页「连接」章提供**有条件、带引导、带二次确认**的 single↔multi 模式互转前端——切换控件 + 确认对话框 + 多台转移向导 + 孤儿清理入口，消费 Phase 2A 已定的 4 个后端端点，失败不留半态。

**Architecture:** 新增一个 typed 客户端封装 `lib/transfer.ts`（4 端点的调用 + 全部载荷/回执 TS 接口 + 业务错误码→中文映射），复用既有 `bridge`（`apiGet`/`apiPost` 在 `ok:false` 时抛 `BusinessError`）。UI 拆为 4 个聚焦组件：`ModeTransfer.vue`（切换控件 + 预览拉取 + 按模式/就绪数派发子流 + POST 编排）、`ModeConfirmDialog.vue`（single↔multi 与 multi→single 单台的确认框，纯展示、emit 勾选集）、`TransferWizard.vue`（multi→single 多台四步向导，纯展示、删除侧勾选闸）、`OrphanCleanup.vue`（孤儿列表 + 强确认清理，自持网络调用）。`SettingsPanel.vue` 仅做**极薄接线**：在 access 章渲染 `ModeTransfer`/`OrphanCleanup`，把 `@applied` 连到既有 `applyConfig`（模式唯一变更点）、`@notify` 连到既有 `toast`。**模式只在后端 `res.ok===true` 后经 `applyConfig(res.config)` 改变**（复用 Phase 1 半态教训）。

**Tech Stack:** Vue 3.5（`<script setup lang="ts">`）、TypeScript 5.9、Vitest 3（jsdom、`globals:true`、`restoreMocks:true`）、`@vue/test-utils` 2、Vite 7（构建产物入 `pages/settings/**`，`npm run build` 内置 `normalize-eol.mjs` 统一 LF）。后端在 Phase 2A（`docs/superpowers/plans/2026-07-15-mode-transition-transfer-backend.md`）、**本计划不写后端**。

## Global Constraints

以下为项目级铁律（spec §8 + MEMORY），逐字适用于**每个任务**：

- **版本号不变（保持 v0.9.7）**——纯前端 + 文档，不动任何版本源（`metadata.yaml`/`__init__.py`/`main.py` 注册串）、不改任何版本断言。
- **失败不留半态（复用 Phase 1 教训，核心不变量）**：运行模式**只在后端 `res.ok===true` 后经 `applyConfig(res.config)` 改变**。任何 `ok:false`（含 `too_many_groups`/`migrate_bind_failed`/`invalid_surviving`/`no_ready_*`/`restart_failed_rolled_back`/校验拒绝）经 `bridge` 抛 `BusinessError`、被 catch → 错误 toast、**不 `applyConfig`、模式与页面不变**。`ok:true` 但带 `warnings`（`cleared_group_servers=False` / `purge_failed`）时仍 `applyConfig`（模式确已切、须对齐后端）+ 附告警 toast——如实告知「已切+清理未尽」，非假装成功。
- **删除侧强确认勾选闸**：multi→single 多台向导删除其余台时，摘要页红字列将删服务器 + 勾选闸「我了解此操作不可恢复」，勾选前「确认切换」按钮**禁用**（仿 Phase 1 点选前禁用范式）。孤儿清理同规格勾选闸。保留数据侧无此闸。
- **脏则先保存闸**：切换入口在 `dirty`（有未保存更改）时**禁用并提示先保存**——转移只读后端落盘 `self._raw_config`，未保存编辑不会进候选（single→multi 用脏 state 里的 umo 会被后端拒 `invalid_migrate_umos`）。spec §5 特指 single→multi，本计划对**两个方向**都门（更安全：multi→single 的保留台亦须是已落盘 server）。
- **前端 build no-drift + LF**：改任何前端源后必须 `cd frontend && npm run build`（内置 `normalize-eol.mjs`）重生成 `pages/settings/**`，并把产物一并 `git add` 提交，保 `git status --porcelain pages/settings` 干净、行尾 LF。
- **提交不出现 Claude**：commit message 正文与尾行都不提 Claude、不加 Co-Authored-By（全局已设 `attribution.commit=""`）。
- **README/docs 改中文用词须核 `tests/unit/readme_test.py` 锚点**：本计划文档只**新增**「模式互转」相关小节到 `docs/commands.md` / `docs/configuration.md`（不改 README、不改写既有锚点短语）——新增内容不会移除既有锚点；Task 5 跑 `readme_test.py` 坐实全绿。
- **端点契约（Phase 2A 权威，前端消费、不重定义）**：
  - `GET mode/transfer/preview?target=single` → `{ok:True, ready_servers:[{server_id,name}], bindings:[{umo,server_ids:[...]}]}`；`?target=multi` → `{ok:True, ready_servers, allowed_groups:[{umo,note}]}`；`restarting` 时 `{ok:True, restarting:True}`（无 ready/bindings/allowed_groups）。
  - `POST mode/transfer {target_mode, surviving_server_id?, migrate_umos:string[], purge_others:bool}` → `ok:True` 时 `{ok:True, config, warnings:{cleared_group_servers?:false, purge_failed?:string[]}, summary:{from,to,surviving,migrated,purged,failed_server_ids}}`；业务失败 `{ok:False, error, detail}`（经 bridge 抛 `BusinessError(error)`）。
  - `GET mode/orphans` → `{ok:True, orphans:[server_id]}`（`restarting` 时 `{ok:True, orphans:[], restarting:True}`）。
  - `POST mode/orphans/purge {server_ids?}` → `{ok:True, purged:{sid:{table:count}}, rejected:[sid], failed_server_ids:[sid]}`。**不信客户端**：后端持锁现场重算孤儿集，前端展示的列表仅供参考。前端不传 `server_ids`（清全部当前孤儿）。
  - `bridge.unwrap`：`ok===false` → 抛 `Unauthorized`（`error==='unauthorized'`）或 `BusinessError(code, path?)`；`ok!==false` → 原样返回。故所有客户端封装的返回类型均为 `ok:True` 分支。

## File Structure（本计划新建 / 修改）

- **新建** `frontend/src/lib/transfer.ts` —— 4 端点 typed 客户端 + 载荷/回执接口 + `TRANSFER_ERR` 码表 + `mapTransferError`（跨全部组件的类型与错误文案单一真相源）。
- **新建** `frontend/src/components/ModeTransfer.vue` —— 切换控件（当前模式 + 「切换到 单/多」按钮，`dirty` 门）+ 预览拉取 + 按 `worldMode`×就绪数派发（confirm/wizard/阻止）+ `postTransfer` 编排 + `applied`/`notify` emit。
- **新建** `frontend/src/components/ModeConfirmDialog.vue` —— single↔multi 与 multi→single 单台确认框（纯展示：迁移勾选清单、已有权/将获新权默认勾逻辑、未勾告警；emit `confirm(migrateUmos)` / `cancel`）。
- **新建** `frontend/src/components/TransferWizard.vue` —— multi→single 多台四步向导（选保留台 / 迁移群 / 其余保留删除 / 摘要+删除侧勾选闸；emit `confirm(payload)` / `cancel`）。
- **新建** `frontend/src/components/OrphanCleanup.vue` —— 孤儿列表（`listOrphans` on mount）+ 勾选闸强确认清理（`purgeOrphans`）；emit `notify`。
- **修改** `frontend/src/components/SettingsPanel.vue` —— access 章接线 `ModeTransfer`/`OrphanCleanup`、chapter-head badge 让位、新增 `serverNames` computed。
- **修改** `docs/commands.md` / `docs/configuration.md` —— 新增「模式互转 / 转移引导 / 孤儿清理」文档小节（Task 5）。
- **测试**：`transfer.test.ts`、`ModeTransfer.test.ts`、`ModeConfirmDialog.test.ts`、`TransferWizard.test.ts`、`OrphanCleanup.test.ts`（各与源同目录）+ 既有 `SettingsPanel.test.ts` 回归须全绿。

## Task 依赖顺序总览

`lib/transfer.ts` + `ModeTransfer` 控件（T1）→ `ModeConfirmDialog` + POST 编排（T2）→ `TransferWizard` + 向导流（T3）→ `OrphanCleanup` 入口（T4）→ 文档 + 全库终检（T5）。T2/T3 在 T1 的 `ModeTransfer` 上加子流渲染，additive；每任务末 `npm run build` 保 no-drift。

---

### Task 1: 转移客户端封装 `lib/transfer.ts` + `ModeTransfer` 切换控件（预览 + 派发）

**Files:**
- Create: `frontend/src/lib/transfer.ts`
- Create: `frontend/src/components/ModeTransfer.vue`
- Modify: `frontend/src/components/SettingsPanel.vue`（import + access 章接线 + `serverNames` computed + chapter-head badge 让位）
- Test: `frontend/src/lib/transfer.test.ts`（新建）、`frontend/src/components/ModeTransfer.test.ts`（新建）

**Interfaces:**
- Consumes: `bridge` 的 `apiGet(path)`/`apiPost(path,body)`（`ok:false` 抛 `BusinessError`/`Unauthorized`）；`errors` 的 `BusinessError`/`Unauthorized`。
- Produces（`lib/transfer.ts` 导出，供 T2–T4 消费）：
  - 接口 `ReadyServer{server_id,name}` / `Binding{umo,server_ids}` / `AllowedGroup{umo,note}` / `TransferPreview` / `TransferBody{target_mode,surviving_server_id?,migrate_umos,purge_others}` / `TransferWarnings` / `TransferSummary` / `TransferResult` / `OrphanList` / `OrphanPurgeResult`。
  - `previewTransfer(target:'single'|'multi'):Promise<TransferPreview>` / `postTransfer(body:TransferBody):Promise<TransferResult>` / `listOrphans():Promise<OrphanList>` / `purgeOrphans(serverIds?:string[]):Promise<OrphanPurgeResult>` / `TRANSFER_ERR:Record<string,string>` / `mapTransferError(e:unknown):string`。
- Produces（`ModeTransfer.vue`）：props `{worldMode:string, dirty:boolean, serverNames:string[]}`；emits `applied(config:Record<string,unknown>)` / `notify(msg:string, error:boolean)`；暴露 setup 态 `flow:'idle'|'confirm'|'wizard'`、`target`、`survivingId`、`preview`（供测试与 T2/T3 子流渲染）。

- [ ] **Step 1: 写失败测试（transfer 客户端）**

新建 `frontend/src/lib/transfer.test.ts`：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  previewTransfer, postTransfer, listOrphans, purgeOrphans, mapTransferError,
} from './transfer'
import { BusinessError, Unauthorized } from './errors'

function setBridge(impl: Partial<AstrBotBridge>) {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn(), ...impl }
}

describe('transfer client', () => {
  beforeEach(() => { delete (window as any).AstrBotPluginPage })

  it('previewTransfer 用 target 查询串调 apiGet 并透传 payload', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], bindings: [] })
    setBridge({ apiGet })
    const pv = await previewTransfer('single')
    expect(apiGet).toHaveBeenCalledWith('mode/transfer/preview?target=single')
    expect(pv.ready_servers).toEqual([{ server_id: 'a', name: 'a' }])
  })

  it('postTransfer ok:true 返回 config/warnings/summary，body 原样透传', async () => {
    const apiPost = vi.fn().mockResolvedValue({
      ok: true, config: { routing: { world_mode: 'single' } }, warnings: {},
      summary: { from: 'multi', to: 'single', surviving: 'a', migrated: 1, purged: {}, failed_server_ids: [] },
    })
    setBridge({ apiPost })
    const r = await postTransfer({ target_mode: 'single', surviving_server_id: 'a', migrate_umos: ['u1'], purge_others: false })
    expect(apiPost).toHaveBeenCalledWith('mode/transfer',
      { target_mode: 'single', surviving_server_id: 'a', migrate_umos: ['u1'], purge_others: false })
    expect((r.config as any).routing.world_mode).toBe('single')
    expect(r.summary.migrated).toBe(1)
  })

  it('postTransfer ok:false → 抛 BusinessError（模式不变由调用方处理）', async () => {
    setBridge({ apiPost: vi.fn().mockResolvedValue({ ok: false, error: 'too_many_groups', detail: {} }) })
    await expect(postTransfer({ target_mode: 'single', migrate_umos: [], purge_others: false }))
      .rejects.toBeInstanceOf(BusinessError)
  })

  it('listOrphans 调 apiGet mode/orphans', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, orphans: ['ghost'] })
    setBridge({ apiGet })
    const r = await listOrphans()
    expect(apiGet).toHaveBeenCalledWith('mode/orphans')
    expect(r.orphans).toEqual(['ghost'])
  })

  it('purgeOrphans 无参不带 server_ids（清全部当前孤儿）', async () => {
    const apiPost = vi.fn().mockResolvedValue({ ok: true, purged: {}, rejected: [], failed_server_ids: [] })
    setBridge({ apiPost })
    await purgeOrphans()
    expect(apiPost).toHaveBeenCalledWith('mode/orphans/purge', {})
  })

  it('mapTransferError 映射业务码 / Unauthorized / 未知码兜底', () => {
    expect(mapTransferError(new BusinessError('migrate_bind_failed'))).toContain('预绑定失败')
    expect(mapTransferError(new BusinessError('too_many_groups'))).toContain('上限')
    expect(mapTransferError(new Unauthorized())).toContain('未登录')
    expect(mapTransferError(new BusinessError('unknown_x'))).toBe('操作失败，请重试')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/lib/transfer.test.ts`
Expected: FAIL —— `Failed to resolve import './transfer'`（模块尚不存在）。

- [ ] **Step 3: 实现 `lib/transfer.ts`**

新建 `frontend/src/lib/transfer.ts`：

```ts
import { apiGet, apiPost } from './bridge'
import { BusinessError, Unauthorized } from './errors'

export interface ReadyServer { server_id: string; name: string }
export interface Binding { umo: string; server_ids: string[] }
export interface AllowedGroup { umo: string; note: string }

// 预览端点回传（restarting 时仅 ok+restarting；否则按 target 带 bindings 或 allowed_groups）。
export interface TransferPreview {
  ok: boolean
  restarting?: boolean
  ready_servers?: ReadyServer[]
  bindings?: Binding[] // target=single（multi→single）
  allowed_groups?: AllowedGroup[] // target=multi（single→multi）
}

export interface TransferBody {
  target_mode: 'single' | 'multi'
  surviving_server_id?: string
  migrate_umos: string[]
  purge_others: boolean
}

export interface TransferWarnings {
  cleared_group_servers?: false // 源介质清理未尽（M-f）
  purge_failed?: string[] // 部分台数据清理失败
}

export interface TransferSummary {
  from: string
  to: string
  surviving: string | null
  migrated: number
  purged: Record<string, Record<string, number>>
  failed_server_ids: string[]
}

// postTransfer 只在 ok:true 返回（ok:false 已由 bridge 抛 BusinessError）。
export interface TransferResult {
  ok: true
  config: Record<string, unknown>
  warnings: TransferWarnings
  summary: TransferSummary
}

export interface OrphanList { ok: boolean; orphans: string[]; restarting?: boolean }
export interface OrphanPurgeResult {
  ok: true
  purged: Record<string, Record<string, number>>
  rejected: string[]
  failed_server_ids: string[]
}

export function previewTransfer(target: 'single' | 'multi'): Promise<TransferPreview> {
  return apiGet<TransferPreview>('mode/transfer/preview?target=' + encodeURIComponent(target))
}

export function postTransfer(body: TransferBody): Promise<TransferResult> {
  return apiPost<TransferResult>('mode/transfer', body)
}

export function listOrphans(): Promise<OrphanList> {
  return apiGet<OrphanList>('mode/orphans')
}

// 不传 server_ids：后端持锁现场重算孤儿集、清全部当前孤儿（不信客户端，Blocker-O）。
export function purgeOrphans(serverIds?: string[]): Promise<OrphanPurgeResult> {
  const body = serverIds && serverIds.length ? { server_ids: serverIds } : {}
  return apiPost<OrphanPurgeResult>('mode/orphans/purge', body)
}

export const TRANSFER_ERR: Record<string, string> = {
  transfer_in_progress: '转移正在进行中，请稍候',
  purge_in_progress: '清理正在进行中，请稍候',
  busy: '系统忙（重载中），请稍后再试',
  no_change: '目标模式与当前一致，无需切换',
  invalid_target: '切换目标无效',
  invalid_surviving: '所选保留服务器无效或未就绪',
  no_ready_server: '没有就绪的服务器，无法切换到单服务器模式',
  no_ready_target: '没有就绪的服务器可绑定，无法迁移授权',
  invalid_migrate_umos: '迁移列表已过期，请重新打开切换向导后重试',
  too_many_groups: '授权群数量超过上限（200），无法迁移，请先精简名单',
  migrate_bind_failed: '授权预绑定失败，模式未改变，可稍后重试',
  restart_failed_rolled_back: '切换未生效，已恢复原模式',
  restart_failed: '切换未生效且恢复失败，请检查后台日志',
}

// 统一错误文案：Unauthorized / BusinessError 码表 / 兜底。模式不变路径只弹此文案、不改 state。
export function mapTransferError(e: unknown): string {
  if (e instanceof Unauthorized) return '未登录或登录已过期，请重新登录 Dashboard'
  if (e instanceof BusinessError) return TRANSFER_ERR[e.code] ?? '操作失败，请重试'
  return '操作失败，请重试'
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/lib/transfer.test.ts`
Expected: PASS（6 passed）。

- [ ] **Step 5: 写失败测试（ModeTransfer 控件派发）**

新建 `frontend/src/components/ModeTransfer.test.ts`：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ModeTransfer from './ModeTransfer.vue'

function setBridge(impl: Partial<AstrBotBridge>) {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn(), ...impl }
}
const mk = (worldMode: string, dirty = false, serverNames: string[] = ['a']) =>
  mount(ModeTransfer, { props: { worldMode, dirty, serverNames } })

describe('ModeTransfer 切换控件', () => {
  beforeEach(() => { delete (window as any).AstrBotPluginPage })

  it('渲染当前模式 + 切换按钮（multi 显示切换到单服务器）', () => {
    setBridge({})
    const w = mk('multi')
    expect(w.text()).toContain('当前模式：多服务器')
    expect(w.get('button[data-act="switch"]').text()).toContain('切换到单服务器')
  })

  it('dirty 时切换按钮禁用 + 提示先保存', () => {
    setBridge({})
    const w = mk('multi', true)
    expect((w.get('button[data-act="switch"]').element as HTMLButtonElement).disabled).toBe(true)
    expect(w.text()).toContain('保存后可切换')
  })

  it('single→multi：预览就绪台后 flow=confirm、target=multi', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], allowed_groups: [] }) })
    const w = mk('single')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    expect((w.vm as any).target).toBe('multi')
    expect((w.vm as any).flow).toBe('confirm')
  })

  it('multi→single 单就绪台：flow=confirm、survivingId 取该台', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], bindings: [] }) })
    const w = mk('multi')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    expect((w.vm as any).flow).toBe('confirm')
    expect((w.vm as any).survivingId).toBe('a')
  })

  it('multi→single 多就绪台：flow=wizard', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }, { server_id: 'b', name: 'b' }], bindings: [] }) })
    const w = mk('multi')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    expect((w.vm as any).flow).toBe('wizard')
  })

  it('multi→single 零就绪台：notify 阻止、flow 保持 idle', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, ready_servers: [], bindings: [] }) })
    const w = mk('multi')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    expect((w.vm as any).flow).toBe('idle')
    expect(w.emitted('notify')?.[0]?.[1]).toBe(true) // error=true
  })

  it('restarting：notify 稍后再试、flow 保持 idle', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, restarting: true }) })
    const w = mk('single')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    expect((w.vm as any).flow).toBe('idle')
    expect((w.emitted('notify')?.[0]?.[0] as string)).toContain('重载中')
  })
})
```

- [ ] **Step 6: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/components/ModeTransfer.test.ts`
Expected: FAIL —— `Failed to resolve import './ModeTransfer.vue'`。

- [ ] **Step 7: 实现 `ModeTransfer.vue`（控件 + 预览派发；子流渲染留 T2/T3）**

新建 `frontend/src/components/ModeTransfer.vue`：

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { previewTransfer, mapTransferError, type TransferPreview } from '../lib/transfer'

const props = defineProps<{ worldMode: string; dirty: boolean; serverNames: string[] }>()
const emit = defineEmits<{
  (e: 'applied', config: Record<string, unknown>): void
  (e: 'notify', msg: string, error: boolean): void
}>()

type Flow = 'idle' | 'confirm' | 'wizard'
const flow = ref<Flow>('idle')
const preview = ref<TransferPreview | null>(null)
const target = ref<'single' | 'multi'>('multi')
const survivingId = ref('')
const working = ref(false)

// 切换派发：dirty 门 → 拉预览 → 按 target×就绪数派对应子流。
// 失败不留半态：此处只开子流，模式变更等 POST ok 后由父 applyConfig 做（T2 runTransfer）。
async function onSwitch() {
  if (props.dirty || working.value) { emit('notify', '请先保存当前更改，再切换模式', true); return }
  const t: 'single' | 'multi' = props.worldMode === 'single' ? 'multi' : 'single'
  target.value = t
  working.value = true
  let pv: TransferPreview
  try { pv = await previewTransfer(t) } catch (e) { emit('notify', mapTransferError(e), true); working.value = false; return }
  working.value = false
  if (pv.restarting) { emit('notify', '系统重载中，请稍后再试', true); return }
  preview.value = pv
  const readyCount = (pv.ready_servers ?? []).length
  if (t === 'single') {
    if (readyCount === 0) { emit('notify', '没有就绪的服务器，无法切换到单服务器模式', true); return }
    if (readyCount === 1) { survivingId.value = pv.ready_servers![0].server_id; flow.value = 'confirm' }
    else { flow.value = 'wizard' }
  } else {
    flow.value = 'confirm' // single→multi 恒确认框（就绪为空时框内提示无可绑目标）
  }
}

function closeFlow() { flow.value = 'idle'; preview.value = null }
</script>

<template>
  <section class="mode-transfer">
    <div class="mt-head">
      <span class="mode-badge">当前模式：{{ worldMode === 'single' ? '单服务器' : '多服务器' }}</span>
      <button class="mt-switch" data-act="switch" :disabled="dirty || working" @click="onSwitch">
        切换到{{ worldMode === 'single' ? '多' : '单' }}服务器
      </button>
      <span v-if="dirty" class="mt-hint">有未保存更改，保存后可切换</span>
    </div>
    <!-- T2 在此渲染 <ModeConfirmDialog v-if="flow === 'confirm' && preview">；
         T3 渲染 <TransferWizard v-if="flow === 'wizard' && preview"> -->
  </section>
</template>

<style scoped>
.mode-transfer { margin-bottom: 4px; }
.mt-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.mode-badge { font-size: 11.5px; color: var(--ink-2); background: color-mix(in srgb, var(--focus) 6%, var(--card)); border: 1px solid var(--rule); border-radius: var(--r); padding: 4px 10px; white-space: nowrap; }
.mt-switch { font-size: 12px; padding: 5px 12px; border-radius: var(--r); border: 1px solid var(--focus); background: color-mix(in srgb, var(--focus) 10%, var(--card)); color: var(--ink); cursor: pointer; }
.mt-switch:disabled { opacity: .5; cursor: not-allowed; }
.mt-hint { font-size: 11.5px; color: var(--warn); }
</style>
```

- [ ] **Step 8: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/components/ModeTransfer.test.ts`
Expected: PASS（7 passed）。

- [ ] **Step 9: 接线进 `SettingsPanel.vue`（access 章 + serverNames + badge 让位）**

在 `<script setup>` import 段（`import GroupCard from './GroupCard.vue'` 一带）后加：

```ts
import ModeTransfer from './ModeTransfer.vue'
```

在 `isPermissions` computed 之后追加 `serverNames` computed（供多台向导算「所有非 surviving 台」）：

```ts
// 全部已配置服务器名（含非就绪）——转移向导删除侧摘要用（M = 所有非 surviving 台）
const serverNames = computed(() => state.servers.map((s) => String((s as Record<string, unknown>).name ?? '')))
```

把 chapter-head 的只读 badge 改为**非 access 章才显示**（access 章由 `ModeTransfer` 提供模式显示 + 切换入口）。将模板中：

```html
      <div class="chapter-head"><h2>{{ chapterTitle }}</h2>
        <span class="mode-badge">当前模式：{{ worldMode === 'single' ? '单服务器' : '多服务器' }} · 切换请到插件齿轮配置</span>
      </div>
```

替换为：

```html
      <div class="chapter-head"><h2>{{ chapterTitle }}</h2>
        <span v-if="!isAccess" class="mode-badge">当前模式：{{ worldMode === 'single' ? '单服务器' : '多服务器' }}</span>
      </div>
```

在 access 章块 `<template v-if="isAccess">` 内、`<section>` 服务器区块**之前**插入 `ModeTransfer`：

```html
      <template v-if="isAccess">
        <ModeTransfer :world-mode="worldMode" :dirty="dirty" :server-names="serverNames"
          @applied="applyConfig" @notify="(m, e) => toast(m, e)" />
        <section>
          <div class="group-head"><span class="t">服务器</span><span class="c">要监测的 Palworld 服务器</span></div>
```

（其余 access 章内容不变。）

- [ ] **Step 10: 跑 SettingsPanel 回归 + 全前端测试**

Run: `cd frontend && npx vitest run src/components/SettingsPanel.test.ts src/components/ModeTransfer.test.ts src/lib/transfer.test.ts`
Expected: PASS（既有 SettingsPanel 用例全绿——`ModeTransfer`/badge 让位不破坏「单服务器/多服务器」文案断言、不新增 `pw-save`/`.add` 冲突；新测全绿）。

Run（全量）: `cd frontend && npx vitest run`
Expected: 全绿（既有 + 新增）。

- [ ] **Step 11: 构建保 no-drift + 提交**

Run: `cd frontend && npm run build`
Expected: 构建成功、`normalize-eol` 统一 LF。

Run: `cd .. && git status --porcelain pages/settings`
Expected: 有产物改动（`pages/settings/assets/index.js` 等）；行尾 LF。

```bash
git add frontend/src/lib/transfer.ts frontend/src/lib/transfer.test.ts \
  frontend/src/components/ModeTransfer.vue frontend/src/components/ModeTransfer.test.ts \
  frontend/src/components/SettingsPanel.vue pages/settings
git commit -m "feat: 前端转移客户端 lib/transfer + ModeTransfer 切换控件（预览派发）"
```

---

### Task 2: 确认对话框 `ModeConfirmDialog.vue` + `ModeTransfer` POST 编排（single↔multi、multi→single 单台）

**Files:**
- Create: `frontend/src/components/ModeConfirmDialog.vue`
- Modify: `frontend/src/components/ModeTransfer.vue`（渲染 `flow==='confirm'` 的对话框 + `onConfirm`/`runTransfer`）
- Test: `frontend/src/components/ModeConfirmDialog.test.ts`（新建）、`frontend/src/components/ModeTransfer.test.ts`（追加 POST 编排用例）

**Interfaces:**
- Consumes: T1 `TransferPreview`/`TransferBody`/`postTransfer`/`mapTransferError`。
- Produces（`ModeConfirmDialog.vue`）：props `{target:'single'|'multi', preview:TransferPreview, survivingId?:string}`；emits `confirm(migrateUmos:string[])` / `cancel`。默认勾选：target=multi 全勾（皆保留、绑唯一就绪台）；target=single 仅「保留台已有权」（`survivingId ∈ binding.server_ids`）默认勾、「将获新权」默认不勾。未勾任何群→告警。
- Produces（`ModeTransfer.vue` 追加）：`onConfirm(migrateUmos)` 组装 `TransferBody`（single→multi 无 surviving；multi→single 单台带 `surviving_server_id=survivingId`、`purge_others=false`）→ `runTransfer`。`runTransfer`：`postTransfer` ok → `emit('applied', res.config)` + 成功/告警 toast；`BusinessError` → `emit('notify', mapTransferError(e), true)`（模式不变）；`finally` 关闭子流。

- [ ] **Step 1: 写失败测试（ModeConfirmDialog）**

新建 `frontend/src/components/ModeConfirmDialog.test.ts`：

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ModeConfirmDialog from './ModeConfirmDialog.vue'

describe('ModeConfirmDialog', () => {
  it('target=multi：allowed_groups 全默认勾，确认 emit 全部 umo', async () => {
    const w = mount(ModeConfirmDialog, { props: {
      target: 'multi',
      preview: { ok: true, ready_servers: [{ server_id: 'a', name: 'a' }],
        allowed_groups: [{ umo: 'u1', note: '主群' }, { umo: 'u2', note: '' }] },
    } })
    expect(w.text()).toContain('切换到多服务器')
    await w.get('button[data-act="confirm"]').trigger('click')
    expect(w.emitted('confirm')?.[0]?.[0]).toEqual(['u1', 'u2'])
  })

  it('target=single：已有保留台权限默认勾、将获新权默认不勾', async () => {
    const w = mount(ModeConfirmDialog, { props: {
      target: 'single', survivingId: 'keep',
      preview: { ok: true, ready_servers: [{ server_id: 'keep', name: 'keep' }],
        bindings: [{ umo: 'u_has', server_ids: ['keep', 'x'] }, { umo: 'u_new', server_ids: ['x'] }] },
    } })
    // u_has 已有权 → 默认勾；u_new 将获新权 → 默认不勾
    expect(w.text()).toContain('已有权')
    expect(w.text()).toContain('将获新权')
    await w.get('button[data-act="confirm"]').trigger('click')
    expect(w.emitted('confirm')?.[0]?.[0]).toEqual(['u_has'])
  })

  it('target=single：手动勾上「将获新权」→ 确认含该 umo（扩权）', async () => {
    const w = mount(ModeConfirmDialog, { props: {
      target: 'single', survivingId: 'keep',
      preview: { ok: true, ready_servers: [{ server_id: 'keep', name: 'keep' }],
        bindings: [{ umo: 'u_new', server_ids: ['x'] }] },
    } })
    const boxes = w.findAll('input[type="checkbox"]')
    await boxes[0].setValue(true)
    await w.get('button[data-act="confirm"]').trigger('click')
    expect(w.emitted('confirm')?.[0]?.[0]).toEqual(['u_new'])
  })

  it('取消全部勾选 → 显示未迁移告警', async () => {
    const w = mount(ModeConfirmDialog, { props: {
      target: 'multi', preview: { ok: true, ready_servers: [{ server_id: 'a', name: 'a' }],
        allowed_groups: [{ umo: 'u1', note: '' }] },
    } })
    await w.findAll('input[type="checkbox"]')[0].setValue(false)
    expect(w.text()).toContain('未勾选任何群')
  })

  it('target=multi 且无就绪台 → 提示无可绑目标', () => {
    const w = mount(ModeConfirmDialog, { props: {
      target: 'multi', preview: { ok: true, ready_servers: [], allowed_groups: [{ umo: 'u1', note: '' }] },
    } })
    expect(w.text()).toContain('无就绪服务器可绑定')
  })

  it('cancel 按钮 emit cancel', async () => {
    const w = mount(ModeConfirmDialog, { props: {
      target: 'multi', preview: { ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], allowed_groups: [] },
    } })
    await w.get('button[data-act="cancel"]').trigger('click')
    expect(w.emitted('cancel')).toBeTruthy()
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/components/ModeConfirmDialog.test.ts`
Expected: FAIL —— `Failed to resolve import './ModeConfirmDialog.vue'`。

- [ ] **Step 3: 实现 `ModeConfirmDialog.vue`**

新建 `frontend/src/components/ModeConfirmDialog.vue`：

```vue
<script setup lang="ts">
import { reactive, computed } from 'vue'
import type { TransferPreview } from '../lib/transfer'

const props = defineProps<{
  target: 'single' | 'multi'
  preview: TransferPreview
  survivingId?: string
}>()
const emit = defineEmits<{ (e: 'confirm', migrateUmos: string[]): void; (e: 'cancel'): void }>()

interface Row { umo: string; label: string; hasNew: boolean }

// 迁移清单行：single→multi 用 allowed_groups；multi→single 用 bindings + survivingId 判已有权/将获新权。
const rows = computed<Row[]>(() => {
  if (props.target === 'multi') {
    return (props.preview.allowed_groups ?? []).map((g) => ({
      umo: g.umo, label: g.note ? `${g.umo}（${g.note}）` : g.umo, hasNew: false,
    }))
  }
  const sid = props.survivingId ?? ''
  return (props.preview.bindings ?? []).map((b) => ({
    umo: b.umo, label: b.umo, hasNew: !b.server_ids.includes(sid),
  }))
})

// 默认勾选：target=multi 全勾；target=single 仅「已有权」勾。构建时一次性初始化。
const checked = reactive<Record<string, boolean>>({})
for (const r of rows.value) checked[r.umo] = props.target === 'multi' ? true : !r.hasNew

const checkedCount = computed(() => rows.value.filter((r) => checked[r.umo]).length)
const noReadyTarget = computed(() => props.target === 'multi' && (props.preview.ready_servers ?? []).length === 0)

function confirm() {
  emit('confirm', rows.value.filter((r) => checked[r.umo]).map((r) => r.umo))
}
</script>

<template>
  <div class="modal-backdrop">
    <div class="modal">
      <h3>切换到{{ target === 'single' ? '单服务器' : '多服务器' }}模式</h3>
      <p v-if="target === 'single'" class="lead">迁移下列群的查询授权到保留服务器；未勾选的群切换后需重新授权。</p>
      <p v-else class="lead">迁移下列授权群到多服务器绑定；未勾选的群切换后需用 /pal link 重新绑定。</p>
      <p v-if="noReadyTarget" class="warn">当前无就绪服务器可绑定，迁移的群暂时无法生效。</p>
      <ul v-if="rows.length" class="rows">
        <li v-for="r in rows" :key="r.umo">
          <label>
            <input type="checkbox" :checked="checked[r.umo]"
              @change="checked[r.umo] = ($event.target as HTMLInputElement).checked" />
            <span class="mono">{{ r.label }}</span>
            <span v-if="r.hasNew" class="tag-new">将获新权</span>
            <span v-else-if="target === 'single'" class="tag-has">已有权</span>
          </label>
        </li>
      </ul>
      <p v-else class="muted">没有可迁移的授权群。</p>
      <p v-if="rows.length && checkedCount === 0" class="warn">未勾选任何群：切换后相关群需重新授权，否则无法查询。</p>
      <div class="actions">
        <button class="ghost" data-act="cancel" @click="emit('cancel')">取消</button>
        <button class="pw-primary" data-act="confirm" @click="confirm">确认切换</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, .45); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal { background: var(--card); border: 1px solid var(--rule); border-radius: var(--r); padding: 20px 22px; width: min(560px, 92vw); max-height: 86vh; overflow: auto; display: flex; flex-direction: column; gap: 12px; }
.modal h3 { margin: 0; font-size: 15px; }
.lead { margin: 0; font-size: 12.5px; color: var(--ink-2); line-height: 1.55; }
.warn { margin: 0; font-size: 12.5px; color: var(--warn); }
.muted { margin: 0; font-size: 12.5px; color: var(--ink-2); }
.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.rows label { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
.mono { font-family: ui-monospace, monospace; }
.tag-new { font-size: 11px; color: var(--warn); border: 1px solid var(--warn); border-radius: 4px; padding: 0 5px; }
.tag-has { font-size: 11px; color: var(--ink-2); border: 1px solid var(--rule); border-radius: 4px; padding: 0 5px; }
.actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 4px; }
.actions button { padding: 6px 14px; border-radius: var(--r); cursor: pointer; }
.ghost { background: transparent; border: 1px solid var(--rule); color: var(--ink); }
</style>
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/components/ModeConfirmDialog.test.ts`
Expected: PASS（6 passed）。

- [ ] **Step 5: 写失败测试（ModeTransfer POST 编排）**

在 `frontend/src/components/ModeTransfer.test.ts` 追加（同文件 `describe` 内）：

```ts
  it('single→multi 确认 → POST 正确 body、ok:true 后 emit applied + 成功 notify', async () => {
    const savedCfg = { routing: { world_mode: 'multi' } }
    const apiGet = vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], allowed_groups: [{ umo: 'u1', note: '' }] })
    const apiPost = vi.fn().mockResolvedValue({ ok: true, config: savedCfg, warnings: {},
      summary: { from: 'single', to: 'multi', surviving: null, migrated: 1, purged: {}, failed_server_ids: [] } })
    setBridge({ apiGet, apiPost })
    const w = mk('single')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    const dlg = w.findComponent({ name: 'ModeConfirmDialog' })
    expect(dlg.exists()).toBe(true)
    dlg.vm.$emit('confirm', ['u1']); await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('mode/transfer',
      { target_mode: 'multi', migrate_umos: ['u1'], purge_others: false })
    expect(w.emitted('applied')?.[0]?.[0]).toEqual(savedCfg)
    expect((w.emitted('notify')?.at(-1)?.[1])).toBe(false) // 成功非 error
    expect((w.vm as any).flow).toBe('idle') // 子流关闭
  })

  it('multi→single 单台确认 → body 带 surviving_server_id、purge_others=false', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'keep', name: 'keep' }], bindings: [{ umo: 'u1', server_ids: ['keep'] }] })
    const apiPost = vi.fn().mockResolvedValue({ ok: true, config: {}, warnings: {},
      summary: { from: 'multi', to: 'single', surviving: 'keep', migrated: 1, purged: {}, failed_server_ids: [] } })
    setBridge({ apiGet, apiPost })
    const w = mk('multi')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    w.findComponent({ name: 'ModeConfirmDialog' }).vm.$emit('confirm', ['u1']); await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('mode/transfer',
      { target_mode: 'single', migrate_umos: ['u1'], purge_others: false, surviving_server_id: 'keep' })
  })

  it('ok:false（too_many_groups）→ 错误 notify、不 emit applied、模式不变', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], allowed_groups: [{ umo: 'u1', note: '' }] })
    const apiPost = vi.fn().mockResolvedValue({ ok: false, error: 'too_many_groups', detail: {} })
    setBridge({ apiGet, apiPost })
    const w = mk('single')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    w.findComponent({ name: 'ModeConfirmDialog' }).vm.$emit('confirm', ['u1']); await flushPromises()
    expect(w.emitted('applied')).toBeFalsy()
    expect((w.emitted('notify')?.at(-1)?.[0] as string)).toContain('上限')
    expect((w.emitted('notify')?.at(-1)?.[1])).toBe(true)
  })

  it('ok:true 带 warnings.cleared_group_servers=false → applied + 告警 notify(error)', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'keep', name: 'keep' }], bindings: [{ umo: 'u1', server_ids: ['keep'] }] })
    const apiPost = vi.fn().mockResolvedValue({ ok: true, config: {}, warnings: { cleared_group_servers: false },
      summary: { from: 'multi', to: 'single', surviving: 'keep', migrated: 1, purged: {}, failed_server_ids: [] } })
    setBridge({ apiGet, apiPost })
    const w = mk('multi')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    w.findComponent({ name: 'ModeConfirmDialog' }).vm.$emit('confirm', ['u1']); await flushPromises()
    expect(w.emitted('applied')).toBeTruthy() // 模式确已切、须对齐后端
    expect((w.emitted('notify')?.at(-1)?.[0] as string)).toContain('清理未尽')
    expect((w.emitted('notify')?.at(-1)?.[1])).toBe(true)
  })

  it('对话框 cancel → 关闭子流、无 POST', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], allowed_groups: [] })
    const apiPost = vi.fn()
    setBridge({ apiGet, apiPost })
    const w = mk('single')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    w.findComponent({ name: 'ModeConfirmDialog' }).vm.$emit('cancel'); await flushPromises()
    expect((w.vm as any).flow).toBe('idle')
    expect(apiPost).not.toHaveBeenCalled()
  })
```

- [ ] **Step 6: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/components/ModeTransfer.test.ts`
Expected: FAIL —— `ModeConfirmDialog` 未渲染（`dlg.exists()` false）、`apiPost` 未被调用。

- [ ] **Step 7: `ModeTransfer.vue` 加对话框渲染 + POST 编排**

在 `<script setup>` import 段补 `ModeConfirmDialog` 与 `postTransfer`/`TransferBody`：

```ts
import { previewTransfer, postTransfer, mapTransferError, type TransferPreview, type TransferBody } from '../lib/transfer'
import ModeConfirmDialog from './ModeConfirmDialog.vue'
```

（即把原 `import { previewTransfer, mapTransferError, type TransferPreview } ...` 一行替换为上面第一行，并加第二行组件 import。）

在 `closeFlow` 之后追加编排函数：

```ts
// 对话框确认：组装 TransferBody（single↔multi 无 surviving；multi→single 单台带 surviving）。
async function onConfirm(migrateUmos: string[]) {
  const body: TransferBody = { target_mode: target.value, migrate_umos: migrateUmos, purge_others: false }
  if (target.value === 'single') body.surviving_server_id = survivingId.value
  await runTransfer(body)
}

// 统一 POST 编排：ok → applied(config) + 成功/告警 toast；ok:false 抛 BusinessError → 错误 toast（模式不变）。
async function runTransfer(body: TransferBody) {
  working.value = true
  try {
    const res = await postTransfer(body)
    emit('applied', res.config)
    const toMode = res.summary.to === 'single' ? '单服务器' : '多服务器'
    let msg = `已切换到${toMode}模式；迁移 ${res.summary.migrated} 个群`
    const purgedN = Object.keys(res.summary.purged ?? {}).length
    if (purgedN) msg += `，清理 ${purgedN} 台数据`
    let warn = false
    if (res.warnings?.cleared_group_servers === false) { msg += '；源介质清理未尽，切回多世界前请人工核查'; warn = true }
    const failed = res.warnings?.purge_failed ?? []
    if (failed.length) { msg += `；${failed.length} 台数据清理失败，可到孤儿清理稍后重试`; warn = true }
    emit('notify', msg, warn)
  } catch (e) {
    emit('notify', mapTransferError(e), true) // ok:false → 模式不变
  } finally {
    working.value = false
    closeFlow()
  }
}
```

在模板 `.mode-transfer` `<section>` 内、注释行处渲染对话框：

```html
    <ModeConfirmDialog v-if="flow === 'confirm' && preview" :target="target" :preview="preview"
      :surviving-id="survivingId" @confirm="onConfirm" @cancel="closeFlow" />
    <!-- T3 渲染 <TransferWizard v-if="flow === 'wizard' && preview"> -->
```

- [ ] **Step 8: 跑测试确认通过 + 全前端**

Run: `cd frontend && npx vitest run src/components/ModeTransfer.test.ts src/components/ModeConfirmDialog.test.ts`
Expected: PASS。

Run: `cd frontend && npx vitest run`
Expected: 全绿。

- [ ] **Step 9: 构建 no-drift + 提交**

Run: `cd frontend && npm run build`
Expected: 成功、LF。

```bash
git add frontend/src/components/ModeConfirmDialog.vue frontend/src/components/ModeConfirmDialog.test.ts \
  frontend/src/components/ModeTransfer.vue frontend/src/components/ModeTransfer.test.ts pages/settings
git commit -m "feat: 模式确认对话框 + ModeTransfer POST 编排（失败不留半态）"
```

---

### Task 3: 转移向导 `TransferWizard.vue` + `ModeTransfer` 向导流（multi→single 多台）

**Files:**
- Create: `frontend/src/components/TransferWizard.vue`
- Modify: `frontend/src/components/ModeTransfer.vue`（渲染 `flow==='wizard'` 向导 + `onWizardConfirm`）
- Test: `frontend/src/components/TransferWizard.test.ts`（新建）、`frontend/src/components/ModeTransfer.test.ts`（追加向导流用例）

**Interfaces:**
- Consumes: T1 `TransferPreview`（`ready_servers` + `bindings`）；`ModeTransfer` 的 `serverNames` prop（算「所有非 surviving 台」，含非就绪）。
- Produces（`TransferWizard.vue`）：props `{preview:TransferPreview, serverNames:string[]}`；emits `confirm({surviving_server_id:string, migrate_umos:string[], purge_others:boolean})` / `cancel`。四步：①选保留台（仅 `ready_servers`）②迁移群（已有权默认勾/将获新权默认不勾，随保留台变更重置）③其余保留/删除 ④摘要（删除台数 = `serverNames − surviving`，含非就绪）+ **删除侧勾选闸禁用确认**。
- Produces（`ModeTransfer.vue` 追加）：`onWizardConfirm(payload)` → `runTransfer({target_mode:'single', ...payload})`。

- [ ] **Step 1: 写失败测试（TransferWizard）**

新建 `frontend/src/components/TransferWizard.test.ts`：

```ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TransferWizard from './TransferWizard.vue'

const preview = {
  ok: true,
  ready_servers: [{ server_id: 'keep', name: 'keep' }, { server_id: 'other', name: 'other' }],
  bindings: [{ umo: 'u_has', server_ids: ['keep'] }, { umo: 'u_new', server_ids: ['other'] }],
}
// serverNames 含一个非就绪台 ghost（不在 ready_servers）→ 删除台数须含它（M-c）
const serverNames = ['keep', 'other', 'ghost']

const mk = () => mount(TransferWizard, { props: { preview, serverNames } })

describe('TransferWizard', () => {
  it('步1 选保留台后可下一步；步2 已有权默认勾、将获新权默认不勾', async () => {
    const w = mk()
    // 步1：选 keep
    await w.findAll('input[type="radio"]')[0].setValue() // 第一个 radio = keep
    await w.get('button[data-act="next"]').trigger('click')
    // 步2：u_has(已有 keep 权)默认勾、u_new(仅 other)默认不勾
    const boxes = w.findAll('input[type="checkbox"]')
    expect((boxes[0].element as HTMLInputElement).checked).toBe(true) // u_has
    expect((boxes[1].element as HTMLInputElement).checked).toBe(false) // u_new
  })

  it('删除侧：摘要页勾选闸勾选前确认禁用、勾选后启用；删除台数含非就绪 ghost', async () => {
    const w = mk()
    await w.findAll('input[type="radio"]')[0].setValue() // 选 keep
    await w.get('button[data-act="next"]').trigger('click') // → 步2
    await w.get('button[data-act="next"]').trigger('click') // → 步3
    // 步3：选「删除其余」
    const step3Radios = w.findAll('input[type="radio"]')
    await step3Radios[step3Radios.length - 1].setValue() // 删除选项
    await w.get('button[data-act="next"]').trigger('click') // → 步4 摘要
    // 删除台数 = serverNames − surviving = other + ghost = 2（含非就绪 ghost）
    expect(w.text()).toContain('2')
    expect(w.text()).toContain('ghost')
    // 勾选闸前禁用
    const confirmBtn = w.get('button[data-act="confirm"]')
    expect((confirmBtn.element as HTMLButtonElement).disabled).toBe(true)
    await w.get('input[data-act="ack"]').setValue(true)
    expect((confirmBtn.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('删除侧确认 → emit payload（purge_others=true、含勾选迁移群）', async () => {
    const w = mk()
    await w.findAll('input[type="radio"]')[0].setValue()
    await w.get('button[data-act="next"]').trigger('click')
    await w.get('button[data-act="next"]').trigger('click')
    const step3Radios = w.findAll('input[type="radio"]')
    await step3Radios[step3Radios.length - 1].setValue() // 删除
    await w.get('button[data-act="next"]').trigger('click')
    await w.get('input[data-act="ack"]').setValue(true)
    await w.get('button[data-act="confirm"]').trigger('click')
    expect(w.emitted('confirm')?.[0]?.[0]).toEqual({
      surviving_server_id: 'keep', migrate_umos: ['u_has'], purge_others: true,
    })
  })

  it('保留侧：无需勾选闸即可确认，purge_others=false', async () => {
    const w = mk()
    await w.findAll('input[type="radio"]')[0].setValue()
    await w.get('button[data-act="next"]').trigger('click')
    await w.get('button[data-act="next"]').trigger('click')
    const step3Radios = w.findAll('input[type="radio"]')
    await step3Radios[step3Radios.length - 2].setValue() // 保留选项
    await w.get('button[data-act="next"]').trigger('click')
    expect((w.get('button[data-act="confirm"]').element as HTMLButtonElement).disabled).toBe(false)
    await w.get('button[data-act="confirm"]').trigger('click')
    expect(w.emitted('confirm')?.[0]?.[0]).toMatchObject({ surviving_server_id: 'keep', purge_others: false })
  })

  it('cancel emit cancel', async () => {
    const w = mk()
    await w.get('button[data-act="cancel"]').trigger('click')
    expect(w.emitted('cancel')).toBeTruthy()
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/components/TransferWizard.test.ts`
Expected: FAIL —— `Failed to resolve import './TransferWizard.vue'`。

- [ ] **Step 3: 实现 `TransferWizard.vue`**

新建 `frontend/src/components/TransferWizard.vue`：

```vue
<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import type { TransferPreview } from '../lib/transfer'

const props = defineProps<{ preview: TransferPreview; serverNames: string[] }>()
const emit = defineEmits<{
  (e: 'confirm', payload: { surviving_server_id: string; migrate_umos: string[]; purge_others: boolean }): void
  (e: 'cancel'): void
}>()

const step = ref(1)
const survivingId = ref('')
const purgeOthers = ref<boolean | null>(null) // 步3：true=删除、false=保留、null=未选
const deleteAck = ref(false)
const checked = reactive<Record<string, boolean>>({})

interface Row { umo: string; hasNew: boolean }
const readyServers = computed(() => props.preview.ready_servers ?? [])
const rows = computed<Row[]>(() => (props.preview.bindings ?? []).map((b) => ({
  umo: b.umo, hasNew: !b.server_ids.includes(survivingId.value),
})))

// 选定/变更保留台 → 重置迁移默认勾（已有权勾、将获新权不勾）
watch(survivingId, () => {
  for (const k of Object.keys(checked)) delete checked[k]
  for (const r of rows.value) checked[r.umo] = !r.hasNew
})

const migrateUmos = computed(() => rows.value.filter((r) => checked[r.umo]).map((r) => r.umo))
const newCount = computed(() => rows.value.filter((r) => checked[r.umo] && r.hasNew).length)
// 删除台 = 所有非 surviving 台（含非就绪但 DB 有历史的台，M-c）——从全部 serverNames 算
const deleteNames = computed(() => props.serverNames.filter((n) => n !== survivingId.value))
const canConfirm = computed(() => purgeOthers.value !== null && (purgeOthers.value === false || deleteAck.value))

function next() { if (step.value < 4) step.value++ }
function back() { if (step.value > 1) step.value-- }
function confirm() {
  if (!canConfirm.value) return
  emit('confirm', {
    surviving_server_id: survivingId.value,
    migrate_umos: migrateUmos.value,
    purge_others: purgeOthers.value === true,
  })
}
</script>

<template>
  <div class="modal-backdrop">
    <div class="modal wizard">
      <h3>切换到单服务器模式（多台）</h3>

      <section v-if="step === 1">
        <p class="lead">选择切换后要保留的服务器（仅就绪服务器可选）：</p>
        <ul class="rows">
          <li v-for="s in readyServers" :key="s.server_id">
            <label><input type="radio" name="surv" :value="s.server_id"
              :checked="survivingId === s.server_id" @change="survivingId = s.server_id" /> {{ s.name }}</label>
          </li>
        </ul>
        <div class="actions">
          <button class="ghost" data-act="cancel" @click="emit('cancel')">取消</button>
          <button class="pw-primary" data-act="next" :disabled="!survivingId" @click="next">下一步</button>
        </div>
      </section>

      <section v-else-if="step === 2">
        <p class="lead">勾选要迁移到保留服务器的授权群（已有权默认勾选，将获新权默认不勾）：</p>
        <ul v-if="rows.length" class="rows">
          <li v-for="r in rows" :key="r.umo">
            <label><input type="checkbox" :checked="checked[r.umo]"
              @change="checked[r.umo] = ($event.target as HTMLInputElement).checked" />
              <span class="mono">{{ r.umo }}</span>
              <span v-if="r.hasNew" class="tag-new">将获新权</span>
              <span v-else class="tag-has">已有权</span></label>
          </li>
        </ul>
        <p v-else class="muted">没有可迁移的授权群。</p>
        <div class="actions">
          <button class="ghost" data-act="back" @click="back">上一步</button>
          <button class="pw-primary" data-act="next" @click="next">下一步</button>
        </div>
      </section>

      <section v-else-if="step === 3">
        <p class="lead">如何处理其余服务器（{{ deleteNames.length }} 台）？</p>
        <label class="opt"><input type="radio" name="others" :checked="purgeOthers === false"
          @change="purgeOthers = false" /> 保留（仅退出多服务器模式，数据留存）</label>
        <label class="opt danger"><input type="radio" name="others" :checked="purgeOthers === true"
          @change="purgeOthers = true" /> 永久删除其余服务器及其全部历史数据（不可恢复）</label>
        <div class="actions">
          <button class="ghost" data-act="back" @click="back">上一步</button>
          <button class="pw-primary" data-act="next" :disabled="purgeOthers === null" @click="next">下一步</button>
        </div>
      </section>

      <section v-else>
        <p class="lead">请确认以下操作：</p>
        <ul class="summary">
          <li>保留服务器：<b>{{ survivingId }}</b></li>
          <li>迁移授权群：<b>{{ migrateUmos.length }}</b> 个（其中新授权 {{ newCount }} 个）</li>
          <li v-if="purgeOthers">永久删除：<b class="danger-text">{{ deleteNames.length }}</b> 台及其全部历史数据</li>
          <li v-else>其余 {{ deleteNames.length }} 台：保留数据</li>
        </ul>
        <div v-if="purgeOthers" class="delete-box">
          <p class="danger-text">将永久删除以下服务器及其全部历史数据，不可恢复：</p>
          <p class="mono">{{ deleteNames.join('、') }}</p>
          <label class="ack"><input type="checkbox" data-act="ack" :checked="deleteAck"
            @change="deleteAck = ($event.target as HTMLInputElement).checked" /> 我了解此操作不可恢复</label>
        </div>
        <div class="actions">
          <button class="ghost" data-act="back" @click="back">上一步</button>
          <button class="pw-primary" data-act="confirm" :disabled="!canConfirm" @click="confirm">确认切换</button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, .45); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal { background: var(--card); border: 1px solid var(--rule); border-radius: var(--r); padding: 20px 22px; width: min(600px, 92vw); max-height: 86vh; overflow: auto; display: flex; flex-direction: column; gap: 12px; }
.modal h3 { margin: 0; font-size: 15px; }
.lead { margin: 0; font-size: 12.5px; color: var(--ink-2); line-height: 1.55; }
.muted { margin: 0; font-size: 12.5px; color: var(--ink-2); }
.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.rows label, .opt { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
.opt { padding: 6px 0; }
.mono { font-family: ui-monospace, monospace; }
.tag-new { font-size: 11px; color: var(--warn); border: 1px solid var(--warn); border-radius: 4px; padding: 0 5px; }
.tag-has { font-size: 11px; color: var(--ink-2); border: 1px solid var(--rule); border-radius: 4px; padding: 0 5px; }
.summary { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 5px; font-size: 12.5px; }
.danger-text { color: var(--warn); font-weight: 600; }
.delete-box { border: 1px solid var(--warn); border-radius: var(--r); padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
.delete-box .ack { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
.actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 4px; }
.actions button { padding: 6px 14px; border-radius: var(--r); cursor: pointer; }
.actions button:disabled { opacity: .5; cursor: not-allowed; }
.ghost { background: transparent; border: 1px solid var(--rule); color: var(--ink); }
</style>
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/components/TransferWizard.test.ts`
Expected: PASS（5 passed）。

- [ ] **Step 5: 写失败测试（ModeTransfer 向导流）**

在 `frontend/src/components/ModeTransfer.test.ts` 追加：

```ts
  it('multi→single 多台 → flow=wizard、向导确认 POST body 带 purge_others', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true,
      ready_servers: [{ server_id: 'keep', name: 'keep' }, { server_id: 'other', name: 'other' }],
      bindings: [{ umo: 'u1', server_ids: ['keep'] }] })
    const apiPost = vi.fn().mockResolvedValue({ ok: true, config: {}, warnings: {},
      summary: { from: 'multi', to: 'single', surviving: 'keep', migrated: 1, purged: { other: {} }, failed_server_ids: [] } })
    setBridge({ apiGet, apiPost })
    const w = mk('multi', false, ['keep', 'other'])
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    const wiz = w.findComponent({ name: 'TransferWizard' })
    expect(wiz.exists()).toBe(true)
    wiz.vm.$emit('confirm', { surviving_server_id: 'keep', migrate_umos: ['u1'], purge_others: true })
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('mode/transfer',
      { target_mode: 'single', surviving_server_id: 'keep', migrate_umos: ['u1'], purge_others: true })
    expect(w.emitted('applied')).toBeTruthy()
  })

  it('向导 cancel → 关闭子流、无 POST', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true,
      ready_servers: [{ server_id: 'a', name: 'a' }, { server_id: 'b', name: 'b' }], bindings: [] })
    const apiPost = vi.fn()
    setBridge({ apiGet, apiPost })
    const w = mk('multi')
    await w.get('button[data-act="switch"]').trigger('click'); await flushPromises()
    w.findComponent({ name: 'TransferWizard' }).vm.$emit('cancel'); await flushPromises()
    expect((w.vm as any).flow).toBe('idle')
    expect(apiPost).not.toHaveBeenCalled()
  })
```

- [ ] **Step 6: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/components/ModeTransfer.test.ts`
Expected: FAIL —— `TransferWizard` 未渲染（`wiz.exists()` false）。

- [ ] **Step 7: `ModeTransfer.vue` 加向导渲染 + 回调**

在 import 段补 `TransferWizard`：

```ts
import TransferWizard from './TransferWizard.vue'
```

在 `onConfirm` 之后追加向导回调：

```ts
// 多台向导确认：payload 已含 surviving/migrate/purge，直接组装 single 目标 body。
async function onWizardConfirm(payload: { surviving_server_id: string; migrate_umos: string[]; purge_others: boolean }) {
  await runTransfer({ target_mode: 'single', ...payload })
}
```

在模板对话框行之后、替换 T3 占位注释为向导渲染：

```html
    <TransferWizard v-if="flow === 'wizard' && preview" :preview="preview" :server-names="serverNames"
      @confirm="onWizardConfirm" @cancel="closeFlow" />
```

- [ ] **Step 8: 跑测试确认通过 + 全前端**

Run: `cd frontend && npx vitest run src/components/ModeTransfer.test.ts src/components/TransferWizard.test.ts`
Expected: PASS。

Run: `cd frontend && npx vitest run`
Expected: 全绿。

- [ ] **Step 9: 构建 no-drift + 提交**

Run: `cd frontend && npm run build`
Expected: 成功、LF。

```bash
git add frontend/src/components/TransferWizard.vue frontend/src/components/TransferWizard.test.ts \
  frontend/src/components/ModeTransfer.vue frontend/src/components/ModeTransfer.test.ts pages/settings
git commit -m "feat: 多台转移向导 TransferWizard + 删除侧强确认勾选闸"
```

---

### Task 4: 孤儿清理入口 `OrphanCleanup.vue`

**Files:**
- Create: `frontend/src/components/OrphanCleanup.vue`
- Modify: `frontend/src/components/SettingsPanel.vue`（access 章接线 `OrphanCleanup`）
- Test: `frontend/src/components/OrphanCleanup.test.ts`（新建）

**Interfaces:**
- Consumes: T1 `listOrphans`/`purgeOrphans`/`mapTransferError`。
- Produces（`OrphanCleanup.vue`）：无 props；emits `notify(msg:string, error:boolean)`。on mount 拉 `listOrphans`；有孤儿才渲染小节 + 勾选闸「我了解此操作不可恢复」+ 清理按钮（`purgeOrphans()` 不传 server_ids，后端重算清全部）；清理后再拉列表刷新。**不信客户端**：前端不传 server_id、列表仅供参考。

- [ ] **Step 1: 写失败测试**

新建 `frontend/src/components/OrphanCleanup.test.ts`（用与既有测试一致的 window 桥 mock，避免 ESM 命名空间 spy 的不确定性；`listOrphans`→`apiGet('mode/orphans')`、`purgeOrphans()`→`apiPost('mode/orphans/purge', {})`）：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import OrphanCleanup from './OrphanCleanup.vue'

function setBridge(impl: Partial<AstrBotBridge>) {
  window.AstrBotPluginPage = { ready: () => Promise.resolve(), apiGet: vi.fn(), apiPost: vi.fn(), ...impl }
}

describe('OrphanCleanup', () => {
  beforeEach(() => { delete (window as any).AstrBotPluginPage })

  it('有孤儿 → 渲染列表 + 勾选闸；勾选前清理按钮禁用', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, orphans: ['ghost', 'gone'] }) })
    const w = mount(OrphanCleanup); await flushPromises()
    expect(w.text()).toContain('ghost')
    expect(w.text()).toContain('残留数据清理')
    const btn = w.get('button[data-act="purge"]')
    expect((btn.element as HTMLButtonElement).disabled).toBe(true)
    await w.get('input[data-act="ack"]').setValue(true)
    expect((btn.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('无孤儿 → 小节不渲染', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, orphans: [] }) })
    const w = mount(OrphanCleanup); await flushPromises()
    expect(w.text()).not.toContain('残留数据清理')
  })

  it('restarting → 视为无孤儿、不渲染', async () => {
    setBridge({ apiGet: vi.fn().mockResolvedValue({ ok: true, orphans: [], restarting: true }) })
    const w = mount(OrphanCleanup); await flushPromises()
    expect(w.text()).not.toContain('残留数据清理')
  })

  it('确认清理 → apiPost mode/orphans/purge 无 body + notify + 刷新列表', async () => {
    const apiGet = vi.fn()
      .mockResolvedValueOnce({ ok: true, orphans: ['ghost'] })   // mount
      .mockResolvedValueOnce({ ok: true, orphans: [] })          // 清理后刷新
    const apiPost = vi.fn().mockResolvedValue({ ok: true, purged: { ghost: { worlds: 1 } }, rejected: [], failed_server_ids: [] })
    setBridge({ apiGet, apiPost })
    const w = mount(OrphanCleanup); await flushPromises()
    await w.get('input[data-act="ack"]').setValue(true)
    await w.get('button[data-act="purge"]').trigger('click'); await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('mode/orphans/purge', {}) // 无 server_ids
    expect(apiGet).toHaveBeenCalledTimes(2) // mount + 刷新
    expect((w.emitted('notify')?.at(-1)?.[1])).toBe(false) // 成功
    expect(w.text()).not.toContain('残留数据清理') // 刷新后空
  })

  it('部分失败 failed_server_ids → 告警 notify(error)', async () => {
    const apiGet = vi.fn().mockResolvedValue({ ok: true, orphans: ['ghost', 'bad'] })
    const apiPost = vi.fn().mockResolvedValue({ ok: true, purged: { ghost: {} }, rejected: [], failed_server_ids: ['bad'] })
    setBridge({ apiGet, apiPost })
    const w = mount(OrphanCleanup); await flushPromises()
    await w.get('input[data-act="ack"]').setValue(true)
    await w.get('button[data-act="purge"]').trigger('click'); await flushPromises()
    expect((w.emitted('notify')?.at(-1)?.[0] as string)).toContain('失败')
    expect((w.emitted('notify')?.at(-1)?.[1])).toBe(true)
  })
})
```

> 说明：`purgeOrphans()` 无参调 `apiPost('mode/orphans/purge', {})`，桥 mock 直接断言此调用；`listOrphans` 用 `mockResolvedValueOnce` 链模拟「mount 列 → 清理后刷新为空」。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/components/OrphanCleanup.test.ts`
Expected: FAIL —— `Failed to resolve import './OrphanCleanup.vue'`。

- [ ] **Step 3: 实现 `OrphanCleanup.vue`**

新建 `frontend/src/components/OrphanCleanup.vue`：

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listOrphans, purgeOrphans, mapTransferError } from '../lib/transfer'

const emit = defineEmits<{ (e: 'notify', msg: string, error: boolean): void }>()
const orphans = ref<string[]>([])
const loaded = ref(false)
const ack = ref(false)
const working = ref(false)

async function refresh() {
  try {
    const r = await listOrphans()
    orphans.value = r.restarting ? [] : (r.orphans ?? [])
  } catch { orphans.value = [] }
  loaded.value = true
}
onMounted(refresh)

// 清理：不传 server_ids，后端持锁现场重算孤儿集清全部（不信客户端）。清理后刷新列表。
async function purge() {
  if (!ack.value || working.value) return
  working.value = true
  try {
    const r = await purgeOrphans()
    const n = Object.keys(r.purged ?? {}).length
    const failed = r.failed_server_ids ?? []
    let msg = `已清理 ${n} 台残留数据`
    let warn = false
    if (failed.length) { msg += `；${failed.length} 台清理失败，可稍后重试`; warn = true }
    emit('notify', msg, warn)
    ack.value = false
    await refresh()
  } catch (e) {
    emit('notify', mapTransferError(e), true)
  } finally {
    working.value = false
  }
}
</script>

<template>
  <section v-if="loaded && orphans.length" class="orphan-cleanup">
    <div class="group-head"><span class="t">残留数据清理</span><span class="c">配置已移除但数据库仍残留的服务器</span></div>
    <p class="grouphint danger-text">以下服务器在配置中已不存在，但数据库仍有其历史数据。清理不可恢复。</p>
    <ul class="rows"><li v-for="o in orphans" :key="o" class="mono">{{ o }}</li></ul>
    <label class="ack"><input type="checkbox" data-act="ack" :checked="ack"
      @change="ack = ($event.target as HTMLInputElement).checked" /> 我了解此操作不可恢复</label>
    <button class="danger-btn" data-act="purge" :disabled="!ack || working" @click="purge">清理残留数据</button>
  </section>
</template>

<style scoped>
.orphan-cleanup { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
.danger-text { color: var(--warn); }
.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; }
.ack { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
.danger-btn { align-self: flex-start; padding: 6px 14px; border-radius: var(--r); border: 1px solid var(--warn); background: color-mix(in srgb, var(--warn) 10%, var(--card)); color: var(--warn); cursor: pointer; }
.danger-btn:disabled { opacity: .5; cursor: not-allowed; }
</style>
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/components/OrphanCleanup.test.ts`
Expected: PASS（5 passed）。

- [ ] **Step 5: 接线进 `SettingsPanel.vue`（access 章末）**

在 import 段补：

```ts
import OrphanCleanup from './OrphanCleanup.vue'
```

在 access 章块 `<template v-if="isAccess">` 内、`singleRestricted` 授权群 `<section>` **之后、`</template>` 之前**插入：

```html
        <OrphanCleanup @notify="(m, e) => toast(m, e)" />
```

（`OrphanCleanup` 自持列表拉取、无孤儿时不渲染任何内容；对既有 access 用例无文案冲突——既有 `SettingsPanel.test.ts` 的 `apiGet` mock 对 `mode/orphans` 返回配置包，`r.orphans` 缺失 → `?? []` → 空 → 小节不渲染，回归安全。）

- [ ] **Step 6: 跑 SettingsPanel 回归 + 全前端**

Run: `cd frontend && npx vitest run src/components/SettingsPanel.test.ts src/components/OrphanCleanup.test.ts`
Expected: PASS（既有 access 用例全绿——`OrphanCleanup` 无孤儿时静默、不影响文案/保存条断言）。

Run: `cd frontend && npx vitest run`
Expected: 全绿。

- [ ] **Step 7: 构建 no-drift + 提交**

Run: `cd frontend && npm run build`
Expected: 成功、LF。

```bash
git add frontend/src/components/OrphanCleanup.vue frontend/src/components/OrphanCleanup.test.ts \
  frontend/src/components/SettingsPanel.vue pages/settings
git commit -m "feat: 孤儿数据清理入口 OrphanCleanup（不信客户端 + 强确认）"
```

---

### Task 5: 文档（模式互转 + 转移引导 + 孤儿清理）+ 全库终检

**Files:**
- Modify: `docs/commands.md`（「运行模式」段追加「在设置页切换模式」小节）
- Modify: `docs/configuration.md`（routing / single_allowed_groups 段追加「模式互转（设置页）」小节）
- Test: `tests/unit/readme_test.py`（不改，作为锚点回归跑）

**Interfaces:**
- Consumes: 无代码接口——纯文档新增，不移除任何既有 `readme_test.py` 锚点短语。
- Produces: 用户可读的模式互转 / 转移向导 / 孤儿清理引导文档。

- [ ] **Step 1: 先跑锚点基线（改前留证）**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py -q`
Expected: PASS（改前全绿——作为新增文档不破锚点的对照基线）。

- [ ] **Step 2: 在 `docs/commands.md`「运行模式:单世界 / 多世界」段末追加小节**

在 `docs/commands.md` 的 `## 运行模式:单世界 / 多世界` 章节内容之后（下一个 `##` 标题之前）追加：

```markdown
### 在设置页切换模式（single ↔ multi）

除首次设置外，运行模式可在插件设置页「连接」章的**切换控件**随时更改（齿轮裸切仍容忍，但无引导、无迁移）：

- **切换按钮**按当前模式与就绪服务器数派发：
  - 单世界 → 多世界：弹**确认对话框**，列出「单世界授权群名单」中的群，默认全部勾选迁移（迁移后绑定到唯一就绪服务器）。
  - 多世界 → 单世界（1 台就绪）：弹**确认对话框**，列出各群的多世界绑定，标注「已有保留台权限」（默认勾选）/「将获新权」（默认不勾），可手动调整。
  - 多世界 → 单世界（多台就绪）：进入**转移向导**——① 选保留哪台 → ② 勾选迁移哪些群 → ③ 其余台「保留 / 永久删除（含全部历史数据，不可恢复）」→ ④ 摘要 + 强确认。删除其余台时须勾选「我了解此操作不可恢复」方可确认。
- 授权采用 **move 语义**：迁移到目标介质后清空源介质，切回原模式不会复活旧授权；未勾选的群切换后需重新授权（单世界填入授权群名单，多世界用 `/pal link` 绑定）。
- **未保存的更改**会禁用切换入口——请先保存再切换（转移只读最后保存的配置）。
- 切换失败（如群数超上限、预绑定失败、重载回滚）**不改变模式**、仅提示错误；成功但清理未尽时会切换并提示人工核查。

### 残留数据清理（孤儿服务器）

从配置中移除服务器（或多台切单台时选择删除）后，若数据库仍残留其历史数据，「连接」章底部会出现**残留数据清理**小节，列出这些孤儿服务器。勾选「我了解此操作不可恢复」后点击「清理残留数据」即可清除。清理为服务端现场重算孤儿集执行（不信任前端列表），仅删除确实已不在配置中的服务器数据，不会误删在册服务器。
```

- [ ] **Step 3: 在 `docs/configuration.md` 的 `### single_allowed_groups` 小节之后追加**

在 `docs/configuration.md` 的 `### single_allowed_groups(单世界授权群名单)` 小节内容之后（下一个 `##`/`###` 标题之前）追加：

```markdown
### 模式互转（设置页切换与授权迁移）

`world_mode` 除首次设置与齿轮裸切外，可在设置页「连接」章的切换控件更改。切换时可按需迁移授权（move 语义，切回不复活）：

- 单世界 → 多世界：把选中的 `single_allowed_groups` 群写入多世界绑定（`group_servers`）、清空单世界名单。
- 多世界 → 单世界：把选中群的绑定并入 `single_allowed_groups`、清空多世界绑定；多台就绪时可选保留一台并永久删除其余台的全部历史数据（不可恢复）。

删除其余台的数据、或从配置中移除服务器后残留的历史数据，可在「连接」章底部的「残留数据清理」小节清除（服务端重算孤儿集，只删已不在配置中的服务器数据）。
```

- [ ] **Step 4: 跑锚点回归（改后仍绿）**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/readme_test.py -q`
Expected: PASS（新增文档不移除任何既有锚点短语——`single`/`multi`/`world_mode`/`单世界`/`多世界`/`/pal link` 等仍在场）。

- [ ] **Step 5: 全库终检**

Run（前端）：
```bash
cd frontend && npx vitest run
```
Expected: 全绿（既有 + 新增 5 个测试文件）。

Run（前端构建 no-drift）：
```bash
cd frontend && npm run build
cd .. && git status --porcelain pages/settings
```
Expected: 构建成功、LF；`pages/settings` 若有改动须已在各前端任务提交（此处应为空或仅本次未提交产物——若非空则 `git add pages/settings` 并入本次提交）。

Run（后端全库——确认纯前端 + 文档改动未破后端）：
```bash
./.venv/Scripts/python.exe -m pytest -q
ruff check .
./.venv/Scripts/python.exe -m mypy palworld_terminal
```
Expected: pytest 全绿（含 Phase 2A 后端测试，若已在同分支）；ruff `All checks passed!`；mypy `Success`。

Run（版本未动哨兵）：
```bash
git diff --stat main -- metadata.yaml palworld_terminal/__init__.py
grep -rn "0.9.7" metadata.yaml palworld_terminal/__init__.py
```
Expected: 版本源零改动、仍 `v0.9.7`。

- [ ] **Step 6: 提交**

```bash
git add docs/commands.md docs/configuration.md
git commit -m "docs: 设置页模式互转 + 转移向导 + 残留数据清理引导"
```

---

## Self-Review

### 1. Spec §5 覆盖（每条前端要求能指到某 Task）

| Spec §5 要求 | 覆盖 Task |
|---|---|
| 模式切换控件（只读 badge 升级为切换入口，按当前模式 + 就绪数派发） | T1（`ModeTransfer` `onSwitch` 按 `worldMode`×`ready_servers.length` 派 confirm/wizard/阻止）|
| preview 客户端调用封装 | T1（`lib/transfer.previewTransfer` + 全部载荷接口）|
| 确认对话框（single↔multi、multi→single 1 台）：目标模式、迁移勾选清单 | T2（`ModeConfirmDialog`）|
| single→multi 清单来自预览端点权威 `allowed_groups`（非脏 state） | T1 preview + T2 dialog（target=multi 读 `preview.allowed_groups`）|
| single→multi 脏则先保存闸 | T1（`ModeTransfer` `dirty` prop 禁用按钮 + 提示；Global Constraints 明确对两方向都门）|
| multi→single 1 台：`bindings` 标注「已有权（默认勾）/ 将获新权（默认不勾）」 | T2（`hasNew = !server_ids.includes(survivingId)`，默认勾 `!hasNew`）|
| 未勾任何群 → 告警 | T2（`checkedCount===0` 告警文案）|
| 确认 → POST `mode/transfer`（`migrate_umos`=勾选集） | T2（`onConfirm` 组装 body）|
| `res.ok===false` → 错误 toast、模式/页面不变（含 `too_many_groups`/`migrate_bind_failed`） | T2（`runTransfer` catch `BusinessError` → `mapTransferError` notify、不 applyConfig）|
| `res.ok===true` → `applyConfig(res.config)` + 回执摘要 toast，`warnings` 弹告警 | T2（`emit('applied')` + 组合 warnings 文案）+ SettingsPanel `@applied="applyConfig"`|
| 转移向导（multi→single 多台）步①选就绪保留台 | T3（步1 `ready_servers` 单选）|
| 步②迁移群（已有权默认勾/将获新权默认不勾，随保留台重置） | T3（`watch(survivingId)` 重置默认勾）|
| 步③其余保留/删除 | T3（步3 radio → `purgeOthers`）|
| 摘要页 + 删除侧勾选闸禁用确认；M = 所有非 surviving 台（含非就绪） | T3（`deleteNames = serverNames − surviving`；`canConfirm` 门 `deleteAck`）|
| 孤儿清理入口（GET 列 + POST purge 带二次确认、不信客户端） | T4（`OrphanCleanup` `listOrphans`/`purgeOrphans` 无参 + 勾选闸）|
| 失败不留半态（模式只在成功后经 applyConfig 改） | T1/T2/T3（`onSwitch` 只开子流；`runTransfer` 仅 ok 后 `emit('applied')`）；Global Constraints |
| 文档（模式互转 + 转移引导 + 孤儿清理；README 若改核锚点） | T5（`docs/commands.md`/`configuration.md` 新增小节；README 不改、跑 `readme_test.py`）|

**无缺口**。后端 4 端点属 Phase 2A、本计划仅消费（Global Constraints 已列契约）。

### 2. 占位扫描

每个改源 step 均给完整 SFC / TS 实码（无 TBD / 无「加适当错误处理」/ 无「类似上文」）；每个测试 step 给完整 Vitest 实测（`mount` / `setBridge` 或 `vi.spyOn(transfer,...)` / `$emit` 驱动 / 断言）+ 运行命令 + 期望。`ModeTransfer.vue` 跨 T1/T2/T3 additive 演进：T1 建控件 + 预览派发（子流留占位注释）、T2 加对话框渲染 + `runTransfer`、T3 加向导渲染——每处 Edit 均给完整替换代码与插入锚点，非占位描述。文档 T5 给完整 markdown 片段。

### 3. 类型一致（组件 props/emit、端点载荷字段跨任务一致）

- **`TransferBody`**（`{target_mode, surviving_server_id?, migrate_umos, purge_others}`）：T1 定义、T2 `onConfirm` 组装、T3 `onWizardConfirm` 组装、`postTransfer` 消费——字段/可选性一致；单台 confirm 与多台 wizard 都产出 `purge_others`（confirm 恒 `false`、wizard 由步3 决定）。
- **`TransferPreview`**（`ready_servers?`/`bindings?`/`allowed_groups?`/`restarting?`）：T1 定义、`ModeTransfer`/`ModeConfirmDialog`/`TransferWizard` 消费——按 target 取 `bindings`(single) 或 `allowed_groups`(multi)，一致。
- **`TransferResult`**（`config`/`warnings.cleared_group_servers`/`warnings.purge_failed`/`summary.{to,migrated,purged,failed_server_ids}`）：T1 定义、T2 `runTransfer` 逐字段消费——`warnings.purge_failed`（string[]）与 `summary.purged`（Record）区分正确。
- **`OrphanPurgeResult`**（`purged`/`rejected`/`failed_server_ids`）：T1 定义、T4 消费（`Object.keys(purged).length` 计数、`failed_server_ids` 告警）——一致。
- **组件 emit 契约**：`ModeConfirmDialog` `confirm(migrateUmos:string[])`；`TransferWizard` `confirm({surviving_server_id, migrate_umos, purge_others})`；`ModeTransfer` `applied(config)` / `notify(msg, error)`；`OrphanCleanup` `notify(msg, error)`——`ModeTransfer` 的 `onConfirm(string[])` 与 dialog emit 签名对齐、`onWizardConfirm(payload)` 与 wizard emit 对齐；SettingsPanel `@applied="applyConfig"`（`applyConfig(c)` 单参）/ `@notify="(m,e)=>toast(m,e)"`（`toast(msg,error)`）对齐。
- **预览查询串**：`previewTransfer` 生成 `mode/transfer/preview?target=single|multi`，与后端 `request.args.get("target")` 对齐（T1 测试锁定 endpoint 字符串）。

**内联修正记录**：`dirty` 闸 spec 仅点名 single→multi，本计划对两方向都门（multi→single 保留台须为已落盘 server，同样怕脏）——已在 Global Constraints 标注理由，非遗漏。
