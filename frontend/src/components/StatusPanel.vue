<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { apiGet } from '../lib/bridge'
import { t } from '../lib/i18n'

interface StatusDetail {
  version?: string; description?: string; uptime_seconds?: number
  frametime_ms?: number; address?: string
  rules?: { difficulty?: string; pvp?: string; death_penalty?: string; exp_rate?: string }
}
interface StatusRow {
  name: string; ready: boolean; online?: number; max_players?: number
  fps?: number; smoothness?: string; smoothness_label?: string; world_day?: number
  peak_online_today?: number; basecamp_count?: number
  updated_at?: number; degraded?: boolean; last_ok?: number | null
  detail?: StatusDetail
}
interface StatusResp { ok: boolean; servers: StatusRow[]; restarting?: boolean }

const state = ref<'loading' | 'error' | 'ready'>('loading')
const rows = ref<StatusRow[]>([])
const restarting = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
let inflight = false

async function load() {
  if (inflight) return  // 连点刷新不并发请求
  inflight = true
  try {
    const data = await apiGet<StatusResp>('status/overview')
    restarting.value = !!data.restarting
    rows.value = data.servers ?? []
    state.value = 'ready'
    if (restarting.value) { if (timer) clearTimeout(timer); timer = setTimeout(load, 3000) }
  } catch {
    state.value = 'error'
  } finally {
    inflight = false
  }
}
onMounted(load)
onUnmounted(() => { if (timer) clearTimeout(timer) })

function ago(epochSec?: number | null): string {
  if (!epochSec) return ''
  const s = Math.max(0, Math.floor(Date.now() / 1000 - epochSec))
  if (s < 60) return t('status.ago.seconds', { n: s })
  if (s < 3600) return t('status.ago.minutes', { n: Math.floor(s / 60) })
  if (s < 86400) return t('status.ago.hours', { n: Math.floor(s / 3600) })
  return t('status.ago.days', { n: Math.floor(s / 86400) })
}
// 在线占比（进度条宽度），max 缺失/为 0 时不画
function onlineRatio(row: StatusRow): number | null {
  if (!row.max_players || row.max_players <= 0) return null
  return Math.min(100, Math.round(((row.online ?? 0) / row.max_players) * 100))
}
// 流畅度着色只读后端稳定键；smoothness_label 是本地化显示串，不参与逻辑。
function fpsClass(smoothness?: string): string {
  if (smoothness === 'smooth') return 'good'
  if (smoothness === 'moderate') return 'mid'
  return 'bad'
}
// 展开：多台默认收起、点卡头展开；仅一台时恒展开（单服务器模式必然命中）
const expandedNames = ref(new Set<string>())
const isOpen = (row: StatusRow) => rows.value.length === 1 || expandedNames.value.has(row.name)
function toggleOpen(row: StatusRow) {
  if (rows.value.length === 1) return
  const next = new Set(expandedNames.value)
  if (next.has(row.name)) next.delete(row.name)
  else next.add(row.name)
  expandedNames.value = next
}
function fmtUptime(s?: number): string {
  if (!s || s <= 0) return ''
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  if (d > 0) return t('status.uptime.days_hours', { days: d, hours: h })
  if (h > 0) return t('status.uptime.hours_minutes', { hours: h, minutes: m })
  return t('status.uptime.minutes', { minutes: m })
}
</script>

