<script setup lang="ts" generic="T extends object">
import { computed, useSlots } from 'vue'

import UiDataTable from '@/components/ui/UiDataTable.vue'

import type {
  DataTableProps,
  RowKey,
  SearchTableSlots,
  SelectionMeta,
  TableFilters,
  TableSort,
} from '../ui/tableTypes'
import SearchPanel from './SearchPanel.vue'
import TableToolbar from './TableToolbar.vue'

const props = withDefaults(
  defineProps<
    DataTableProps<T> & {
      query?: string
      expanded?: boolean
      searchable?: boolean
      searchLabel?: string
      searchPlaceholder?: string
    }
  >(),
  { pagination: undefined, initialized: true, searchable: true },
)
const emit = defineEmits<{
  'update:query': [value: string]
  'update:expanded': [value: boolean]
  'update:page': [value: number]
  'update:pageSize': [value: number]
  'update:sort': [value: TableSort]
  'update:filters': [value: TableFilters]
  'update:selection': [keys: RowKey[], rows: T[], meta: SelectionMeta<T>]
  submit: [query: string, filters: TableFilters]
  reset: []
  clear: []
  retry: []
  rowClick: [row: T, index: number, event: MouseEvent | KeyboardEvent]
}>()
const slots = useSlots()
defineSlots<SearchTableSlots<T>>()
const forwarded = computed(
  () => Object.keys(slots).filter((name) => name.startsWith('cell-')) as `cell-${string}`[],
)
const tableProps = computed(() => ({
  rows: props.rows,
  columns: props.columns,
  rowKey: props.rowKey,
  rowProps: props.rowProps,
  mode: props.mode,
  total: props.total,
  page: props.page,
  pageSize: props.pageSize,
  pagination: props.pagination,
  sort: props.sort,
  filters: props.filters,
  selection: props.selection,
  loading: props.loading,
  error: props.error,
  initialized: props.initialized,
  disabled: props.disabled,
  scrollX: props.scrollX,
  maxHeight: props.maxHeight,
  size: props.size,
  bordered: props.bordered,
  emptyText: props.emptyText,
  label: props.label,
}))
function submitted(query: string, filters: TableFilters) {
  emit('submit', query, filters)
}
function checked(keys: RowKey[], rows: T[], meta: SelectionMeta<T>) {
  emit('update:selection', keys, rows, meta)
}
function clicked(row: T, index: number, event: MouseEvent | KeyboardEvent) {
  emit('rowClick', row, index, event)
}
</script>

<template>
  <section class="search-table min-w-0">
    <slot
      name="search"
      :query="query ?? ''"
      :filters="filters ?? {}"
      :submit="submitted"
      :update="(value: string) => emit('update:query', value)"
    >
      <SearchPanel
        v-if="searchable !== false"
        :query="query"
        :filters="filters"
        :expanded="expanded"
        :loading="loading"
        :disabled="disabled"
        :label="searchLabel"
        :placeholder="searchPlaceholder"
        @update:query="emit('update:query', $event)"
        @update:expanded="emit('update:expanded', $event)"
        @update:filters="emit('update:filters', $event)"
        @submit="submitted"
        @reset="emit('reset')"
        @clear="emit('clear')"
      >
        <template v-if="$slots.filter" #filter="context"
          ><slot name="filter" v-bind="context"
        /></template>
        <template v-if="$slots.advanced" #advanced="context"
          ><slot name="advanced" v-bind="context"
        /></template>
        <template v-if="$slots['search-actions']" #actions="context"
          ><slot name="search-actions" v-bind="context"
        /></template>
      </SearchPanel>
    </slot>
    <UiDataTable
      v-bind="tableProps"
      @update:page="emit('update:page', $event)"
      @update:page-size="emit('update:pageSize', $event)"
      @update:sort="emit('update:sort', $event)"
      @update:filters="emit('update:filters', $event)"
      @update:selection="checked"
      @retry="emit('retry')"
      @row-click="clicked"
    >
      <template #toolbar="context">
        <slot v-if="$slots.toolbar" name="toolbar" v-bind="context" />
        <TableToolbar
          v-else
          :total="context.total"
          :selection="context.selection"
          :loading="loading"
          :label="label"
        >
          <template #actions><slot name="toolbar-actions" /></template>
          <template #filters><slot name="toolbar-filters" /></template>
        </TableToolbar>
      </template>
      <template v-if="$slots.cell" #cell="context"><slot name="cell" v-bind="context" /></template>
      <template v-if="$slots.actions" #actions="context"
        ><slot name="actions" v-bind="context"
      /></template>
      <template v-if="$slots.error" #error="context"
        ><slot name="error" v-bind="context"
      /></template>
      <template v-if="$slots.empty" #empty><slot name="empty" /></template>
      <template v-if="$slots.initial" #initial><slot name="initial" /></template>
      <template v-if="$slots.loading" #loading><slot name="loading" /></template>
      <template v-if="$slots.refreshing" #refreshing><slot name="refreshing" /></template>
      <template v-if="$slots.footer" #footer="context"
        ><slot name="footer" v-bind="context"
      /></template>
      <template v-for="name in forwarded" #[name]="context"
        ><slot :name="name" v-bind="context ?? {}"
      /></template>
    </UiDataTable>
  </section>
</template>

<style scoped>
.search-table {
  min-width: 0;
  background: var(--surface-panel);
}
.search-table :deep(.table-toolbar) {
  padding-top: 10px;
  padding-bottom: 10px;
  border-top: 1px solid var(--border-muted);
}
.search-table :deep([data-slot='table-container']) {
  border: 1px solid var(--border-muted);
  border-radius: var(--radius-control);
}
.search-table :deep([data-slot='table-head']) {
  height: 38px;
  color: var(--foreground-muted);
  background: var(--surface-muted);
  font-size: 12px;
  font-weight: 500;
}
.search-table :deep([data-slot='table-cell']) {
  font-size: var(--font-small);
}
</style>
