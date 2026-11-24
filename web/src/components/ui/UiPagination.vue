<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { boundedPage, lastPage, positiveInteger } from './tableTypes'

const props = defineProps<{
  page?: number
  pageSize?: number
  total?: number
  itemCount?: number
  pageCount?: number
  disabled?: boolean
  showSizePicker?: boolean
  pageSizes?: number[]
  label?: string
}>()
const emit = defineEmits<{
  'update:page': [page: number]
  'update:pageSize': [pageSize: number]
  change: [page: number]
}>()
const { t, locale } = useI18n()
const numbers = computed(() => new Intl.NumberFormat(locale.value))
const format = (value: number) => numbers.value.format(value)
const count = computed(() => props.total ?? props.itemCount)
const size = computed(() => positiveInteger(props.pageSize, 20))
const pages = computed(() =>
  count.value === undefined
    ? props.pageCount === undefined
      ? undefined
      : positiveInteger(props.pageCount, 1)
    : lastPage(count.value, size.value),
)
const current = computed(() =>
  count.value === undefined
    ? pages.value === undefined
      ? positiveInteger(props.page, 1)
      : Math.min(positiveInteger(props.page, 1), pages.value)
    : boundedPage(props.page, count.value, size.value),
)
const sizes = computed(
  () =>
    props.pageSizes?.filter((value) => Number.isSafeInteger(value) && value > 0) ?? [
      10, 20, 50, 100,
    ],
)
watch(
  () => [current.value, props.page, props.disabled] as const,
  ([page]) => {
    if (!props.disabled && props.page !== undefined && page !== props.page)
      emit('update:page', page)
  },
  { immediate: true },
)
function change(page: number) {
  if (
    props.disabled ||
    page < 1 ||
    (pages.value !== undefined && page > pages.value) ||
    page === current.value
  )
    return
  emit('update:page', page)
  emit('change', page)
}
function changeSize(event: Event) {
  if (props.disabled) return
  const value = Number((event.target as HTMLSelectElement).value)
  if (sizes.value.includes(value)) emit('update:pageSize', value)
}
</script>

<template>
  <nav
    class="ui-pagination flex flex-wrap items-center justify-end gap-2 py-3"
    :aria-label="label ?? t('runs.page', { page: format(current) })"
  >
    <slot name="summary" :total="count" :page="current" :page-size="size">
      <span
        v-if="count !== undefined"
        class="mr-auto text-sm text-muted-foreground"
        data-testid="pagination-total"
        >{{ t('assetLedger.resultCount', { count: format(count) }) }}</span
      >
    </slot>
    <label v-if="showSizePicker" class="flex items-center gap-2 text-sm">
      <span>{{ t('ui.visible') }}</span>
      <select
        class="h-9 rounded-md border border-input bg-background px-2 focus-visible:outline-2 focus-visible:outline-ring"
        :value="size"
        :disabled="disabled"
        @change="changeSize"
      >
        <option v-if="!sizes.includes(size)" :value="size">{{ format(size) }}</option>
        <option v-for="value in sizes" :key="value" :value="value">{{ format(value) }}</option>
      </select>
    </label>
    <button
      type="button"
      class="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"
      :disabled="disabled || current <= 1"
      @click="change(current - 1)"
    >
      {{ t('runs.previous') }}
    </button>
    <span class="min-w-16 text-center text-sm tabular-nums" aria-current="page">{{
      t('runs.page', { page: format(current) })
    }}</span>
    <button
      type="button"
      class="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"
      :disabled="disabled || pages === undefined || current >= pages"
      @click="change(current + 1)"
    >
      {{ t('runs.next') }}
    </button>
    <slot :page="current" :page-count="pages" :change="change" />
  </nav>
</template>
