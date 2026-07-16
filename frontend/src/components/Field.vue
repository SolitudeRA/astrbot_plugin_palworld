<script setup lang="ts">
import { computed } from 'vue'
import {
  SelectRoot, SelectTrigger, SelectValue, SelectContent, SelectViewport, SelectItem, SelectItemText,
  SwitchRoot, SwitchThumb,
  NumberFieldRoot, NumberFieldInput, NumberFieldDecrement, NumberFieldIncrement,
} from 'reka-ui'
import type { FieldSpec } from '../lib/schema'

const props = defineProps<{ spec: FieldSpec; modelValue: unknown }>()
const emit = defineEmits<{ 'update:modelValue': [v: unknown] }>()
const set = (v: unknown) => emit('update:modelValue', v)

const strVal = computed<string>({ get: () => String(props.modelValue ?? ''), set })
const boolVal = computed<boolean>({ get: () => props.modelValue === true, set })
const numVal = computed<number>({ get: () => Number(props.modelValue ?? 0), set })
</script>

<template>
  <SelectRoot v-if="spec.type === 'enum'" v-model="strVal">
    <SelectTrigger class="pw-select-trigger" :aria-label="spec.key"><SelectValue /></SelectTrigger>
    <SelectContent class="pw-select-content">
      <SelectViewport>
        <SelectItem v-for="opt in spec.options" :key="opt" :value="opt" class="pw-select-item">
          <SelectItemText>{{ spec.optionLabels?.[opt] ?? opt }}</SelectItemText>
        </SelectItem>
      </SelectViewport>
    </SelectContent>
  </SelectRoot>

  <SwitchRoot v-else-if="spec.type === 'bool'" v-model="boolVal" class="pw-switch">
    <SwitchThumb class="pw-switch-thumb" />
  </SwitchRoot>

  <NumberFieldRoot v-else-if="spec.type === 'int' || spec.type === 'float'" v-model="numVal"
    :step="spec.type === 'float' ? 0.01 : 1" class="pw-number">
    <NumberFieldDecrement class="pw-number-btn">−</NumberFieldDecrement>
    <NumberFieldInput class="pw-number-input" />
    <NumberFieldIncrement class="pw-number-btn">+</NumberFieldIncrement>
  </NumberFieldRoot>

  <input v-else class="pw-input" type="text" v-model.trim="strVal" />
</template>
