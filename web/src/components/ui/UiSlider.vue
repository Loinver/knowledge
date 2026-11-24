<script setup lang="ts" generic="T extends number | number[] | null = number | number[] | null">
import { SliderRange, SliderRoot, SliderThumb, SliderTrack } from 'reka-ui'
import { computed, ref, useAttrs } from 'vue'

import { sameSelection } from './selectionTypes'
import { useControlField } from './useControlField'

const props = defineProps<{
  value?: T
  defaultValue?: T
  range?: boolean
  min?: number
  max?: number
  step?: number
  disabled?: boolean
  readonly?: boolean
  formatTooltip?: (value: number) => string | number
  vertical?: boolean
}>()
const emit = defineEmits<{
  'update:value': [value: T]
  change: [value: T]
  blur: [event: FocusEvent]
}>()
const { field, disabled, readonly, attributes } = useControlField(props)
const attrs = useAttrs()
const ariaLabel = computed(() => attrs['aria-label'] as string | undefined)
const local = ref<number | number[] | null>(
  props.defaultValue ?? (props.range ? [props.min ?? 0, props.max ?? 100] : (props.min ?? 0)),
)
const value = computed(() => (props.value === undefined ? local.value : props.value))
const values = computed(() => {
  if (Array.isArray(value.value) && value.value.length) return value.value
  return props.range
    ? [props.min ?? 0, props.max ?? 100]
    : [typeof value.value === 'number' ? value.value : (props.min ?? 0)]
})
function update(next: number[] | undefined) {
  if (!next || disabled.value || readonly.value) return
  const result = (props.range || Array.isArray(value.value) ? next : (next[0] ?? null)) as T
  if (sameSelection(value.value, result)) return
  local.value = result
  emit('update:value', result)
  field?.validate('input')
}
function commit(next: number[] | undefined) {
  if (!next || disabled.value || readonly.value) return
  const result = (props.range || Array.isArray(value.value) ? next : (next[0] ?? null)) as T
  emit('change', result)
}
function blur(event: FocusEvent) {
  field?.validate('blur')
  emit('blur', event)
}
</script>
<template>
  <SliderRoot
    v-bind="$attrs"
    class="ui-slider"
    :model-value="values"
    :min="min"
    :max="max"
    :step="step"
    :disabled="disabled || readonly"
    :orientation="vertical ? 'vertical' : 'horizontal'"
    @update:model-value="update"
    @value-commit="commit"
  >
    <SliderTrack class="slider-track"><SliderRange class="slider-range" /></SliderTrack>
    <SliderThumb
      v-for="(item, index) in values"
      :key="index"
      v-bind="{
        ...attributes,
        id: index === 0 ? attributes.id : attributes.id ? `${attributes.id}-${index}` : undefined,
      }"
      class="slider-thumb"
      :aria-label="ariaLabel"
      :aria-readonly="readonly || undefined"
      :aria-valuetext="formatTooltip ? String(formatTooltip(item)) : undefined"
      :title="formatTooltip ? String(formatTooltip(item)) : undefined"
      @blur="blur"
    />
  </SliderRoot>
</template>
<style scoped>
.ui-slider {
  display: flex;
  align-items: center;
  position: relative;
  width: 100%;
  min-height: var(--control-height);
  touch-action: none;
  user-select: none;
}
.slider-track {
  position: relative;
  flex: 1;
  height: var(--space-1);
  border-radius: var(--radius-control);
  background: var(--border-default);
}
.slider-range {
  position: absolute;
  height: 100%;
  background: var(--action-primary);
  border-radius: inherit;
}
.slider-thumb {
  display: block;
  width: var(--space-4);
  height: var(--space-4);
  border: 1px solid var(--action-primary);
  border-radius: 50%;
  background: var(--surface-input);
}
.slider-thumb:focus-visible {
  box-shadow: var(--glow);
  outline: none;
}
.ui-slider[data-orientation='vertical'] {
  flex-direction: column;
  min-height: var(--control-height-large);
  width: var(--control-height);
}
.ui-slider[data-orientation='vertical'] .slider-track {
  width: var(--space-1);
  height: auto;
}
.ui-slider[data-orientation='vertical'] .slider-range {
  width: 100%;
  height: auto;
}
.ui-slider[data-disabled] .slider-thumb {
  background: var(--surface-muted);
  border-color: var(--foreground-disabled);
}
</style>
