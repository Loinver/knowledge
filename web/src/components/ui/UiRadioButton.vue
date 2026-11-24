<script setup lang="ts">
import { RadioGroupItem } from 'reka-ui'
import { inject } from 'vue'

import { radioContextKey } from './selectionTypes'
import { useControlField } from './useControlField'

const props = defineProps<{
  value: string | number
  disabled?: boolean
  readonly?: boolean
  label?: string
}>()
const { field, disabled, readonly, attributes } = useControlField(props)
const group = inject(radioContextKey, undefined)
</script>
<template>
  <RadioGroupItem
    v-bind="$attrs"
    class="ui-radio-button"
    :value="value"
    :disabled="disabled || readonly || group?.disabled.value || group?.readonly.value"
    :aria-describedby="attributes['aria-describedby']"
    :aria-invalid="attributes['aria-invalid']"
    @blur="field?.validate('blur')"
    ><slot>{{ label }}</slot></RadioGroupItem
  >
</template>
<style scoped>
.ui-radio-button {
  min-height: var(--control-height);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  color: var(--foreground-secondary);
  background: var(--surface-input);
  font-size: var(--font-body);
}
.ui-radio-button[data-state='checked'] {
  color: var(--action-primary);
  border-color: var(--action-primary);
  background: var(--action-soft);
}
.ui-radio-button:disabled {
  color: var(--foreground-disabled);
}
</style>
