<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import type { TransferPreview } from '../lib/transfer'
import { t } from '../lib/i18n'

const props = defineProps<{ preview: TransferPreview; serverNames: string[] }>()
const emit = defineEmits<{
  (e: 'confirm', payload: { surviving_server_id: string; migrate_umos: string[]; purge_others: boolean }): void
  (e: 'cancel'): void
}>()

const STEPS = ['survivor', 'groups', 'disposal', 'confirm'] as const
const step = ref(1)
const survivingId = ref('')
const purgeOthers = ref<boolean | null>(null) // 步3：true=删除、false=保留、null=未选
const deleteAck = ref(false)
const checked = reactive<Record<string, boolean>>({})

interface Row { umo: string; hasNew: boolean }
const readyServers = computed(() => props.preview.ready_servers ?? [])
const rows = computed<Row[]>(() => (props.preview.bindings ?? []).map((b) => ({
  umo: b.umo, hasNew: !b.server_ids.includes(survivingId.value),
})))

// 选定/变更保留台 → 重置迁移默认勾（已有权勾、将获新权不勾）
watch(survivingId, () => {
  for (const k of Object.keys(checked)) delete checked[k]
  for (const r of rows.value) checked[r.umo] = !r.hasNew
})

// 变更「其余台」处置（删除↔保留）→ 复位删除确认勾，回到删除时须重新确认（销毁性操作不复用旧勾）
watch(purgeOthers, () => { deleteAck.value = false })

const migrateUmos = computed(() => rows.value.filter((r) => checked[r.umo]).map((r) => r.umo))
const newCount = computed(() => rows.value.filter((r) => checked[r.umo] && r.hasNew).length)
// 删除台 = 所有非 surviving 台（含非就绪但 DB 有历史的台，M-c）——从全部 serverNames 算
const deleteNames = computed(() => props.serverNames.filter((n) => n !== survivingId.value))
const canConfirm = computed(() => purgeOthers.value !== null && (purgeOthers.value === false || deleteAck.value))

function next() { if (step.value < 4) step.value++ }
function back() { if (step.value > 1) step.value-- }
function confirm() {
  if (!canConfirm.value) return
  emit('confirm', {
    surviving_server_id: survivingId.value,
    migrate_umos: migrateUmos.value,
    purge_others: purgeOthers.value === true,
  })
}
</script>

