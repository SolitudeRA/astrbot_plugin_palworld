<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { apiGet } from '../lib/bridge'

interface StatusRow {
  name: string; ready: boolean; online?: number; max_players?: number
  fps?: number; smoothness_label?: string; world_day?: number
  peak_online_today?: number; basecamp_count?: number
  updated_at?: number; degraded?: boolean; last_ok?: number | null
}
interface StatusResp { ok: boolean; servers: StatusRow[]; restarting?: boolean }

const state = ref<'loading' | 'error' | 'ready'>('loading')
const rows = ref<StatusRow[]>([])
const restarting = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

async function load() {
  try {
    const data = await apiGet<StatusResp>('status/overview')
    restarting.value = !!data.restarting
    rows.value = data.servers ?? []
    state.value = 'ready'
    if (restarting.value) { if (timer) clearTimeout(timer); timer = setTimeout(load, 3000) }
  } catch {
    state.value = 'error'
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
      <div v-for="row in rows" :key="row.name" class="obs">
        <span class="nm">{{ row.name }}</span>
        <span v-if="!row.ready" class="chip idle">未连接</span>
        <span v-else-if="row.degraded" class="chip warn">部分数据缺失</span>
        <span v-else class="chip good">正常</span>
        <span class="read">
          <template v-if="row.ready && !row.degraded">
            <b>在线 {{ row.online }}/{{ row.max_players }}</b><span>·</span>
            <span>FPS {{ Math.round(row.fps ?? 0) }}（{{ row.smoothness_label }}）</span><span>·</span>
            <span>第 {{ row.world_day }} 天</span><span>·</span>
            <span>今日峰值 {{ row.peak_online_today }}</span>
            <span v-if="row.basecamp_count">·</span>
            <span v-if="row.basecamp_count">据点 {{ row.basecamp_count }}</span>
            <span v-if="row.updated_at">·</span>
            <span v-if="row.updated_at">更新于 {{ ago(row.updated_at) }}</span>
          </template>
          <template v-else-if="row.ready && row.degraded">
            <span v-if="row.last_ok">最后成功更新 {{ ago(row.last_ok) }}</span>
            <span v-else>暂无可用数据</span>
          </template>
          <span v-else>未连接</span>
        </span>
      </div>
    </template>
  </div>
</template>
