<script setup lang="ts">
import Field from './Field.vue'
import { SERVER_FIELDS } from '../lib/schema'

const props = defineProps<{ modelValue: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:modelValue': [v: Record<string, unknown>]; delete: [] }>()
const update = (key: string, v: unknown) => emit('update:modelValue', { ...props.modelValue, [key]: v })
</script>

<template>
  <div class="pw-card">
    <template v-for="f in SERVER_FIELDS" :key="f.key">
      <div v-if="f.secret" class="pw-field">
        <label class="pw-field-label">{{ f.label }}</label>
        <!-- type=text + -webkit-text-security 遮罩：绕开受限 iframe(opaque origin)对
             type=password 的剪贴板读取门控（否则 Ctrl+V 在 Chrome/Edge 无反应）；
             仍非受控、不回显 modelValue[secret]（T8 安全红线保持）。 -->
        <input class="pw-input pw-secret" type="text"
          autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false"
          :placeholder="modelValue.password_set ? '已设置（留空保持不变）' : '未设置'"
          @input="update(f.key, ($event.target as HTMLInputElement).value)" />
      </div>
      <Field v-else :spec="f" :model-value="modelValue[f.key]"
        @update:model-value="(v) => update(f.key, v)" />
    </template>
    <button class="pw-danger" @click="emit('delete')">删除</button>
  </div>
</template>
