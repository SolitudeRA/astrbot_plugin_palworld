<script setup lang="ts">
import Field from './Field.vue'
import { HEADER_FIELDS } from '../lib/schema'

const props = defineProps<{ modelValue: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:modelValue': [v: Record<string, unknown>]; delete: [] }>()
const update = (key: string, v: unknown) => emit('update:modelValue', { ...props.modelValue, [key]: v })
</script>

<template>
  <div class="pw-card">
    <template v-for="f in HEADER_FIELDS" :key="f.key">
      <div v-if="f.secret" class="pw-field">
        <label class="pw-field-label">{{ f.label }}</label>
        <input class="pw-input" type="password"
          :placeholder="modelValue.value_set ? '已设置（留空保持不变）' : '未设置'"
          :value="String(modelValue[f.key] ?? '')"
          @input="update(f.key, ($event.target as HTMLInputElement).value)" />
      </div>
      <Field v-else :spec="f" :model-value="modelValue[f.key]"
        @update:model-value="(v) => update(f.key, v)" />
    </template>
    <button class="pw-danger" @click="emit('delete')">删除</button>
  </div>
</template>
