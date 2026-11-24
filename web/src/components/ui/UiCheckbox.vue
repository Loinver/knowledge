<script setup lang="ts">
import { computed, ref } from 'vue'

import Checkbox from './primitives/checkbox/Checkbox.vue'
import { useControlField } from './useControlField'

defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{
    checked?: boolean
    defaultChecked?: boolean
    disabled?: boolean
    readonly?: boolean
    indeterminate?: boolean
    value?: string | number
    size?: string
  }>(),
  { checked: undefined },
)
const emit = defineEmits<{
  'update:checked': [value: boolean]
  change: [value: boolean]
  blur: [event: FocusEvent]
}>()
const { field, disabled, readonly, attributes } = useControlField(props)
const local = ref(props.defaultChecked ?? false)
const checked = computed(() => props.checked ?? local.value)
function update(value: boolean | 'indeterminate') {
  if (disabled.value || readonly.value || value === 'indeterminate' || value === checked.value)
    return
  local.value = value
  emit('update:checked', value)
  emit('change', value)
  field?.validate('input')
}
function blur(event: FocusEvent) {
  field?.validate('blur')
  emit('blur', event)
}
</script>
<template>
  <label class="ui-checkbox-label"
    ><Checkbox
      v-bind="{ ...$attrs, ...attributes }"
      :model-value="indeterminate ? 'indeterminate' : checked"
      :disabled="disabled"
      :value="value"
      :aria-readonly="readonly || undefined"
      @update:model-value="update"
      @click="readonly && $event.preventDefault()"
      @keydown.space="readonly && $event.preventDefault()"
      @blur="blur" /><span v-if="$slots.default"><slot /></span
  ></label>
</template>
<style scoped>
.ui-checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-body);
}
</style>
