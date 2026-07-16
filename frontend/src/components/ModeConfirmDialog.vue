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
  <div class="helper-overlay">
    <div class="helper-panel">
      <div class="helper-head"><h3>切换到{{ target === 'single' ? '单服务器' : '多服务器' }}模式</h3></div>
      <p v-if="target === 'single'" class="lead">迁移下列群的查询授权到保留服务器；未勾选的群切换后需重新授权。</p>
      <p v-else class="lead">迁移下列授权群到多服务器绑定；未勾选的群切换后需用 /pal link 重新绑定。</p>
      <p v-if="noReadyTarget" class="warn">当前无就绪服务器可绑定，迁移的群暂时无法生效。</p>
      <ul v-if="rows.length" class="pick-list">
        <li v-for="r in rows" :key="r.umo">
          <label class="pick-row" :class="{ sel: checked[r.umo] }">
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
      <div class="helper-actions">
        <button class="ghost" data-act="cancel" @click="emit('cancel')">取消</button>
        <button class="pw-primary" data-act="confirm" @click="confirm">确认切换</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 全覆盖 helper 壳由全局 .helper-overlay/.helper-panel/.helper-head 承载 */
.lead { margin: 0; font-size: var(--fs-sm); color: var(--ink-2); line-height: var(--lh-base); }
.warn { margin: 0; font-size: var(--fs-caption); color: var(--warn); }
.muted { margin: 0; font-size: var(--fs-sm); color: var(--ink-2); }
.tag-new { font-size: var(--fs-caption); color: var(--warn); border: 1px solid var(--warn); border-radius: var(--r-sm); padding: 0 var(--space-1); }
.tag-has { font-size: var(--fs-caption); color: var(--ink-2); border: 1px solid var(--rule); border-radius: var(--r-sm); padding: 0 var(--space-1); }
</style>
