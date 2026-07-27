<script setup lang="ts">
import { reactive, computed } from 'vue'
import type { TransferPreview } from '../lib/transfer'
import { t } from '../lib/i18n'

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
      umo: g.umo, label: g.note ? t('transfer.group_with_note', { umo: g.umo, note: g.note }) : g.umo, hasNew: false,
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
      <div class="helper-head"><h3>{{ t('transfer.switch_to_mode', { mode: t(`settings.mode.${target}`) }) }}</h3></div>
      <p v-if="target === 'single'" class="lead">{{ t('transfer.confirm.single_lead') }}</p>
      <p v-else class="lead">{{ t('transfer.confirm.multi_lead') }}</p>
      <p v-if="noReadyTarget" class="warn">{{ t('transfer.no_ready_target_warning') }}</p>
      <ul v-if="rows.length" class="pick-list">
        <li v-for="r in rows" :key="r.umo">
          <label class="pick-row" :class="{ sel: checked[r.umo] }">
            <input type="checkbox" :checked="checked[r.umo]"
              @change="checked[r.umo] = ($event.target as HTMLInputElement).checked" />
            <span class="mono">{{ r.label }}</span>
            <span v-if="r.hasNew" class="tag-new">{{ t('transfer.tag.new_access') }}</span>
            <span v-else-if="target === 'single'" class="tag-has">{{ t('transfer.tag.existing_access') }}</span>
          </label>
        </li>
      </ul>
      <p v-else class="muted">{{ t('transfer.no_migratable_groups') }}</p>
      <p v-if="rows.length && checkedCount === 0" class="warn">{{ t('transfer.none_selected_warning') }}</p>
      <div class="helper-actions">
        <button class="ghost" data-act="cancel" @click="emit('cancel')">{{ t('common.cancel') }}</button>
        <button class="pw-primary" data-act="confirm" @click="confirm">{{ t('transfer.confirm_switch') }}</button>
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
