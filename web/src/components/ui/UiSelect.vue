<script setup lang="ts" generic="T extends SelectValue = SelectValue">
import { Check, ChevronDown, X } from '@lucide/vue'
import {
  ComboboxAnchor,
  ComboboxContent,
  ComboboxInput,
  ComboboxItem,
  ComboboxItemIndicator,
  ComboboxPortal,
  ComboboxRoot,
  ComboboxTrigger,
  ComboboxViewport,
} from 'reka-ui'
import type { VNodeChild } from 'vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { InputProps } from './inputTypes'
import type { SelectOption, SelectValue } from './selectionTypes'
import { sameSelection, selectionKey } from './selectionTypes'
import { useControlField } from './useControlField'

defineOptions({ inheritAttrs: false })
const props = defineProps<{
  value?: T
  defaultValue?: T
  options?: SelectOption[]
  multiple?: boolean
  filterable?: boolean
  remote?: boolean
  loading?: boolean
  disabled?: boolean
  readonly?: boolean
  clearable?: boolean
  placeholder?: string
  inputProps?: InputProps
  size?: string
  filter?: (pattern: string, option: SelectOption) => boolean
  renderLabel?: (option: SelectOption, selected: boolean) => VNodeChild
}>()
const emit = defineEmits<{
  'update:value': [value: T, option: SelectOption | SelectOption[] | null]
  change: [value: T, option: SelectOption | SelectOption[] | null]
  search: [value: string]
  clear: []
  blur: [event: FocusEvent]
  focus: [event: FocusEvent]
}>()
const { t } = useI18n()
const { field, disabled, readonly, attributes } = useControlField(props)
const local = ref<SelectValue>(props.defaultValue ?? (props.multiple ? [] : null))
const value = computed(() => (props.value === undefined ? local.value : props.value))
const open = ref(false)
const search = ref('')
const editingSearch = ref(false)
const inputText = ref('')
const wrap = ref<HTMLElement>()
const options = computed(() => props.options ?? [])
const optionLabel = (option?: SelectOption) =>
  typeof option?.label === 'string' ? option.label : option ? String(option.value) : ''
const selectedOptions = computed(() => {
  const keys = Array.isArray(value.value) ? value.value : value.value == null ? [] : [value.value]
  return keys.map(
    (key) =>
      options.value.find((option) => option.value === key) ?? { value: key, label: String(key) },
  )
})
const selectedLabel = computed(() => (props.multiple ? '' : optionLabel(selectedOptions.value[0])))
watch(
  [selectedLabel, open],
  () => {
    if (!open.value || !editingSearch.value) inputText.value = selectedLabel.value
  },
  { immediate: true },
)
watch(value, () => {
  editingSearch.value = false
  search.value = ''
  inputText.value = selectedLabel.value
})
const visibleOptions = computed(() =>
  !props.filterable || props.remote || !search.value
    ? options.value
    : options.value.filter((option) =>
        props.filter
          ? props.filter(search.value, option)
          : optionLabel(option).toLocaleLowerCase().includes(search.value.toLocaleLowerCase()),
      ),
)
const hasValue = computed(() =>
  Array.isArray(value.value) ? value.value.length > 0 : value.value !== null,
)
function update(next: unknown) {
  if (disabled.value || readonly.value) return
  editingSearch.value = false
  search.value = ''
  inputText.value = selectedLabel.value
  const result = next as T
  if (sameSelection(value.value, result)) return
  local.value = result
  const keys = Array.isArray(result) ? result : result == null ? [] : [result]
  const selected = keys
    .map((key) => options.value.find((option) => option.value === key))
    .filter((option): option is SelectOption => Boolean(option))
  const payload = props.multiple ? selected : (selected[0] ?? null)
  emit('update:value', result, payload)
  emit('change', result, payload)
  field?.validate('change')
}
function onSearch(event: Event) {
  if (!props.filterable || disabled.value || readonly.value) return
  editingSearch.value = true
  const next = (event.target as HTMLInputElement).value
  if (search.value === next) return
  search.value = next
  emit('search', next)
  field?.validate('input')
}
function changeOpen(next: boolean) {
  open.value = next && !disabled.value && !readonly.value
  if (!open.value) {
    editingSearch.value = false
    search.value = ''
    inputText.value = selectedLabel.value
  }
}
function clear() {
  if (disabled.value || readonly.value) return
  update(props.multiple ? [] : null)
  search.value = ''
  emit('clear')
  wrap.value?.querySelector('input')?.focus()
}
function blur(event: FocusEvent) {
  field?.validate('blur')
  emit('blur', event)
}
const Label = (labelProps: { option: SelectOption; selected: boolean }): VNodeChild =>
  props.renderLabel?.(labelProps.option, labelProps.selected) ??
  (typeof labelProps.option.label === 'function'
    ? labelProps.option.label()
    : optionLabel(labelProps.option))