<template>
  <div class="pw-status">
    <div class="chapter-head"><h2>{{ t('status.title') }}</h2></div>
    <p class="stint"><span>{{ t('status.subtitle') }}</span><button class="ghost" @click="load">{{ t('common.refresh') }}</button></p>
    <p v-if="state === 'loading'" class="pw-muted">{{ t('status.loading') }}</p>
    <p v-else-if="state === 'error'" class="pw-error">{{ t('status.load_error') }}</p>
    <template v-else>
      <p v-if="restarting" class="pw-muted">{{ t('status.restarting') }}</p>
      <p v-if="!rows.length" class="pw-muted">{{ t('status.empty') }}</p>
      <div v-for="row in rows" :key="row.name" class="obs-card">
        <div class="oc-head" :class="{ clickable: rows.length > 1 }" @click="toggleOpen(row)">
          <span class="oc-nm">{{ row.name }}</span>
          <span v-if="!row.ready" class="chip idle">{{ t('status.chip.disconnected') }}</span>
          <span v-else-if="row.degraded" class="chip warn">{{ t('status.chip.degraded') }}</span>
          <span v-else class="chip good">{{ t('status.chip.normal') }}</span>
          <span v-if="row.ready && !row.degraded && row.updated_at" class="oc-updated">{{ t('status.updated_at', { ago: ago(row.updated_at) }) }}</span>
          <button v-if="rows.length > 1" type="button" class="oc-chev" :class="{ open: isOpen(row) }"
            :aria-expanded="isOpen(row)" :aria-label="t('status.details_aria', { name: row.name })" @click.stop="toggleOpen(row)">▸</button>
        </div>

        <template v-if="row.ready && !row.degraded">
        <div class="oc-grid">
          <div class="oc-stat">
            <span class="oc-label">{{ t('status.label.online_players') }}</span>
            <span class="oc-value">{{ row.online }}<small>/{{ row.max_players }}</small></span>
            <span v-if="onlineRatio(row) !== null" class="oc-bar" aria-hidden="true"><i :style="{ width: onlineRatio(row) + '%' }"></i></span>
            <span class="oc-sub">{{ t('status.today_peak', { n: row.peak_online_today ?? 0 }) }}</span>
          </div>
          <div class="oc-stat">
            <span class="oc-label">{{ t('status.label.fps') }}</span>
            <span class="oc-value">{{ Math.round(row.fps ?? 0) }}</span>
            <span class="oc-sub" :class="'fps-' + fpsClass(row.smoothness)">{{ row.smoothness_label }}</span>
          </div>
          <div class="oc-stat">
            <span class="oc-label">{{ t('status.label.world_time') }}</span>
            <span class="oc-value">{{ t('status.world_day', { day: row.world_day ?? 0 }) }}</span>
          </div>
          <div v-if="row.basecamp_count" class="oc-stat">
            <span class="oc-label">{{ t('status.label.basecamp_count') }}</span>
            <span class="oc-value">{{ row.basecamp_count }}</span>
          </div>
        </div>

        <!-- 详细区：展开时显示（仅一台时恒展开）；detail 缺失时静默不渲染。
             ready 且非 degraded 由外层 template 守卫，此处只判展开/有 detail——绝不参与 fallback 链 -->
        <div v-if="isOpen(row) && row.detail" class="oc-detail">
          <div class="oc-section">
            <span class="oc-label">{{ t('status.runtime_info') }}</span>
            <div class="oc-kvgrid">
              <div v-if="row.detail.version" class="oc-kv"><span>{{ t('status.version') }}</span><b class="mono">{{ row.detail.version }}</b></div>
              <div v-if="row.detail.uptime_seconds" class="oc-kv"><span>{{ t('status.uptime') }}</span><b>{{ fmtUptime(row.detail.uptime_seconds) }}</b></div>
              <div v-if="row.detail.frametime_ms" class="oc-kv"><span>{{ t('status.frametime') }}</span><b class="mono">{{ row.detail.frametime_ms }} ms</b></div>
              <div v-if="row.detail.address" class="oc-kv"><span>{{ t('status.address') }}</span><b class="mono">{{ row.detail.address }}</b></div>
              <div v-if="row.detail.description" class="oc-kv oc-kv-wide"><span>{{ t('status.description') }}</span><b>{{ row.detail.description }}</b></div>
            </div>
          </div>
          <div v-if="row.detail.rules" class="oc-section">
            <span class="oc-label">{{ t('status.world_rules') }}</span>
            <div class="oc-kvgrid">
              <div v-if="row.detail.rules.difficulty" class="oc-kv"><span>{{ t('status.difficulty') }}</span><b>{{ row.detail.rules.difficulty }}</b></div>
              <div v-if="row.detail.rules.pvp" class="oc-kv"><span>{{ t('status.pvp') }}</span><b>{{ row.detail.rules.pvp }}</b></div>
              <div v-if="row.detail.rules.death_penalty" class="oc-kv"><span>{{ t('status.death_penalty') }}</span><b>{{ row.detail.rules.death_penalty }}</b></div>
              <div v-if="row.detail.rules.exp_rate" class="oc-kv"><span>{{ t('status.exp_rate') }}</span><b class="mono">{{ row.detail.rules.exp_rate }}</b></div>
            </div>
          </div>
        </div>
        </template>

        <p v-else-if="row.ready && row.degraded" class="oc-degraded">
          <template v-if="row.last_ok">{{ t('status.last_success', { ago: ago(row.last_ok) }) }}</template>
          <template v-else>{{ t('status.no_data') }}</template>
        </p>
        <p v-else class="oc-degraded">{{ t('status.disconnected_help') }}</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* 观测卡：结构化读数网格（auto-fit 响应式折行） */
