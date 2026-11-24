<script setup lang="ts" generic="T extends object">
import { useI18n } from 'vue-i18n'

import type { RowAction } from '@/components/ui/tableTypes'

const props = defineProps<{
  row: T
  actions?: RowAction<T>[]
  disabled?: boolean
  label?: string
}>()
const emit = defineEmits<{ action: [key: string | number, row: T, event: MouseEvent] }>()
const { t } = useI18n()
function isDisabled(action: RowAction<T>) {
  return (
    props.disabled ||
    action.loading ||
    (typeof action.disabled === 'function' ? action.disabled(props.row) : action.disabled)
  )
}
function run(action: RowAction<T>, event: MouseEvent) {
  if (isDisabled(action)) return
  action.onClick?.(props.row, event)
  emit('action', action.key, props.row, event)
}
</script>

<template>
  <div
    class="row-actions flex flex-wrap items-center justify-end gap-1"
    role="group"
    :aria-label="label ?? t('common.actions')"
    @click.stop
  >
    <slot :row="row">
      <button
        v-for="action in actions"
        :key="action.key"
        type="button"
        class="min-h-9 rounded-md px-2 text-sm focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"
        :class="action.destructive ? 'text-destructive' : 'text-primary'"
        :disabled="isDisabled(action)"
        :aria-busy="action.loading"
        @click="run(action, $event)"
      >
        {{ action.label }}
      </button>
    </slot>
  </div>
</template>
