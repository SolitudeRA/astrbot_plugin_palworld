<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { listOrphans, purgeOrphans, mapTransferError } from '../lib/transfer'
import { t } from '../lib/i18n'

// refreshKey：父组件在「转移完成 / 保存后」自增此值，令本节重拉孤儿集（兄弟组件改配置后
// 本节不再滞留旧空列表）。初次拉取由 onMounted 负责，watch 只在后续变更触发，避免挂载双拉。
const props = withDefaults(defineProps<{ refreshKey?: number }>(), { refreshKey: 0 })
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
watch(() => props.refreshKey, () => { refresh() })

// 清理：不传 server_ids，后端持锁现场重算孤儿集清全部（不信客户端）。清理后刷新列表。
async function purge() {
  if (!ack.value || working.value) return
  working.value = true
  try {
    const r = await purgeOrphans()
    const n = Object.keys(r.purged ?? {}).length
    const failed = r.failed_server_ids ?? []
    const rejected = r.rejected ?? []
    let msg = t('transfer.orphan.purged', { n })
    let warn = false
    if (failed.length) {
      msg += t('punct.semicolon') + t('transfer.orphan.failed', { n: failed.length }); warn = true
    }
    // rejected：清理前重算发现这些台服务端已不再是孤儿（TOCTOU），被跳过——提示用户其未被清理。
    if (rejected.length) {
      msg += t('punct.semicolon') + t('transfer.orphan.rejected', { n: rejected.length }); warn = true
    }
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
  <section v-if="loaded && orphans.length" class="orphan-cleanup dz-item">
    <div class="dz-info">
      <span class="dz-title">{{ t('transfer.orphan.title') }}</span>
      <span class="dz-desc">{{ t('transfer.orphan.desc') }}</span>
      <ul class="rows"><li v-for="o in orphans" :key="o" class="mono">{{ o }}</li></ul>
      <label class="ack"><input type="checkbox" data-act="ack" :checked="ack"
        @change="ack = ($event.target as HTMLInputElement).checked" /> {{ t('transfer.irreversible_ack') }}</label>
    </div>
    <button class="dz-btn" data-act="purge" :disabled="!ack || working" @click="purge">{{ t('transfer.orphan.action') }}</button>
  </section>
</template>

<style scoped>
/* 危险区行形态：容器/行/按钮样式由全局 .danger-zone/.dz-* 承载，这里只补组件私有细节 */
.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-1); }
.mono { font-size: var(--fs-caption); }
.ack { display: flex; align-items: center; gap: var(--space-2); font-size: var(--fs-caption); }
</style>
