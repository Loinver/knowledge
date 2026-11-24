<script setup lang="ts">
import { AccordionRoot } from 'reka-ui'
import { computed, ref } from 'vue'

import type { SelectionKey } from './selectionTypes'
import { selectionKey } from './selectionTypes'
import { useControlField } from './useControlField'

const props = defineProps<{
  expandedNames?: SelectionKey | SelectionKey[] | null
  defaultExpandedNames?: SelectionKey | SelectionKey[] | null
  accordion?: boolean
  disabled?: boolean
  readonly?: boolean
}>()
const emit = defineEmits<{
  'update:expandedNames': [value: SelectionKey | SelectionKey[] | null]
}>()
const { field, disabled, readonly, attributes } = useControlField(props)
const local = ref(props.defaultExpandedNames ?? null)
const value = computed(() =>
  props.expandedNames === undefined ? local.value : props.expandedNames,
)
const encoded = computed(() => {
  const values = Array.isArray(value.value) ? value.value : value.value == null ? [] : [value.value]
  return props.accordion
    ? values[0] === undefined
      ? ''
      : selectionKey(values[0])
    : values.map(selectionKey)
})
function update(next: string | string[] | undefined) {
  if (disabled.value || readonly.value) return
  const decode = (key: string) => (key.startsWith('number:') ? Number(key.slice(7)) : key.slice(7))
  const result = props.accordion
    ? next
      ? decode(String(next))
      : null
    : (Array.isArray(next) ? next : []).map(decode)
  local.value = result
  emit('update:expandedNames', result)
  field?.validate('input')
}
</script>
<template>
  <AccordionRoot
    v-bind="{ ...$attrs, ...attributes, 'aria-readonly': readonly || undefined }"
    class="ui-collapse"
    :type="accordion ? 'single' : 'multiple'"
    :model-value="encoded"
    :disabled="disabled || readonly"
    collapsible
    @update:model-value="update"
    @focusout="field?.validate('blur')"
    ><slot
  /></AccordionRoot>
</template>