<template>
  <div class="helper-overlay">
    <div class="helper-panel">
      <div class="helper-head">
        <h3>{{ t('transfer.switch_to_mode', { mode: t('settings.mode.single') }) }}</h3>
        <div class="helper-steps" :aria-label="t('transfer.steps_aria')">
          <template v-for="(s, i) in STEPS" :key="s">
            <span class="st" :class="{ cur: step === i + 1, done: step > i + 1 }"><i>{{ step > i + 1 ? '✓' : i + 1 }}</i>{{ t(`transfer.step.${s}`) }}</span>
            <span v-if="i < STEPS.length - 1" class="sep">—</span>
          </template>
        </div>
      </div>

      <section v-if="step === 1">
        <p class="lead">{{ t('transfer.wizard.select_survivor') }}</p>
        <ul class="pick-list">
          <li v-for="s in readyServers" :key="s.server_id">
            <label class="pick-row" :class="{ sel: survivingId === s.server_id }"><input type="radio" name="surv" :value="s.server_id"
              :checked="survivingId === s.server_id" @change="survivingId = s.server_id" /> {{ s.name }}</label>
          </li>
        </ul>
        <div class="helper-actions">
          <button class="ghost" data-act="cancel" @click="emit('cancel')">{{ t('common.cancel') }}</button>
          <button class="pw-primary" data-act="next" :disabled="!survivingId" @click="next">{{ t('transfer.next') }}</button>
        </div>
      </section>

      <section v-else-if="step === 2">
        <p class="lead">{{ t('transfer.wizard.select_groups') }}</p>
        <ul v-if="rows.length" class="pick-list">
          <li v-for="r in rows" :key="r.umo">
            <label class="pick-row" :class="{ sel: checked[r.umo] }"><input type="checkbox" :checked="checked[r.umo]"
              @change="checked[r.umo] = ($event.target as HTMLInputElement).checked" />
              <span class="mono">{{ r.umo }}</span>
              <span v-if="r.hasNew" class="tag-new">{{ t('transfer.tag.new_access') }}</span>
              <span v-else class="tag-has">{{ t('transfer.tag.existing_access') }}</span></label>
          </li>
        </ul>
        <p v-else class="muted">{{ t('transfer.no_migratable_groups') }}</p>
        <div class="helper-actions">
          <button class="ghost" data-act="back" @click="back">{{ t('transfer.back') }}</button>
          <button class="pw-primary" data-act="next" @click="next">{{ t('transfer.next') }}</button>
        </div>
      </section>

      <section v-else-if="step === 3">
        <p class="lead">{{ t('transfer.wizard.handle_others', { n: deleteNames.length }) }}</p>
        <div class="pick-list">
          <label class="pick-row" :class="{ sel: purgeOthers === false }"><input type="radio" name="others" :checked="purgeOthers === false"
            @change="purgeOthers = false" /> {{ t('transfer.wizard.keep_others') }}</label>
          <label class="pick-row" :class="{ 'sel-danger': purgeOthers === true }"><input type="radio" name="others" :checked="purgeOthers === true"
            @change="purgeOthers = true" /> {{ t('transfer.wizard.purge_others') }}</label>
        </div>
        <div class="helper-actions">
          <button class="ghost" data-act="back" @click="back">{{ t('transfer.back') }}</button>
          <button class="pw-primary" data-act="next" :disabled="purgeOthers === null" @click="next">{{ t('transfer.next') }}</button>
        </div>
      </section>

      <section v-else>
        <p class="lead">{{ t('transfer.wizard.confirm_intro') }}</p>
        <ul class="summary">
          <li>{{ t('transfer.wizard.summary.survivor') }}<b>{{ survivingId }}</b></li>
          <li>{{ t('transfer.wizard.summary.migrated', { n: migrateUmos.length, new: newCount }) }}</li>
          <li v-if="purgeOthers" class="danger-text">{{ t('transfer.wizard.summary.purged', { n: deleteNames.length }) }}</li>
          <li v-else>{{ t('transfer.wizard.summary.kept', { n: deleteNames.length }) }}</li>
        </ul>
        <div v-if="purgeOthers" class="delete-box">
          <p class="danger-text">{{ t('transfer.wizard.purge_warning') }}</p>
          <p class="mono">{{ deleteNames.join(t('punct.list_separator')) }}</p>
          <label class="ack"><input type="checkbox" data-act="ack" :checked="deleteAck"
            @change="deleteAck = ($event.target as HTMLInputElement).checked" /> {{ t('transfer.irreversible_ack') }}</label>
        </div>
        <div class="helper-actions">
          <button class="ghost" data-act="back" @click="back">{{ t('transfer.back') }}</button>
          <button class="pw-primary" data-act="confirm" :disabled="!canConfirm" @click="confirm">{{ t('transfer.confirm_switch') }}</button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* 全覆盖 helper 壳由全局 .helper-overlay/.helper-panel/.helper-head/.helper-steps 承载 */
.lead { margin: 0; font-size: var(--fs-sm); color: var(--ink-2); line-height: var(--lh-base); }
.muted { margin: 0; font-size: var(--fs-sm); color: var(--ink-2); }
.tag-new { font-size: var(--fs-caption); color: var(--warn); border: 1px solid var(--warn); border-radius: var(--r-sm); padding: 0 var(--space-1); }
.tag-has { font-size: var(--fs-caption); color: var(--ink-2); border: 1px solid var(--rule); border-radius: var(--r-sm); padding: 0 var(--space-1); }
.summary { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-1); font-size: var(--fs-caption); }
.danger-text { color: var(--danger); font-weight: var(--fw-semibold); }
.delete-box { border: 1px solid var(--danger); border-radius: var(--r); padding: var(--space-3) var(--space-3); display: flex; flex-direction: column; gap: var(--space-2); }
.delete-box .ack { display: flex; align-items: center; gap: var(--space-2); font-size: var(--fs-caption); }
</style>
