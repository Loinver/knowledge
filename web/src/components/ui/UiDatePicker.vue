<script setup lang="ts" generic="T extends number | number[] | null = number | number[] | null">
import { X } from '@lucide/vue'
import { computed, ref, useAttrs, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { InputProps } from './inputTypes'
import { formatDateInput, parseDateInput } from './inputTypes'
import { sameSelection } from './selectionTypes'
import { useControlField } from './useControlField'

defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{
    value?: T
    defaultValue?: T
    type?: 'date' | 'datetime' | 'daterange' | 'datetimerange'
    disabled?: boolean
    readonly?: boolean
    clearable?: boolean
    placeholder?: string
    inputProps?: InputProps
    size?: string
  }>(),
  { type: 'date' },
)
const emit = defineEmits<{
  'update:value': [value: T]
  change: [value: T]
  clear: []
  blur: [event: FocusEvent]
}>()
const { t } = useI18n()
const attrs = useAttrs()
const { field, disabled, readonly, attributes } = useControlField(props)
function inputAttributes(index: number) {
  const merged = { ...attrs, ...props.inputProps, ...attributes.value }
  const id = merged.id
  const label = merged['aria-label'] as string | undefined
  return {
    ...merged,
    id: index === 0 ? id : id ? `${id}-${index}` : undefined,
    'aria-label': range.value
      ? `${label ?? props.placeholder ?? t('ds.dateRange')}: ${t(index ? 'ds.endDate' : 'ds.startDate')}`
      : label,
  }
}
const local = ref<number | number[] | null>(props.defaultValue ?? null)
const value = computed(() => (props.value === undefined ? local.value : props.value))
const range = computed(() => props.type.endsWith('range'))
const datetime = computed(() => props.type.startsWith('datetime'))
const drafts = ref<string[]>([])
const editingRange = ref(false)
watch(
  [value, datetime, range],
  () => {
    if (editingRange.value && value.value === null) return
    const values = Array.isArray(value.value) ? value.value : [value.value]
    drafts.value = Array.from({ length: range.value ? 2 : 1 }, (_, index) =>
      formatDateInput(values[index], datetime.value),
    )
  },
  { immediate: true },
)
function commit(next: number | number[] | null) {
  if (disabled.value || readonly.value || sameSelection(value.value, next)) return
  local.value = next
  emit('update:value', next as T)
  emit('change', next as T)
  field?.validate('input')
}
function update(text: string, index: number) {
  if (disabled.value || readonly.value) return
  drafts.value[index] = text
  const parsed = drafts.value.map(parseDateInput)
  if (!range.value) commit(parsed[0])
  else if (parsed.every((part): part is number => part !== null) && parsed[0] <= parsed[1]) {
    editingRange.value = false
    commit(parsed)
  } else {
    editingRange.value = true
    commit(null)
    field?.validate('input')
  }
}
function clear() {
  if (disabled.value || readonly.value) return
  editingRange.value = false
  drafts.value = range.value ? ['', ''] : ['']
  commit(null)
  emit('clear')
}
function blur(event: FocusEvent) {
  field?.validate('blur')
  emit('blur', event)
}
</script>
<template>
  <div class="ui-input-wrap date-wrap" :class="$attrs.class" :style="$attrs.style">
    <input
      v-for="(_, index) in drafts"
      :key="index"
      v-bind="inputAttributes(index)"
      class="ui-date-input"
      :type="datetime ? 'datetime-local' : 'date'"
      :step="datetime ? 1 : undefined"
      :value="drafts[index]"
      :disabled="disabled"
      :readonly="readonly"
      :placeholder="placeholder"
      @input="update(($event.target as HTMLInputElement).value, index)"
      @blur="blur"
    />
    <button
      v-if="clearable && (value !== null || drafts.some(Boolean)) && !disabled && !readonly"
      class="ui-control-action"
      type="button"
      :aria-label="t('ds.clear')"
      @click="clear"
    >
      <X :size="16" />
    </button>
  </div>
</template>
<style scoped>
.date-wrap {
  gap: var(--space-2);
}
.date-wrap .ui-date-input:last-of-type {
  padding-right: var(--space-8);
}
</style>
