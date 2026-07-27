<script setup lang="ts">
import Field from './Field.vue'
import type { ObjectSection } from '../lib/schema'
import { t } from '../lib/i18n'

const props = defineProps<{ section: ObjectSection; modelValue: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:modelValue': [v: Record<string, unknown>] }>()
const update = (key: string, v: unknown) => emit('update:modelValue', { ...props.modelValue, [key]: v })
</script>

<template>
  <section class="entry">
    <div class="entry-head">
      <span class="entry-title">{{ t(`section.${section.key}.title`) }}</span>
      <span v-if="section.subtitle" class="entry-role">{{ t(`section.${section.key}.subtitle`) }}</span>
    </div>
    <div v-for="f in section.fields" :key="f.key" class="row">
      <span class="rlabel">{{ t(`field.${section.key}.${f.key}.label`) }}<small v-if="f.hint">{{ t(`field.${section.key}.${f.key}.hint`) }}</small></span>
      <span class="rctl">
        <Field :spec="f" :section="section.key" :model-value="modelValue[f.key]" @update:model-value="(v) => update(f.key, v)" />
      </span>
    </div>
  </section>
</template>
