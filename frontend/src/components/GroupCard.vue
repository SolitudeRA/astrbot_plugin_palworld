<script setup lang="ts">
import { ref, reactive } from 'vue'

const props = defineProps<{ modelValue: Record<string, unknown>; indexLabel: string }>()
const emit = defineEmits<{
  'update:modelValue': [v: Record<string, unknown>]
  delete: []
}>()

const mode = ref<'view' | 'edit'>(props.modelValue.__row_id ? 'view' : 'edit')
// 新增且从未「完成」过的行,「取消」应等同移除(否则留下一张空白幽灵卡,
// 统一保存时被静默提交);「完成」过一次即视为用户确认保留
const freshNew = ref(!props.modelValue.__row_id)
const draft = reactive<Record<string, unknown>>({})
const flash = ref(false)

function enterEdit() {
  for (const k of Object.keys(draft)) delete draft[k]
  Object.assign(draft, props.modelValue)
  mode.value = 'edit'
}
function cancel() {
  if (freshNew.value) { emit('delete'); return }
  mode.value = 'view'
}
function setDraft(key: string, v: unknown) { draft[key] = v }
function saveCard() {
  freshNew.value = false
  // 无任何改动的「完成」只回查看态,不 emit(避免误置「有未保存的更改」)
  const changed = Object.keys(draft).some((k) => draft[k] !== props.modelValue[k])
  mode.value = 'view'
  if (!changed) return
  // 只暂存到页面工作态,不落库——统一由底部「保存设置」提交
  emit('update:modelValue', { ...props.modelValue, ...draft })
  flash.value = true
  setTimeout(() => { flash.value = false }, 1900)
}
</script>

<template>
  <!-- 查看态 -->
  <div v-if="mode === 'view'" class="card">
    <div class="card-head">
      <span class="idx">{{ indexLabel }}</span>
      <span class="nm mono">{{ (modelValue.umo as string) || '（未填）' }}</span>
      <span class="grow"></span>
      <span v-if="flash" class="hchip on savedflash">已暂存</span>
      <button class="headbtn del" data-act="delete" @click="emit('delete')">移除</button>
      <button class="headbtn edit" data-act="edit" @click="enterEdit">修改</button>
    </div>
    <div class="cbody">
      <div class="crow"><span class="ck">标识</span><span class="cv mono">{{ (modelValue.umo as string) || '（未填）' }}</span></div>
      <div class="crow"><span class="ck">备注</span><span class="cv">
        <template v-if="modelValue.note">{{ modelValue.note }}</template>
        <span v-else class="muted">（无）</span>
      </span></div>
    </div>
  </div>

  <!-- 编辑态 -->
  <div v-else class="card editing">
    <div class="card-head">
      <span class="idx">{{ indexLabel }}</span>
      <span class="editing-tag">编辑</span>
      <span class="grow"></span>
      <button class="headbtn cancel-card" data-act="cancel" @click="cancel">取消</button>
      <button class="headbtn save-card" data-act="save" @click="saveCard">完成</button>
    </div>
    <div class="cbody">
      <div class="crow">
        <span class="ck">标识</span>
        <span class="cv">
          <input class="pw-input mono" type="text"
            autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false"
            placeholder="如 aiocqhttp:GroupMessage:123456"
            :value="(draft.umo as string) ?? ''"
            @input="setDraft('umo', ($event.target as HTMLInputElement).value)" />
        </span>
      </div>
      <div class="crow">
        <span class="ck">备注</span>
        <span class="cv">
          <input class="pw-input" type="text"
            placeholder="备注，可选"
            :value="(draft.note as string) ?? ''"
            @input="setDraft('note', ($event.target as HTMLInputElement).value)" />
        </span>
      </div>
    </div>
  </div>
</template>
