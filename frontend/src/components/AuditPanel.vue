<script setup lang="ts">
import { ref, onMounted } from 'vue'
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

async function load() {
  if (inflight) return  // 连点刷新不并发请求
  inflight = true
  try {
    const data = await apiGet<AuditResp>('audit/list')
    restarting.value = !!data.restarting
    rows.value = data.audits ?? []
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
    <p v-else-if="state === 'error'" class="pw-error">读取审计记录失败，请重试</p>
    <template v-else>
      <p v-if="restarting" class="pw-muted">正在应用新配置…</p>
      <p v-if="!rows.length" class="pw-muted">暂无管理操作记录</p>
      <table v-else class="pw-audit-table">
        <thead>
          <tr>
            <th>时间</th><th>管理员</th><th>动作</th><th>目标</th><th>服务器</th><th>结果</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in rows" :key="`${r.ts}-${i}`">
            <td>{{ r.time }}</td>
            <td>{{ r.admin }}</td>
            <td>{{ r.action }}</td>
            <td>{{ r.target || '—' }}</td>
            <td>{{ r.server }}</td>
            <td>
              <span v-if="r.success" class="chip good">成功</span>
              <span v-else class="chip warn" :title="r.error || ''">失败</span>
            </td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>
