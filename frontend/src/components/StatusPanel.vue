<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { apiGet } from '../lib/bridge'

interface StatusDetail {
  version?: string; description?: string; uptime_seconds?: number
  frametime_ms?: number; address?: string
  rules?: { difficulty?: string; pvp?: string; death_penalty?: string; exp_rate?: string }
}
interface StatusRow {
  name: string; ready: boolean; online?: number; max_players?: number
  fps?: number; smoothness_label?: string; world_day?: number
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
  if (s < 60) return `${s} 秒前`
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`
  return `${Math.floor(s / 86400)} 天前`
}
// 在线占比（进度条宽度），max 缺失/为 0 时不画
function onlineRatio(row: StatusRow): number | null {
  if (!row.max_players || row.max_players <= 0) return null
  return Math.min(100, Math.round(((row.online ?? 0) / row.max_players) * 100))
}
// 流畅度着色：后端 label（流畅/一般/卡顿/严重卡顿）→ 语义色类
function fpsClass(label?: string): string {
  if (label === '流畅') return 'good'
  if (label === '一般') return 'mid'
  return 'bad' // 卡顿 / 严重卡顿
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
  if (d > 0) return `${d} 天 ${h} 小时`
  if (h > 0) return `${h} 小时 ${m} 分钟`
  return `${m} 分钟`
}
</script>

<template>
  <div class="pw-status">
    <div class="chapter-head"><h2>状态</h2></div>
    <p class="stint"><span>服务器实时状态</span><button class="ghost" @click="load">刷新</button></p>
    <p v-if="state === 'loading'" class="pw-muted">加载中…</p>
    <p v-else-if="state === 'error'" class="pw-error">读取状态失败，请重试</p>
    <template v-else>
      <p v-if="restarting" class="pw-muted">正在应用新配置…</p>
      <p v-if="!rows.length" class="pw-muted">尚未添加服务器，或数据尚未采集</p>
      <div v-for="row in rows" :key="row.name" class="obs-card">
        <div class="oc-head" :class="{ clickable: rows.length > 1 }" @click="toggleOpen(row)">
          <span class="oc-nm">{{ row.name }}</span>
          <span v-if="!row.ready" class="chip idle">未连接</span>
          <span v-else-if="row.degraded" class="chip warn">部分数据缺失</span>
          <span v-else class="chip good">正常</span>
          <span v-if="row.ready && !row.degraded && row.updated_at" class="oc-updated">更新于 {{ ago(row.updated_at) }}</span>
          <button v-if="rows.length > 1" type="button" class="oc-chev" :class="{ open: isOpen(row) }"
            :aria-expanded="isOpen(row)" :aria-label="row.name + ' 详细信息'" @click.stop="toggleOpen(row)">▸</button>
        </div>

        <div v-if="row.ready && !row.degraded" class="oc-grid">
          <div class="oc-stat">
            <span class="oc-label">在线玩家</span>
            <span class="oc-value">{{ row.online }}<small>/{{ row.max_players }}</small></span>
            <span v-if="onlineRatio(row) !== null" class="oc-bar" aria-hidden="true"><i :style="{ width: onlineRatio(row) + '%' }"></i></span>
            <span class="oc-sub">今日峰值 {{ row.peak_online_today }}</span>
          </div>
          <div class="oc-stat">
            <span class="oc-label">帧率 FPS</span>
            <span class="oc-value">{{ Math.round(row.fps ?? 0) }}</span>
            <span class="oc-sub" :class="'fps-' + fpsClass(row.smoothness_label)">{{ row.smoothness_label }}</span>
          </div>
          <div class="oc-stat">
            <span class="oc-label">世界时间</span>
            <span class="oc-value">第 {{ row.world_day }} 天</span>
          </div>
          <div v-if="row.basecamp_count" class="oc-stat">
            <span class="oc-label">据点数</span>
            <span class="oc-value">{{ row.basecamp_count }}</span>
          </div>
        </div>

        <!-- 详细区：展开时显示（仅一台时恒展开）；detail 缺失时静默不渲染 -->
        <div v-if="row.ready && !row.degraded && isOpen(row) && row.detail" class="oc-detail">
          <div class="oc-section">
            <span class="oc-label">运行信息</span>
            <div class="oc-kvgrid">
              <div v-if="row.detail.version" class="oc-kv"><span>版本</span><b class="mono">{{ row.detail.version }}</b></div>
              <div v-if="row.detail.uptime_seconds" class="oc-kv"><span>运行时长</span><b>{{ fmtUptime(row.detail.uptime_seconds) }}</b></div>
              <div v-if="row.detail.frametime_ms" class="oc-kv"><span>帧时间</span><b class="mono">{{ row.detail.frametime_ms }} ms</b></div>
              <div v-if="row.detail.address" class="oc-kv"><span>地址</span><b class="mono">{{ row.detail.address }}</b></div>
              <div v-if="row.detail.description" class="oc-kv oc-kv-wide"><span>描述</span><b>{{ row.detail.description }}</b></div>
            </div>
          </div>
          <div v-if="row.detail.rules" class="oc-section">
            <span class="oc-label">世界规则</span>
            <div class="oc-kvgrid">
              <div v-if="row.detail.rules.difficulty" class="oc-kv"><span>难度</span><b>{{ row.detail.rules.difficulty }}</b></div>
              <div v-if="row.detail.rules.pvp" class="oc-kv"><span>PVP</span><b>{{ row.detail.rules.pvp }}</b></div>
              <div v-if="row.detail.rules.death_penalty" class="oc-kv"><span>死亡惩罚</span><b>{{ row.detail.rules.death_penalty }}</b></div>
              <div v-if="row.detail.rules.exp_rate" class="oc-kv"><span>经验倍率</span><b class="mono">{{ row.detail.rules.exp_rate }}</b></div>
            </div>
          </div>
        </div>

        <p v-else-if="row.ready && row.degraded" class="oc-degraded">
          <template v-if="row.last_ok">最后成功更新 {{ ago(row.last_ok) }}</template>
          <template v-else>暂无可用数据</template>
        </p>
        <p v-else class="oc-degraded">尚未建立连接，请检查「连接」页的服务器配置</p>
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
