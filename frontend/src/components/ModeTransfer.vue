<script setup lang="ts">
import { ref } from 'vue'
import { previewTransfer, postTransfer, mapTransferError, type TransferPreview, type TransferBody } from '../lib/transfer'
import ModeConfirmDialog from './ModeConfirmDialog.vue'
import TransferWizard from './TransferWizard.vue'

const props = defineProps<{ worldMode: string; dirty: boolean; serverNames: string[] }>()
const emit = defineEmits<{
  (e: 'applied', config: Record<string, unknown>): void
  (e: 'notify', msg: string, error: boolean): void
}>()

type Flow = 'idle' | 'confirm' | 'wizard'
const flow = ref<Flow>('idle')
const preview = ref<TransferPreview | null>(null)
const target = ref<'single' | 'multi'>('multi')
const survivingId = ref('')
const working = ref(false)

// 切换派发：dirty 门 → 拉预览 → 按 target×就绪数派对应子流。
// 失败不留半态：此处只开子流，模式变更等 POST ok 后由父 applyConfig 做（T2 runTransfer）。
async function onSwitch() {
  if (props.dirty || working.value) { emit('notify', '请先保存当前更改，再切换模式', true); return }
  const t: 'single' | 'multi' = props.worldMode === 'single' ? 'multi' : 'single'
  target.value = t
  working.value = true
  let pv: TransferPreview
  try { pv = await previewTransfer(t) } catch (e) { emit('notify', mapTransferError(e), true); working.value = false; return }
  working.value = false
  if (pv.restarting) { emit('notify', '系统重载中，请稍后再试', true); return }
  preview.value = pv
  const readyCount = (pv.ready_servers ?? []).length
  if (t === 'single') {
    if (readyCount === 0) { emit('notify', '没有就绪的服务器，无法切换到单服务器模式', true); return }
    if (readyCount === 1) { survivingId.value = pv.ready_servers![0].server_id; flow.value = 'confirm' }
    else { flow.value = 'wizard' }
  } else {
    flow.value = 'confirm' // single→multi 恒确认框（就绪为空时框内提示无可绑目标）
  }
}

function closeFlow() { flow.value = 'idle'; preview.value = null }

// 对话框确认：组装 TransferBody（single↔multi 无 surviving；multi→single 单台带 surviving）。
async function onConfirm(migrateUmos: string[]) {
  const body: TransferBody = { target_mode: target.value, migrate_umos: migrateUmos, purge_others: false }
  if (target.value === 'single') body.surviving_server_id = survivingId.value
  await runTransfer(body)
}

// 多台向导确认：payload 已含 surviving/migrate/purge，直接组装 single 目标 body。
async function onWizardConfirm(payload: { surviving_server_id: string; migrate_umos: string[]; purge_others: boolean }) {
  await runTransfer({ target_mode: 'single', ...payload })
}

// 统一 POST 编排：ok → applied(config) + 成功/告警 toast；ok:false 抛 BusinessError → 错误 toast（模式不变）。
async function runTransfer(body: TransferBody) {
  working.value = true
  try {
    const res = await postTransfer(body)
    emit('applied', res.config)
    const toMode = res.summary.to === 'single' ? '单服务器' : '多服务器'
    let msg = `已切换到${toMode}模式；迁移 ${res.summary.migrated} 个群`
    const purgedN = Object.keys(res.summary.purged ?? {}).length
    if (purgedN) msg += `，清理 ${purgedN} 台数据`
    let warn = false
    if (res.warnings?.cleared_group_servers === false) { msg += '；源介质清理未尽，切回多世界前请人工核查'; warn = true }
    const failed = res.warnings?.purge_failed ?? []
    if (failed.length) { msg += `；${failed.length} 台数据清理失败，可到孤儿清理稍后重试`; warn = true }
    emit('notify', msg, warn)
  } catch (e) {
    emit('notify', mapTransferError(e), true) // ok:false → 模式不变
  } finally {
    working.value = false
    closeFlow()
  }
}
</script>

<template>
  <section class="mode-transfer dz-item">
    <div class="dz-info">
      <span class="dz-title">切换运行模式</span>
      <span class="dz-desc">当前为<b class="mt-name">{{ worldMode === 'single' ? '单服务器' : '多服务器' }}</b>，{{ worldMode === 'single' ? '所有操作对应唯一服务器' : '按群绑定与切换服务器' }}。切换前会先预览影响范围，可能涉及数据迁移与清理。</span>
      <span v-if="dirty" class="mt-hint">有未保存更改，保存后可切换</span>
    </div>
    <button class="dz-btn" data-act="switch" :disabled="dirty || working" @click="onSwitch">
      切换到{{ worldMode === 'single' ? '多' : '单' }}服务器
    </button>
    <ModeConfirmDialog v-if="flow === 'confirm' && preview" :target="target" :preview="preview"
      :surviving-id="survivingId" @confirm="onConfirm" @cancel="closeFlow" />
    <TransferWizard v-if="flow === 'wizard' && preview" :preview="preview" :server-names="serverNames"
      @confirm="onWizardConfirm" @cancel="closeFlow" />
  </section>
</template>

<style scoped>
/* 危险区行形态：容器/行/按钮样式由全局 .danger-zone/.dz-* 承载，这里只补组件私有细节 */
.mt-name { font-weight: var(--fw-semibold); color: var(--ink); }
.mt-hint { font-size: var(--fs-caption); color: var(--warn); }
</style>