defineExpose({
  focus: (options?: FocusOptions) => wrap.value?.querySelector('input')?.focus(options),
  blur: () => wrap.value?.querySelector('input')?.blur(),
})
</script>
<template>
  <div ref="wrap" class="ui-select" :class="$attrs.class" :style="$attrs.style">
    <ComboboxRoot
      :model-value="value"
      :multiple="multiple"
      :disabled="disabled"
      :open="open"
      ignore-filter
      :reset-model-value-on-clear="false"
      :open-on-focus="!readonly"
      @update:model-value="update"
      @update:open="changeOpen"
    >
      <ComboboxAnchor class="ui-input-wrap">
        <ComboboxInput
          v-model="inputText"
          v-bind="{ ...$attrs, ...inputProps, ...attributes }"
          class="ui-combobox-input"
          :disabled="disabled"
          :readonly="readonly || !filterable"
          :placeholder="placeholder ?? t('ds.selectPlaceholder')"
          :aria-busy="loading || undefined"
          :aria-readonly="readonly || undefined"
          :display-value="() => (multiple ? '' : optionLabel(selectedOptions[0]))"
          @input="onSearch"
          @focus="emit('focus', $event)"
          @blur="blur"
        />
        <ComboboxTrigger
          class="ui-control-action"
          :disabled="disabled || readonly"
          :aria-label="placeholder ?? t('ds.selectPlaceholder')"
          ><ChevronDown :size="16"
        /></ComboboxTrigger>
        <button
          v-if="clearable && hasValue && !disabled && !readonly"
          class="ui-control-action select-clear"
          type="button"
          :aria-label="t('ds.clear')"
          @click.stop="clear"
        >
          <X :size="16" />
        </button>
      </ComboboxAnchor>
      <div v-if="multiple && selectedOptions.length" class="select-values">
        <span
          v-for="itemOption in selectedOptions"
          :key="selectionKey(itemOption.value)"
          class="select-value"
          ><Label :option="itemOption" selected /><button
            v-if="!disabled && !readonly"
            type="button"
            :aria-label="t('ds.clear') + ': ' + optionLabel(itemOption)"
            @click="
              update((Array.isArray(value) ? value : []).filter((key) => key !== itemOption.value))
            "
          >
            <X :size="12" /></button
        ></span>
      </div>
      <ComboboxPortal>
        <ComboboxContent class="ui-popup" position="popper" :side-offset="4" :align="'start'">
          <div v-if="loading" class="ui-option" role="status">{{ t('ds.loading') }}</div>
          <ComboboxViewport>
            <ComboboxItem
              v-for="itemOption in visibleOptions"
              :key="selectionKey(itemOption.value)"
              class="ui-option"
              :value="itemOption.value"
              :disabled="itemOption.disabled || readonly"
              :text-value="optionLabel(itemOption)"
            >
              <Label
                :option="itemOption"
                :selected="selectedOptions.some((selected) => selected.value === itemOption.value)"
              /><ComboboxItemIndicator><Check :size="16" /></ComboboxItemIndicator>
            </ComboboxItem>
            <div v-if="!loading && !visibleOptions.length" class="ui-option" role="status">
              {{ t('ds.noOptions') }}
            </div>
          </ComboboxViewport>
        </ComboboxContent>
      </ComboboxPortal>
    </ComboboxRoot>
  </div>
</template>
<style scoped>
.ui-combobox-input {
  padding-right: calc(var(--space-5) * 2);
}
.select-clear {
  right: var(--space-6);
}
.select-values {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin-top: var(--space-1);
}
.select-value {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-small);
  background: var(--surface-muted);
  font-size: var(--font-caption);
}
.select-value button {
  display: flex;
  border: 0;
  background: transparent;
  color: inherit;
}
</style>
