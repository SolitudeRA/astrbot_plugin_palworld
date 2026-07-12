<script setup lang="ts">
import Field from './Field.vue'
import type { ObjectSection } from '../lib/schema'

const props = defineProps<{ section: ObjectSection; modelValue: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:modelValue': [v: Record<string, unknown>] }>()
const update = (key: string, v: unknown) => emit('update:modelValue', { ...props.modelValue, [key]: v })
</script>

<template>
  <section class="pw-section">
    <h3 class="pw-section-title">{{ section.title }}</h3>
    <Field v-for="f in section.fields" :key="f.key" :spec="f"
      :model-value="modelValue[f.key]"
      @update:model-value="(v) => update(f.key, v)" />
  </section>
</template>
