<script setup lang="ts">
import { ref } from 'vue'
import { previewTransfer, mapTransferError, type TransferPreview } from '../lib/transfer'

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
</script>

<template>
  <section class="mode-transfer">
    <div class="mt-head">
      <span class="mode-badge">当前模式：{{ worldMode === 'single' ? '单服务器' : '多服务器' }}</span>
      <button class="mt-switch" data-act="switch" :disabled="dirty || working" @click="onSwitch">
        切换到{{ worldMode === 'single' ? '多' : '单' }}服务器
      </button>
      <span v-if="dirty" class="mt-hint">有未保存更改，保存后可切换</span>
    </div>
    <!-- T2 在此渲染 <ModeConfirmDialog v-if="flow === 'confirm' && preview">；
         T3 渲染 <TransferWizard v-if="flow === 'wizard' && preview"> -->
  </section>
</template>

<style scoped>
.mode-transfer { margin-bottom: 4px; }
.mt-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.mode-badge { font-size: 11.5px; color: var(--ink-2); background: color-mix(in srgb, var(--focus) 6%, var(--card)); border: 1px solid var(--rule); border-radius: var(--r); padding: 4px 10px; white-space: nowrap; }
.mt-switch { font-size: 12px; padding: 5px 12px; border-radius: var(--r); border: 1px solid var(--focus); background: color-mix(in srgb, var(--focus) 10%, var(--card)); color: var(--ink); cursor: pointer; }
.mt-switch:disabled { opacity: .5; cursor: not-allowed; }
.mt-hint { font-size: 11.5px; color: var(--warn); }
</style>
