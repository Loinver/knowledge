<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { InputProps } from './inputTypes'
import { parseNumberInput } from './inputTypes'
import { useControlField } from './useControlField'

defineOptions({ inheritAttrs: false })
const props = defineProps<{
  value?: number | null
  defaultValue?: number | null
  min?: number
  max?: number
  step?: number
  precision?: number
  disabled?: boolean
  readonly?: boolean
  clearable?: boolean
  placeholder?: string
  inputProps?: InputProps
  size?: string
  showButton?: boolean
}>()
const emit = defineEmits<{
  'update:value': [value: number | null]
  input: [value: number | null]
  change: [value: number | null]
  blur: [event: FocusEvent]
  focus: [event: FocusEvent]
  clear: []
}>()
const { t } = useI18n()
const { field, disabled, readonly, attributes } = useControlField(props)
const local = ref(props.defaultValue ?? null)
const value = computed(() => (props.value === undefined ? local.value : props.value))
const input = ref<HTMLInputElement>()
function update(text: string) {
  if (disabled.value || readonly.value) return
  const next = parseNumberInput(text, props.min, props.max, props.precision)
  if (next === value.value) {
    field?.validate('input')
    return
  }
  local.value = next
  emit('update:value', next)
  emit('input', next)
  field?.validate('input')
}
function blur(event: FocusEvent) {
  if (input.value) input.value.value = value.value == null ? '' : String(value.value)
  field?.validate('blur')
  emit('blur', event)
}
function change() {
  if (disabled.value || readonly.value) return
  field?.validate('change')
  emit('change', value.value)
}
function clear() {
  if (disabled.value || readonly.value) return
  update('')
  emit('clear')
  input.value?.focus()
}
defineExpose({
  focus: (options?: FocusOptions) => input.value?.focus(options),
  blur: () => input.value?.blur(),
})
</script>
<template>
  <div class="ui-input-wrap" :class="$attrs.class" :style="$attrs.style">
    <input
      ref="input"
      v-bind="{ ...$attrs, ...inputProps, ...attributes }"
      class="ui-number-input"
      type="number"
      :value="value ?? ''"
      :min="min"
      :max="max"
      :step="step ?? (precision === undefined ? 'any' : 10 ** -precision)"
      :disabled="disabled"
      :readonly="readonly"
      :placeholder="placeholder"
      @input="update(($event.target as HTMLInputElement).value)"
      @change="change"
      @focus="emit('focus', $event)"
      @blur="blur"
    />
    <button
      v-if="clearable && value !== null && !disabled && !readonly"
      class="ui-control-action"
      type="button"
      :aria-label="t('ds.clear')"
      @click="clear"
    >
      <X :size="16" />
    </button>
  </div>
</template>
