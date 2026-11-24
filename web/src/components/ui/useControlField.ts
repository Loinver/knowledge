import { computed, inject } from 'vue'

import { fieldContextKey, formContextKey } from './formTypes'

export function useControlField(props: { disabled?: boolean; readonly?: boolean }) {
  const field = inject(fieldContextKey, undefined)
  const form = inject(formContextKey, undefined)
  const disabled = computed(() =>
    Boolean(props.disabled || field?.disabled.value || form?.disabled.value),
  )
  const readonly = computed(() =>
    Boolean(props.readonly || field?.readonly.value || form?.readonly.value),
  )
  const attributes = computed(() =>
    field
      ? {
          id: field.id,
          'aria-labelledby': field.labelId,
          'aria-describedby': field.descriptionId.value,
          'aria-invalid': field.invalid.value || undefined,
          'aria-required': field.required.value || undefined,
        }
      : {},
  )
  return { field, disabled, readonly, attributes }
}