.obs-card { background: var(--card); border: 1px solid var(--rule); border-radius: var(--r); padding: var(--space-3) var(--space-4) var(--space-4); }
.obs-card + .obs-card { margin-top: var(--space-3); }
.oc-head { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; padding-bottom: var(--space-2); border-bottom: 1px dashed var(--rule); }
.oc-nm { font-size: var(--fs-heading); font-weight: var(--fw-semibold); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.oc-updated { margin-left: auto; font-size: var(--fs-caption); color: var(--ink-3); }
.oc-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: var(--space-3) var(--space-4); margin-top: var(--space-3); }
.oc-stat { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.oc-label { font-size: var(--fs-caption); color: var(--ink-3); letter-spacing: var(--track-eyebrow); }
.oc-value { font-size: var(--fs-title); font-weight: var(--fw-semibold); font-variant-numeric: tabular-nums; line-height: var(--lh-tight); }
.oc-value small { font-size: var(--fs-sm); font-weight: var(--fw-regular); color: var(--ink-3); }
.oc-sub { font-size: var(--fs-caption); color: var(--ink-3); font-variant-numeric: tabular-nums; }
.oc-bar { display: block; height: 4px; border-radius: var(--r-pill); background: var(--sink); overflow: hidden; margin-top: var(--space-1); max-width: 140px; }
.oc-bar i { display: block; height: 100%; border-radius: var(--r-pill); background: var(--flux); transition: width var(--motion-slow) var(--ease-out); }
.fps-good { color: var(--flux); font-weight: var(--fw-medium); }
.fps-mid { color: var(--warn); font-weight: var(--fw-medium); }
.fps-bad { color: var(--danger); font-weight: var(--fw-medium); }
.oc-degraded { margin: var(--space-3) 0 0; font-size: var(--fs-sm); color: var(--ink-3); }
/* 展开交互：多台时卡头可点，chevron 指示 */
.oc-head.clickable { cursor: pointer; }
.oc-chev { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; font-size: var(--fs-caption); color: var(--ink-3); background: none; border: 1px solid transparent; border-radius: var(--r-sm); cursor: pointer; transition: transform var(--motion-fast), color var(--motion-fast); }
.oc-chev.open { transform: rotate(90deg); }
.oc-chev:hover { color: var(--ink); }
.oc-chev:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
/* 详细区：kv 双列网格（窄屏 auto-fit 折行） */
.oc-detail { margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px dashed var(--rule); display: flex; flex-direction: column; gap: var(--space-3); }
.oc-section { display: flex; flex-direction: column; gap: var(--space-2); }
.oc-kvgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: var(--space-1) var(--space-4); }
.oc-kv { display: flex; align-items: baseline; gap: var(--space-2); font-size: var(--fs-sm); min-width: 0; }
.oc-kv > span { color: var(--ink-3); font-size: var(--fs-caption); flex: 0 0 auto; }
.oc-kv > b { font-weight: var(--fw-regular); color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.oc-kv-wide { grid-column: 1 / -1; }
</style>
