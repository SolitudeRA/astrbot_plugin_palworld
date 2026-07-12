<script setup lang="ts">
import Field from './Field.vue'
import type { ObjectSection } from '../lib/schema'

const props = defineProps<{ section: ObjectSection; modelValue: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:modelValue': [v: Record<string, unknown>] }>()
const update = (key: string, v: unknown) => emit('update:modelValue', { ...props.modelValue, [key]: v })
</script>

<template>
  <section class="entry">
    <div class="entry-head">
      <span class="entry-title">{{ section.title }}</span>
      <span v-if="section.subtitle" class="entry-role">{{ section.subtitle }}</span>
    </div>
    <div v-for="f in section.fields" :key="f.key" class="row">
      <span class="rlabel">{{ f.label }}<small v-if="f.hint">{{ f.hint }}</small></span>
      <span class="rctl">
        <Field :spec="f" :model-value="modelValue[f.key]" @update:model-value="(v) => update(f.key, v)" />
      </span>
    </div>
  </section>
</template>
