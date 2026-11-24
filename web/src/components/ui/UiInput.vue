<script setup lang="ts">
import { Eye, EyeOff, X } from '@lucide/vue'
import { computed, nextTick, onMounted, ref, useAttrs, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { AutosizeOptions, InputInst, InputProps, InputValue } from './inputTypes'
import Input from './primitives/input/Input.vue'
import { useControlField } from './useControlField'

defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{
    value?: InputValue
    defaultValue?: InputValue
    type?: string
    disabled?: boolean
    readonly?: boolean
    clearable?: boolean
    placeholder?: string
    inputProps?: InputProps
    autosize?: boolean | AutosizeOptions
    rows?: number
    maxlength?: number | string
    minlength?: number | string
    showPasswordOn?: 'click' | 'mousedown'
    size?: string
  }>(),
  { type: 'text' },
)
const emit = defineEmits<{
  'update:value': [value: string]
  input: [value: string]
  change: [value: string]
  clear: []
  focus: [event: FocusEvent]
  blur: [event: FocusEvent]
}>()
const { t } = useI18n()
const attrs = useAttrs()
const { field, disabled, readonly, attributes } = useControlField(props)
const localValue = ref(props.defaultValue ?? '')
const text = computed(() =>
  String(props.value !== undefined ? (props.value ?? '') : localValue.value),
)
const wrap = ref<HTMLElement>()
const textarea = ref<HTMLTextAreaElement>()
const revealed = ref(false)
const composing = ref(false)
const inputType = computed(() =>
  props.type === 'password' && revealed.value ? 'text' : props.type,
)
const nativeAttrs = computed(() => ({ ...attrs, ...props.inputProps, ...attributes.value }))
function element() {
  return textarea.value ?? wrap.value?.querySelector('input') ?? null
}
function resize() {
  if (!textarea.value || !props.autosize) return
  const options = typeof props.autosize === 'object' ? props.autosize : {}
  const style = getComputedStyle(textarea.value)
  const line = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.5
  const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom)
  textarea.value.style.height = 'auto'
  const minimum = (options.minRows ?? props.rows ?? 3) * line + padding
  const maximum = (options.maxRows ?? Infinity) * line + padding
  textarea.value.style.height = `${Math.min(maximum, Math.max(minimum, textarea.value.scrollHeight))}px`
  textarea.value.style.overflowY = textarea.value.scrollHeight > maximum ? 'auto' : 'hidden'
}
function update(value: string | number) {
  if (disabled.value || readonly.value) return
  const next = String(value)
  if (next === text.value) {
    field?.validate('input')
    return
  }
  localValue.value = next
  emit('update:value', next)
  emit('input', next)
  field?.validate('input')
  void nextTick(resize)
}
function blur(event: FocusEvent) {
  field?.validate('blur')
  emit('blur', event)
}
function clear() {
  if (disabled.value || readonly.value) return
  update('')
  emit('clear')
  element()?.focus()
}
watch(text, () => void nextTick(resize))
onMounted(resize)
defineExpose<InputInst>({
  focus: (options) => element()?.focus(options),
  blur: () => element()?.blur(),
  select: () => element()?.select(),
  clear,
  activate: () => element()?.focus(),
  deactivate: () => element()?.blur(),
  scrollTo: (options) => element()?.scrollTo(options),
  get wrapperElRef() {
    return wrap.value ?? null
  },
  get isCompositing() {
    return composing.value
  },
  get inputElRef() {
    return wrap.value?.querySelector('input') ?? null
  },
  get textareaElRef() {
    return textarea.value ?? null
  },
})
</script>

<template>
  <div
    ref="wrap"
    class="ui-input-wrap"
    :class="attrs.class"
    :style="attrs.style"
    :data-clearable="clearable || type === 'password'"
  >
    <slot name="prefix" />
    <textarea
      v-if="type === 'textarea'"
      ref="textarea"
      v-bind="nativeAttrs"
      class="ui-input"
      :value="text"
      :rows="typeof autosize === 'object' ? (autosize.minRows ?? rows ?? 3) : (rows ?? 3)"
      :disabled="disabled"
      :readonly="readonly"
      :maxlength="maxlength"
      :minlength="minlength"
      :placeholder="placeholder"
      @input="update(($event.target as HTMLTextAreaElement).value)"
      @compositionstart="composing = true"
      @compositionend="composing = false"
      @change="emit('change', text)"
      @blur="blur"
      @focus="emit('focus', $event)"
    />
    <Input
      v-else
      v-bind="nativeAttrs"
      class="ui-input"
      :type="inputType"
      :model-value="text"
      :disabled="disabled"
      :readonly="readonly"
      :maxlength="maxlength"
      :minlength="minlength"
      :placeholder="placeholder"
      @update:model-value="update"
      @compositionstart="composing = true"
      @compositionend="composing = false"
      @change="emit('change', text)"
      @blur="blur"
      @focus="emit('focus', $event)"
    />
    <button
      v-if="type === 'password' && showPasswordOn"
      class="ui-control-action"
      type="button"
      :disabled="disabled"
      :aria-label="t(revealed ? 'ds.hidePassword' : 'ds.showPassword')"
      :aria-pressed="revealed"
      @click="showPasswordOn === 'click' && (revealed = !revealed)"
      @pointerdown="showPasswordOn === 'mousedown' && (revealed = true)"
      @pointerup="showPasswordOn === 'mousedown' && (revealed = false)"
      @pointerleave="showPasswordOn === 'mousedown' && (revealed = false)"
    >
      <EyeOff v-if="revealed" :size="16" /><Eye v-else :size="16" />
    </button>
    <button
      v-else-if="clearable && text && !disabled && !readonly"
      class="ui-control-action"
      type="button"
      :aria-label="t('ds.clear')"
      @click="clear"
    >
      <X :size="16" />
    </button>
    <slot name="suffix" />
  </div>
</template>
