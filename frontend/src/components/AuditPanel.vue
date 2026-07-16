<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiGet } from '../lib/bridge'

interface AuditRow {
  ts: number; time: string; action: string; server: string
  admin: string; target: string; success: boolean; error?: string | null
}
interface AuditResp { ok: boolean; audits: AuditRow[]; restarting?: boolean }

const state = ref<'loading' | 'error' | 'ready'>('loading')
const rows = ref<AuditRow[]>([])
const restarting = ref(false)
let inflight = false

// 客户端分页：后端已按 ts DESC + LIMIT 封顶（无游标），前端每页 10 条页码分页
const PAGE_SIZE = 10
const page = ref(1)
const totalPages = computed(() => Math.max(1, Math.ceil(rows.value.length / PAGE_SIZE)))
const visibleRows = computed(() => rows.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))
const goto = (p: number) => { page.value = Math.min(Math.max(1, p), totalPages.value) }
// 窗口式页码：首尾恒显 + 当前 ±1，间隙折叠为省略号
const pageList = computed<(number | '…')[]>(() => {
  const total = totalPages.value, cur = page.value
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const keep = new Set([1, 2, cur - 1, cur, cur + 1, total - 1, total])
  const out: (number | '…')[] = []
  for (let p = 1; p <= total; p++) {
    if (keep.has(p)) out.push(p)
    else if (out[out.length - 1] !== '…') out.push('…')
  }
  return out
})

async function load() {
  if (inflight) return  // 连点刷新不并发请求
  inflight = true
  try {
    const data = await apiGet<AuditResp>('audit/list')
    restarting.value = !!data.restarting
    rows.value = data.audits ?? []
    page.value = 1 // 刷新回第一页
    state.value = 'ready'
  } catch {
    state.value = 'error'
  } finally {
    inflight = false
  }
}
onMounted(load)
</script>

<template>
  <div class="pw-audit">
    <div class="chapter-head"><h2>审计</h2></div>
    <p class="stint"><span>管理操作记录 · 只读</span><button class="ghost" @click="load">刷新</button></p>
    <p v-if="state === 'loading'" class="pw-muted">加载中…</p>
    <div v-else-if="state === 'error'" class="state-card">
      <p class="pw-error">读取审计记录失败，请重试</p>
      <button class="ghost" @click="load">刷新</button>
    </div>
    <template v-else>
      <p v-if="restarting" class="pw-muted">正在应用新配置…</p>
      <div v-if="!rows.length" class="state-card"><p class="pw-muted">暂无管理操作记录</p></div>
      <div v-else class="pw-audit-scroll">
        <table class="pw-audit-table">
          <thead>
            <tr>
              <th>时间</th><th>管理员</th><th>动作</th><th>目标</th><th>服务器</th><th>结果</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in visibleRows" :key="`${r.ts}-${i}`">
              <td class="mono">{{ r.time }}</td>
              <td class="mono">{{ r.admin }}</td>
              <td class="act">{{ r.action }}</td>
              <td class="mono" :class="{ muted: !r.target }">{{ r.target || '—' }}</td>
              <td>{{ r.server }}</td>
              <td>
                <span v-if="r.success" class="chip good">成功</span>
                <span v-else class="chip bad" :title="r.error || ''">失败</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="totalPages > 1" class="pw-audit-foot">
          <button class="pg-btn" :disabled="page === 1" aria-label="上一页" @click="goto(page - 1)">‹</button>
          <template v-for="(p, i) in pageList" :key="i">
            <span v-if="p === '…'" class="pg-ellipsis">…</span>
            <button v-else class="pg-btn pg-num" :class="{ cur: p === page }"
              :aria-current="p === page ? 'page' : undefined" @click="goto(p)">{{ p }}</button>
          </template>
          <button class="pg-btn" :disabled="page === totalPages" aria-label="下一页" @click="goto(page + 1)">›</button>
          <span class="pg-total">共 {{ rows.length }} 条</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* 观测面表格（阶段二定稿方向）：card 外框、表头呼应 .card-head 渐变、dashed 行分隔、
   time/admin/target 等宽对齐、hover 助扫描；窄屏横向滚动兜底 */
.pw-audit { display: flex; flex-direction: column; gap: var(--space-4); }
.pw-audit-scroll { overflow-x: auto; }
.pw-audit-table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--rule); border-radius: var(--r); overflow: hidden; font-size: var(--fs-sm); }
.pw-audit-table thead th { text-align: left; background: linear-gradient(var(--raise), var(--card)); color: var(--ink-2); font-size: var(--fs-caption); font-weight: var(--fw-semibold); letter-spacing: var(--track-eyebrow); padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--rule-2); white-space: nowrap; }
.pw-audit-table tbody td { padding: var(--space-2) var(--space-3); vertical-align: middle; border-bottom: 1px dashed var(--rule); }
.pw-audit-table tbody tr:last-child td { border-bottom: none; }
.pw-audit-table tbody tr:hover { background: color-mix(in srgb, var(--focus) 6%, transparent); }
.pw-audit-table td.mono { font-size: var(--fs-caption); }
.pw-audit-table td.muted { color: var(--ink-3); }
.pw-audit-table td.act { color: var(--ink); font-weight: var(--fw-medium); }
.pw-audit-foot { display: flex; align-items: center; justify-content: center; gap: var(--space-1); padding: var(--space-2) 0; font-size: var(--fs-caption); flex-wrap: wrap; }
.pg-btn { min-width: 28px; height: 28px; padding: 0 var(--space-2); font-family: var(--sans); font-size: var(--fs-caption); font-variant-numeric: tabular-nums; color: var(--ink-2); background: none; border: 1px solid transparent; border-radius: var(--r-sm); cursor: pointer; transition: color var(--motion-fast), border-color var(--motion-fast), background var(--motion-fast); }
.pg-btn:hover:not(:disabled) { color: var(--ink); border-color: var(--rule-2); }
.pg-btn:disabled { opacity: .4; cursor: not-allowed; }
.pg-btn:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
.pg-num.cur { color: var(--on-focus); background: var(--focus); font-weight: var(--fw-semibold); }
.pg-ellipsis { color: var(--ink-3); padding: 0 2px; }
.pg-total { margin-left: var(--space-3); color: var(--ink-3); }
/* 空/错误态：卡框内居中，与观测面同语言 */
.state-card { background: var(--card); border: 1px solid var(--rule); border-radius: var(--r); padding: var(--space-8) var(--space-4); text-align: center; display: flex; flex-direction: column; align-items: center; gap: var(--space-3); }
.state-card p { margin: 0; }
</style>
