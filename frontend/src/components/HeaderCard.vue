<script setup lang="ts">
import { ref, reactive } from 'vue'
import Field from './Field.vue'
import { HEADER_FIELDS } from '../lib/schema'

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
  for (const f of HEADER_FIELDS) if (f.secret) draft[f.key] = '' // secret 不回填明文
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
      <span class="nm">{{ (modelValue.name as string) || '（未命名）' }}</span>
      <span class="grow"></span>
      <span v-if="flash" class="hchip on savedflash">已暂存</span>
      <button class="headbtn del" @click="emit('delete')">移除</button>
      <button class="headbtn edit" @click="enterEdit">修改</button>
    </div>
    <div class="cbody">
      <div class="crow"><span class="ck">值</span><span class="cv">
        <span class="muted">{{ modelValue.value_set ? '已设置' : (modelValue.value_env ? '用环境变量' : '未设置') }}</span>
      </span></div>
      <div v-if="modelValue.value_env" class="crow"><span class="ck">值环境变量</span><span class="cv">{{ modelValue.value_env }}</span></div>
      <div class="crow"><span class="ck">作用域</span><span class="cv">
        <template v-if="modelValue.servers">限定 {{ modelValue.servers }}</template>
        <span v-else class="muted">所有服务器</span>
      </span></div>
    </div>
  </div>

  <!-- 编辑态 -->
  <div v-else class="card editing">
    <div class="card-head">
      <span class="idx">{{ indexLabel }}</span>
      <span class="editing-tag">编辑</span>
      <span class="grow"></span>
      <button class="headbtn cancel-card" @click="cancel">取消</button>
      <button class="headbtn save-card" @click="saveCard">完成</button>
    </div>
    <div class="cbody">
      <template v-for="f in HEADER_FIELDS" :key="f.key">
        <div class="crow">
          <span class="ck">{{ f.label }}<small v-if="f.hint">{{ f.hint }}</small></span>
          <span class="cv">
            <input v-if="f.secret" class="pw-input pw-secret" type="text"
              autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false"
              :placeholder="modelValue.value_set ? '已设置，留空则不修改' : '未设置'"
              @input="setDraft(f.key, ($event.target as HTMLInputElement).value)" />
            <Field v-else :spec="f" :model-value="draft[f.key]" @update:model-value="(v) => setDraft(f.key, v)" />
          </span>
        </div>
      </template>
    </div>
  </div>
</template>
