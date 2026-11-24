<script setup lang="ts">
import { computed, ref } from 'vue'

import Switch from './primitives/switch/Switch.vue'
import { useControlField } from './useControlField'

defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{
    value?: boolean
    defaultValue?: boolean
    disabled?: boolean
    readonly?: boolean
    loading?: boolean
    size?: string
  }>(),
  { value: undefined },
)
const emit = defineEmits<{
  'update:value': [value: boolean]
  change: [value: boolean]
  blur: [event: FocusEvent]
}>()
const { field, disabled, readonly, attributes } = useControlField(props)
const local = ref(props.defaultValue ?? false)
const value = computed(() => props.value ?? local.value)
function update(next: boolean) {
  if (disabled.value || readonly.value || props.loading || next === value.value) return
  local.value = next
  emit('update:value', next)
  emit('change', next)
  field?.validate('input')
}
function blur(event: FocusEvent) {
  field?.validate('blur')
  emit('blur', event)
}
</script>
<template>
  <span class="ui-switch-wrap"
    ><Switch
      v-bind="{ ...$attrs, ...attributes }"
      :model-value="value"
      :disabled="disabled || loading"
      :aria-readonly="readonly || undefined"
      :aria-busy="loading || undefined"
      @update:model-value="update"
      @click="readonly && $event.preventDefault()"
      @keydown.space="readonly && $event.preventDefault()"
      @blur="blur" /><span v-if="value && $slots.checked"><slot name="checked" /></span
    ><span v-else-if="!value && $slots.unchecked"><slot name="unchecked" /></span
  ></span>
</template>
<style scoped>
.ui-switch-wrap {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}
</style>
