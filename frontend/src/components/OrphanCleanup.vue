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
