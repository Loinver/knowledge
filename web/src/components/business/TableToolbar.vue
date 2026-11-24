<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { RowKey } from '@/components/ui/tableTypes'

defineProps<{ total?: number; selection?: RowKey[]; loading?: boolean; label?: string }>()
const { t, locale } = useI18n()
const numbers = computed(() => new Intl.NumberFormat(locale.value))
const format = (value: number) => numbers.value.format(value)
</script>

<template>
  <div
    class="table-toolbar flex flex-wrap items-center justify-between gap-3 py-3"
    :aria-busy="loading"
  >
    <div class="flex flex-wrap items-center gap-3 text-sm">
      <slot name="summary" :total="total">
        <span v-if="label" class="font-medium">{{ label }}</span>
        <span v-if="total !== undefined" class="text-muted-foreground">{{
          t('assetLedger.resultCount', { count: format(total) })
        }}</span>
      </slot>
      <slot name="selection" :keys="selection ?? []">
        <span v-if="selection?.length"
          >{{ t('ui.selected')
          }}{{ t('assetLedger.resultCount', { count: format(selection.length) }) }}</span
        >
      </slot>
      <slot name="filters" />
    </div>
    <div class="flex flex-wrap items-center gap-2"><slot name="actions" /><slot /></div>
  </div>
</template>
