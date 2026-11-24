<script setup lang="ts" generic="T extends string | number | null = string | number | null">
import { RadioGroupRoot } from 'reka-ui'
import { computed, provide, ref } from 'vue'

import { radioContextKey } from './selectionTypes'
import { useControlField } from './useControlField'

const props = defineProps<{
  value?: T
  defaultValue?: T
  disabled?: boolean
  readonly?: boolean
  name?: string
  size?: string
}>()
const emit = defineEmits<{
  'update:value': [value: T]
  change: [value: T]
  blur: [event: FocusEvent]
}>()
const { field, disabled, readonly, attributes } = useControlField(props)
const local = ref<string | number | null>(props.defaultValue ?? null)
const value = computed(() => (props.value === undefined ? local.value : props.value))
provide(radioContextKey, { disabled, readonly })
function update(next: unknown) {
  if (typeof next !== 'string' && typeof next !== 'number') return
  if (disabled.value || readonly.value || next === value.value) return
  local.value = next
  emit('update:value', next as T)
  emit('change', next as T)
  field?.validate('input')
}
function blur(event: FocusEvent) {
  field?.validate('blur')
  emit('blur', event)
}
</script>
<template>
  <RadioGroupRoot
    v-bind="{ ...$attrs, ...attributes }"
    class="ui-radio-group"
    :model-value="value ?? undefined"
    :disabled="disabled || readonly"
    :aria-readonly="readonly || undefined"
    :name="name"
    @update:model-value="update"
    @focusout="blur"
    ><slot
  /></RadioGroupRoot>
</template>
<style scoped>
.ui-radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}
</style>
