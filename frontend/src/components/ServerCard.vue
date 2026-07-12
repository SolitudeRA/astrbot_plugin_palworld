<script setup lang="ts">
import { ref, reactive } from 'vue'
import Field from './Field.vue'
import { SERVER_FIELDS } from '../lib/schema'

const props = defineProps<{ modelValue: Record<string, unknown>; indexLabel: string }>()
const emit = defineEmits<{
  'update:modelValue': [v: Record<string, unknown>]
  delete: []
  save: [done: (ok: boolean) => void]
}>()

const mode = ref<'view' | 'edit'>(props.modelValue.__row_id ? 'view' : 'edit')
const draft = reactive<Record<string, unknown>>({})
const flash = ref(false)

function enterEdit() {
  for (const k of Object.keys(draft)) delete draft[k]
  Object.assign(draft, props.modelValue)
  for (const f of SERVER_FIELDS) if (f.secret) draft[f.key] = '' // secret 不回填明文
  mode.value = 'edit'
}
function cancel() { mode.value = 'view' }
function setDraft(key: string, v: unknown) { draft[key] = v }
function saveCard() {
  emit('update:modelValue', { ...props.modelValue, ...draft })
  emit('save', (ok: boolean) => {
    if (!ok) return // 失败留在编辑态，父已 toast 错误（flash 不触发）
    mode.value = 'view'
    flash.value = true
    setTimeout(() => { flash.value = false }, 1900)
  })
}
</script>

<template>
  <!-- 查看态 -->
  <div v-if="mode === 'view'" class="card">
    <div class="card-head">
      <span class="idx">{{ indexLabel }}</span>
      <span class="nm">{{ (modelValue.name as string) || '（未命名）' }}</span>
      <span class="hchip" :class="modelValue.enabled ? 'on' : 'off'">{{ modelValue.enabled ? '启用' : '停用' }}</span>
      <span class="grow"></span>
      <span v-if="flash" class="hchip on savedflash">已保存 ✓</span>
      <button class="headbtn del" @click="emit('delete')">移除</button>
      <button class="headbtn edit" @click="enterEdit">修改</button>
    </div>
    <div class="cbody">
      <div class="crow"><span class="ck">地址</span><span class="cv">{{ modelValue.base_url }}</span></div>
      <div class="crow"><span class="ck">用户名</span><span class="cv">{{ modelValue.username }}</span></div>
      <div v-if="modelValue.password_set" class="crow"><span class="ck">密码</span><span class="cv"><span class="muted">已设置</span></span></div>
      <div v-if="modelValue.password_env" class="crow"><span class="ck">密码变量</span><span class="cv">{{ modelValue.password_env }}</span></div>
      <div class="crow"><span class="ck">超时</span><span class="cv">{{ modelValue.timeout }} 秒</span></div>
      <div class="crow"><span class="ck">校验 TLS</span><span class="cv">{{ modelValue.verify_tls ? '是' : '否' }}</span></div>
      <div v-if="modelValue.timezone" class="crow"><span class="ck">时区</span><span class="cv">{{ modelValue.timezone }}</span></div>
    </div>
  </div>

  <!-- 编辑态 -->
  <div v-else class="card editing">
    <div class="card-head">
      <span class="idx">{{ indexLabel }}</span>
      <span class="editing-tag">编辑</span>
      <span class="grow"></span>
      <button class="headbtn cancel-card" @click="cancel">取消</button>
      <button class="headbtn save-card" @click="saveCard">保存</button>
    </div>
    <div class="cbody">
      <template v-for="f in SERVER_FIELDS" :key="f.key">
        <div class="crow">
          <span class="ck">{{ f.label }}<small v-if="f.hint">{{ f.hint }}</small></span>
          <span class="cv">
            <input v-if="f.secret" class="pw-input pw-secret" type="text"
              autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false"
              :placeholder="modelValue.password_set ? '已设置（留空保持不变）' : '未设置'"
              @input="setDraft(f.key, ($event.target as HTMLInputElement).value)" />
            <Field v-else :spec="f" :model-value="draft[f.key]" @update:model-value="(v) => setDraft(f.key, v)" />
          </span>
        </div>
      </template>
    </div>
  </div>
</template>
