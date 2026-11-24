<script setup lang="ts">
import { computed, inject, onBeforeUnmount, provide, ref, useId, useSlots, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { fieldContextKey, formContextKey } from '@/components/ui/formTypes'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/primitives/field'

const props = withDefaults(
  defineProps<{
    path?: string
    name?: string
    label?: string
    help?: string
    error?: string
    required?: boolean
    disabled?: boolean
    readonly?: boolean
    showFeedback?: boolean
    labelFor?: string
    labelProps?: Record<string, unknown>
    validationStatus?: string
    feedback?: string
  }>(),
  { showFeedback: true },
)
const { t } = useI18n()
const slots = useSlots()
const form = inject(formContextKey, undefined)
const root = ref<HTMLElement | null>(null)
const unique = useId()
const path = computed(() => props.path || props.name || '')
const id = computed(
  () => props.labelFor || String(props.labelProps?.for || '') || `field-${unique}`,
)
const error = computed(
  () =>
    props.error ||
    (props.validationStatus === 'error' ? props.feedback : '') ||
    form?.errors.value[path.value] ||
    '',
)
const required = computed(() => Boolean(props.required || form?.required(path.value)))
const labelId = `label-${unique}`
const helpId = `help-${unique}`
const errorId = `error-${unique}`
const descriptionId = computed(() =>
  error.value
    ? errorId
    : props.showFeedback && (props.help || props.feedback || slots.feedback || slots.help)
      ? helpId
      : undefined,
)
let unregister: (() => void) | undefined
watch(
  path,
  (value) => {
    unregister?.()
    if (value) unregister = form?.register(value, () => root.value)
  },
  { immediate: true },
)
onBeforeUnmount(() => unregister?.())
provide(fieldContextKey, {
  get id() {
    return id.value
  },
  get labelId() {
    return props.label || slots.label ? labelId : undefined
  },
  descriptionId,
  invalid: computed(() => Boolean(error.value)),
  required,
  disabled: computed(() => Boolean(props.disabled || form?.disabled.value)),
  readonly: computed(() => Boolean(props.readonly || form?.readonly.value)),
  validate: (trigger) => {
    if (path.value) void form?.validateField(path.value, trigger)
  },
})
</script>

<template>
  <div ref="root" class="ui-field">
    <Field :data-invalid="error ? true : undefined">
      <FieldLabel
        v-if="label || $slots.label"
        v-bind="labelProps"
        :id="labelId"
        :for="id"
        class="ui-field-label"
      >
        <slot name="label">{{ label }}</slot>
        <svg
          v-if="required"
          class="ui-required"
          aria-hidden="true"
          width="8"
          height="8"
          viewBox="0 0 12 12"
        >
          <path d="M6 1v10M1.7 3.5l8.6 5M1.7 8.5l8.6-5" stroke="currentColor" stroke-width="1.25" />
        </svg>
        <span v-if="required" class="sr-only">{{ t('common.required') }}</span>
      </FieldLabel>
      <div class="ui-field-control">
        <slot
          :id="id"
          :aria-labelledby="labelId"
          :aria-describedby="descriptionId"
          :aria-invalid="!!error"
          :disabled="disabled || form?.disabled.value"
        />
      </div>
      <div v-if="error" :id="errorId" class="ui-field-error" role="alert">{{ error }}</div>
      <FieldDescription
        v-else-if="showFeedback && (help || feedback || $slots.feedback || $slots.help)"
        :id="helpId"
        class="ui-field-help"
      >
        <slot name="help"
          ><slot name="feedback">{{ help || feedback }}</slot></slot
        >
      </FieldDescription>
    </Field>
  </div>
</template>
