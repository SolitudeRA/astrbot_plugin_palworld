<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { apiGet } from '../lib/bridge'

interface StatusRow { name: string; ready: boolean; online?: number; smoothness_label?: string; degraded?: boolean }
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
</script>

<template>
  <div class="pw-status">
    <button class="pw-primary" @click="load">刷新</button>
    <p v-if="state === 'loading'" class="pw-muted">加载中…</p>
    <p v-else-if="state === 'error'" class="pw-error">读取状态失败，请重试</p>
    <template v-else>
      <p v-if="restarting" class="pw-muted">插件正在重载配置…</p>
      <div v-for="row in rows" :key="row.name" class="pw-card">
        <strong>{{ row.name }}</strong>
        <div v-if="!row.ready" class="pw-muted">未就绪</div>
        <div v-else>在线 {{ row.online }} · {{ row.smoothness_label }}<span v-if="row.degraded"> · 数据缺失</span></div>
      </div>
    </template>
  </div>
</template>
