<script setup lang="ts">
import { computed } from 'vue'
import {
  SelectRoot, SelectTrigger, SelectValue, SelectContent, SelectViewport, SelectItem, SelectItemText,
  SwitchRoot, SwitchThumb,
  NumberFieldRoot, NumberFieldInput, NumberFieldDecrement, NumberFieldIncrement,
} from 'reka-ui'
import type { FieldSpec } from '../lib/schema'
import { t, locale } from '../lib/i18n'

// section：字段所属 OBJECT_SECTIONS 节键（由 SectionForm 下传）。有则枚举选项经
// t('opt.<section>.<key>.<value>') 取译名；无（如 ServerCard/HeaderCard 的裸字段）或
// locale 字段（母语名恒定不译）则回退 schema 内 optionLabels 字面。
const props = defineProps<{ spec: FieldSpec; modelValue: unknown; section?: string }>()
const emit = defineEmits<{ 'update:modelValue': [v: unknown] }>()
const set = (v: unknown) => emit('update:modelValue', v)

const strVal = computed<string>({ get: () => String(props.modelValue ?? ''), set })
const boolVal = computed<boolean>({ get: () => props.modelValue === true, set })
const numVal = computed<number>({ get: () => Number(props.modelValue ?? 0), set })
const ariaLabel = computed(() => props.section
  ? t(`field.${props.section}.${props.spec.key}.label`)
  : props.spec.key)

function optLabel(opt: string): string {
  if (props.section && props.spec.key !== 'locale') return t(`opt.${props.section}.${props.spec.key}.${opt}`)
  return props.spec.optionLabels?.[opt] ?? opt
}
</script>

<template>
  <SelectRoot v-if="spec.type === 'enum'" :key="locale" v-model="strVal">
    <SelectTrigger class="pw-select-trigger" :aria-label="ariaLabel"><SelectValue /></SelectTrigger>
    <SelectContent class="pw-select-content">
      <SelectViewport>
        <SelectItem v-for="opt in spec.options" :key="opt" :value="opt" class="pw-select-item">
          <SelectItemText>{{ optLabel(opt) }}</SelectItemText>
        </SelectItem>
      </SelectViewport>
    </SelectContent>
  </SelectRoot>

  <SwitchRoot v-else-if="spec.type === 'bool'" v-model="boolVal" class="pw-switch" :aria-label="ariaLabel">
    <SwitchThumb class="pw-switch-thumb" />
  </SwitchRoot>

  <NumberFieldRoot v-else-if="spec.type === 'int' || spec.type === 'float'" v-model="numVal"
    :step="spec.type === 'float' ? 0.01 : 1" class="pw-number" :aria-label="ariaLabel">
    <NumberFieldDecrement class="pw-number-btn">−</NumberFieldDecrement>
    <NumberFieldInput class="pw-number-input" />
    <NumberFieldIncrement class="pw-number-btn">+</NumberFieldIncrement>
  </NumberFieldRoot>

  <input v-else class="pw-input" type="text" v-model.trim="strVal" :aria-label="ariaLabel" />
</template>
