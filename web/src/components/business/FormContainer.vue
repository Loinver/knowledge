<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, provide, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { FormInst, FormRules } from '@/components/ui/formTypes'
import { formContextKey } from '@/components/ui/formTypes'

import { fieldRules, readField, validateFieldValue } from './formValidation'

const props = withDefaults(
  defineProps<{
    model?: object
    rules?: FormRules
    disabled?: boolean
    readonly?: boolean
    submitting?: boolean
    labelPlacement?: string
    showSummary?: boolean
  }>(),
  { rules: () => ({}), showSummary: true },
)
const emit = defineEmits<{
  submit: [event: SubmitEvent]
  invalid: [errors: Record<string, string>]
}>()
const { t } = useI18n()
const root = ref<HTMLFormElement | null>(null)
const errors = ref<Record<string, string>>({})
const summary = ref<HTMLElement | null>(null)
const registered = new Map<string, () => HTMLElement | null>()
const fieldGenerations = new Map<string, number>()
let generation = 0
let disposed = false
let validation: Promise<void> | undefined
const validatingSubmit = ref(false)
const blocked = computed(() => props.disabled || props.readonly || props.submitting)
function restoreValidation() {
  generation++
  fieldGenerations.clear()
  errors.value = {}
  validation = undefined
}
watch(() => props.model, restoreValidation)
watch(
  () => props.model,
  () => {
    generation++
  },
  { deep: true, flush: 'sync' },
)
watch(
  () => props.rules,
  () => {
    generation++
    for (const path of Object.keys(errors.value)) void validateField(path)
  },
  { deep: true },
)
onBeforeUnmount(() => {
  disposed = true
  restoreValidation()
})
async function validateField(path: string, trigger?: string) {
  const rules = fieldRules(props.rules, path)
  if (trigger && !rules.some((rule) => !rule.trigger || [rule.trigger].flat().includes(trigger)))
    return
  const fieldGeneration = (fieldGenerations.get(path) ?? 0) + 1
  fieldGenerations.set(path, fieldGeneration)
  const current = generation
  const error = await validateFieldValue(readField(props.model, path), rules, t('common.required'))
  if (disposed || current !== generation || fieldGenerations.get(path) !== fieldGeneration) return
  errors.value = { ...errors.value }
  if (error) errors.value[path] = error
  else delete errors.value[path]
}
async function validate(callback?: Parameters<FormInst['validate']>[0], paths?: string[]) {
  if (validation && !paths) return validation
  const current = generation
  const selected = paths ?? Object.keys(props.rules)
  const task = (async () => {
    const result: Record<string, string> = {}
    await Promise.all(
      selected.map(async (path) => {
        const error = await validateFieldValue(
          readField(props.model, path),
          fieldRules(props.rules, path),
          t('common.required'),
        )
        if (error) result[path] = error
      }),
    )
    if (disposed || generation !== current) throw new Error('FORM_CONTEXT_CHANGED')
    errors.value = paths ? { ...errors.value } : {}
    for (const path of selected) {
      if (result[path]) errors.value[path] = result[path]
      else delete errors.value[path]
    }
    if (Object.keys(result).length) {
      callback?.(result)
      emit('invalid', result)
      await nextTick()
      const first = registered.get(Object.keys(result)[0])?.()
      first?.querySelector<HTMLElement>('input,textarea,select,button,[tabindex]')?.focus()
      throw new Error('FORM_INVALID')
    }
    callback?.(undefined)
  })()
  if (!paths) validation = task
  try {
    await task
  } finally {
    if (validation === task) validation = undefined
  }
}
async function submit(event: SubmitEvent) {
  if (blocked.value || validatingSubmit.value) return
  validatingSubmit.value = true
  try {
    await validate()
    if (!blocked.value) emit('submit', event)
  } catch {
    /* Inline errors retain the draft and receive focus. */
  } finally {
    validatingSubmit.value = false
  }
}
provide(formContextKey, {
  disabled: computed(() => Boolean(props.disabled || props.submitting)),
  readonly: computed(() => Boolean(props.readonly)),
  errors,
  required: (path) => fieldRules(props.rules, path).some((rule) => rule.required),
  register: (path, element) => {
    registered.set(path, element)
    return () => registered.delete(path)
  },
  validateField,
})
defineExpose<FormInst>({ validate, restoreValidation })
</script>

<template>
  <form
    ref="root"
    novalidate
    class="ui-form"
    :aria-busy="submitting || validatingSubmit || undefined"
    @submit.prevent="submit"
  >
    <div
      v-if="showSummary && Object.keys(errors).length > 1"
      ref="summary"
      role="alert"
      class="ui-field-error"
      tabindex="-1"
    >
      {{ t('ds.form.invalidSummary', { count: Object.keys(errors).length }) }}
    </div>
    <slot :errors="errors" :disabled="blocked" />
  </form>
</template>
