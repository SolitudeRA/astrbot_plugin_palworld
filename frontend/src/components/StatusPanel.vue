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
