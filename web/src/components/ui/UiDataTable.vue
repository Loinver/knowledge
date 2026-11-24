<script setup lang="ts" generic="T extends object">
import { type ColumnDef, FlexRender, tableFeatures, useTable } from '@tanstack/vue-table'
import { computed, type CSSProperties, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './primitives/table'
import type {
  DataTableColumn,
  DataTableProps,
  DataTableSlots,
  RowKey,
  SelectionMeta,
  TableFilters,
  TableSort,
} from './tableTypes'
import { boundedPage, columnId, fieldValue, localRows, positiveInteger } from './tableTypes'
import UiPagination from './UiPagination.vue'

const props = withDefaults(defineProps<DataTableProps<T>>(), {
  pagination: undefined,
  initialized: true,
})
defineSlots<DataTableSlots<T>>()
const emit = defineEmits<{
  'update:page': [page: number]
  'update:pageSize': [pageSize: number]
  'update:sort': [sort: TableSort]
  'update:filters': [filters: TableFilters]
  'update:selection': [keys: RowKey[], rows: T[], meta: SelectionMeta<T>]
  retry: []
  rowClick: [row: T, index: number, event: MouseEvent | KeyboardEvent]
}>()
const { t, locale } = useI18n()
const numbers = computed(() => new Intl.NumberFormat(locale.value))
const source = computed(() => props.rows ?? [])
const mode = computed(() => props.mode ?? 'none')
const config = computed(() => (typeof props.pagination === 'object' ? props.pagination : {}))
const effectivePageSize = computed(() =>
  positiveInteger(props.pageSize ?? config.value.pageSize, 20),
)
const requestedPage = computed(() => positiveInteger(props.page ?? config.value.page, 1))
const collection = computed(() =>
  mode.value === 'local'
    ? localRows(source.value, props.columns, props.sort ?? null, props.filters ?? {})
    : source.value,
)
const count = computed(() =>
  mode.value === 'local' ? collection.value.length : (props.total ?? config.value.itemCount),
)
const resultUnavailable = computed(
  () => !!props.loading || !!props.error || props.initialized === false,
)
const displayedCount = computed(() => (resultUnavailable.value ? undefined : count.value))
const page = computed(() =>
  mode.value === 'local'
    ? boundedPage(requestedPage.value, collection.value.length, effectivePageSize.value)
    : requestedPage.value,
)
const displayed = computed(() =>
  mode.value === 'local'
    ? collection.value.slice(
        (page.value - 1) * effectivePageSize.value,
        page.value * effectivePageSize.value,
      )
    : collection.value,
)
const selected = computed(() => props.selection ?? [])
const selectableColumn = computed(() => props.columns.find((column) => column.type === 'selection'))
const hasPagination = computed(() => mode.value !== 'none' && props.pagination !== false)
const locked = computed(() => !!props.disabled || !!props.loading)
const tableMinimum = computed(
  () =>
    props.scrollX ??
    (props.columns.length
      ? `max(100%, calc(${props.columns.map((item) => cssLength(item.width ?? item.minWidth ?? 160)).join(' + ')}))`
      : '100%'),
)
function keyOf(row: T): RowKey {
  const key =
    typeof props.rowKey === 'function' ? props.rowKey(row) : fieldValue(row, props.rowKey ?? 'id')
  if (typeof key === 'string' || typeof key === 'number') return key
  if (selectableColumn.value)
    throw new Error('UiDataTable selection requires a stable string or number rowKey')
  return source.value.indexOf(row)
}
const features = tableFeatures({})
const definitions = computed<ColumnDef<typeof features, T>[]>(() =>
  props.columns.map((column, index) => ({
    id: columnId(column, index),
    accessorFn: (row: T) => fieldValue(row, column.key),
    header: () => (typeof column.title === 'function' ? column.title() : column.title),
    cell: ({ row }) =>
      column.render
        ? column.render(row.original, row.index)
        : displayValue(fieldValue(row.original, column.key), column),
  })),
)
const table = useTable<typeof features, T>({
  features,
  data: displayed,
  columns: definitions,
  getRowId: (row) => `${typeof keyOf(row)}:${keyOf(row)}`,
})
const model = computed(() => table.getRowModel().rows)
function text(value: unknown): string {
  return value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)
}
function displayValue(value: unknown, column: DataTableColumn<T>): string {
  return typeof value === 'number' && column.format !== 'raw'
    ? numbers.value.format(value)
    : text(value)
}
function column(id: string): DataTableColumn<T> {
  return props.columns.find(
    (candidate, index) => columnId(candidate, index) === id,
  ) as DataTableColumn<T>
}
function eligible(row: T): boolean {
  const disabled = selectableColumn.value?.disabled
  return !(typeof disabled === 'function' ? disabled(row) : disabled)
}
function isSelectable(row: T): boolean {
  return !locked.value && eligible(row)
}
const selectableRows = computed(() => displayed.value.filter(eligible))
const allChecked = computed(
  () =>
    selectableRows.value.length > 0 &&
    selectableRows.value.every((row) => selected.value.includes(keyOf(row))),
)
const someChecked = computed(
  () =>
    selectableRows.value.some((row) => selected.value.includes(keyOf(row))) && !allChecked.value,
)
function updateSelection(keys: RowKey[], meta: SelectionMeta<T>) {
  emit(
    'update:selection',
    keys,
    source.value.filter((row) => keys.includes(keyOf(row))),
    meta,
  )
}
function check(row: T, event: Event) {
  if (!isSelectable(row)) return
  const key = keyOf(row)
  const checked = (event.target as HTMLInputElement).checked
  updateSelection(
    checked
      ? [...new Set([...selected.value, key])]
      : selected.value.filter((item) => item !== key),
    { action: checked ? 'check' : 'uncheck', row },
  )
}
function checkAll(event: Event) {
  if (locked.value) return
  const checked = (event.target as HTMLInputElement).checked
  const keys = selectableRows.value.map(keyOf)
  updateSelection(
    checked
      ? [...new Set([...selected.value, ...keys])]
      : selected.value.filter((key) => !keys.includes(key)),
    { action: checked ? 'checkAll' : 'uncheckAll' },
  )
}
function order(key: DataTableColumn<T>['key']) {
  return (Array.isArray(props.sort) ? props.sort : props.sort ? [props.sort] : []).find(
    (state) => state.columnKey === key,
  )?.order
}
function sortBy(current: DataTableColumn<T>) {
  if (!current.sorter || current.key === undefined || locked.value) return
  const previous = order(current.key)
  const next: TableSort =
    previous === 'descend'
      ? null
      : {
          columnKey: current.key as string | number,
          order: previous === 'ascend' ? 'descend' : 'ascend',
        }
  const multiple = typeof current.sorter === 'object' && current.sorter.multiple !== undefined
  const previousStates = Array.isArray(props.sort) ? props.sort : props.sort ? [props.sort] : []
  const state = multiple
    ? [...previousStates.filter((item) => item.columnKey !== current.key), ...(next ? [next] : [])]
    : next
  emit('update:sort', state)
}
function ariaSort(current: DataTableColumn<T>): 'ascending' | 'descending' | 'none' | undefined {
  if (!current.sorter) return undefined
  return order(current.key) === 'ascend'
    ? 'ascending'
    : order(current.key) === 'descend'
      ? 'descending'
      : 'none'
}
function filterSelected(current: DataTableColumn<T>, value: string) {
  const selected = props.filters?.[String(current.key)]
  if (value === '') return selected === undefined || (Array.isArray(selected) && !selected.length)
  const option = current.filterOptions?.[Number(value)]
  return (Array.isArray(selected) ? selected : [selected]).some((item) =>
    Object.is(item, option?.value),
  )
}
function filterBy(current: DataTableColumn<T>, event: Event) {
  if (locked.value) return
  const input = event.target as HTMLSelectElement
  const values = current.filterMultiple
    ? Array.from(input.selectedOptions).map((option) => option.value)
    : [input.value]
  const selected = values
    .filter((value) => value !== '')
    .map((value) => current.filterOptions?.[Number(value)]?.value)
    .filter((value) => value !== undefined)
  emit('update:filters', {
    ...props.filters,
    [String(current.key)]: current.filterMultiple ? selected : selected[0],
  })
}
function cssLength(value: number | string | undefined): string | undefined {
  return typeof value === 'number' ? `${value}px` : value
}
function cellStyle(current: DataTableColumn<T>): CSSProperties {
  const style: CSSProperties = {
    width: cssLength(current.width ?? (current.fixed ? (current.minWidth ?? 160) : undefined)),
    minWidth: cssLength(current.minWidth),
    maxWidth: cssLength(current.maxWidth),
    textAlign: current.align,
  }
  if (current.fixed) {
    const index = props.columns.indexOf(current)
    const adjacent =
      current.fixed === 'right' ? props.columns.slice(index + 1) : props.columns.slice(0, index)
    const widths = adjacent
      .filter((item) => item.fixed === current.fixed)
      .map((item) => cssLength(item.width ?? item.minWidth ?? 160))
    Object.assign(style, {
      position: 'sticky',
      [current.fixed]: widths.length ? `calc(${widths.join(' + ')})` : '0px',
      zIndex: 1,
      boxShadow: `${current.fixed === 'right' ? 'calc(-1 * var(--border-width))' : 'var(--border-width)'} 0 0 var(--border-default)`,
    })
  }
  return style
}
function changePage(value: number) {
  if (locked.value) return
  emit('update:page', value)
  config.value.onChange?.(value)
  config.value.onUpdatePage?.(value)
}
function changeSize(value: number) {
  if (locked.value) return
  emit('update:pageSize', value)
  config.value.onUpdatePageSize?.(value)
}
watch(
  () => [page.value, requestedPage.value, locked.value] as const,
  ([value]) => {
    if (mode.value === 'local' && value !== requestedPage.value) changePage(value)
  },
  { immediate: true },
)
function interactive(event: MouseEvent | KeyboardEvent) {
  return (event.target as HTMLElement | null)?.closest?.(
    'button,a,input,select,textarea,[role="button"],[role="checkbox"]',
  )
}
function activate(row: T, index: number, event: MouseEvent | KeyboardEvent) {
  if (props.disabled || interactive(event)) return
  emit('rowClick', row, index, event)
}
function keyboard(row: T, index: number, event: KeyboardEvent) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  if (interactive(event) || props.disabled) return
  event.preventDefault()
  activate(row, index, event)
}
</script>

<template>
  <section
    class="ui-data-table min-w-0 [&_[data-slot=table-container]:focus-visible]:outline-2 [&_[data-slot=table-container]:focus-visible]:outline-ring"
    :aria-busy="loading"
  >
    <slot name="toolbar" :rows="displayed" :total="displayedCount" :selection="selected" />
    <div
      v-if="error"
      role="alert"
      class="mb-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
    >
      <slot name="error" :error="error" :retry="() => emit('retry')"
        >{{ error }}
        <button
          type="button"
          class="ml-2 rounded px-2 py-1 focus-visible:outline-2 focus-visible:outline-ring"
          :disabled="loading || disabled"
          @click="emit('retry')"
        >
          {{ t('ui.retry') }}
        </button></slot
      >
    </div>
    <div v-if="loading" role="status" class="py-2 text-sm text-muted-foreground">
      <slot v-if="source.length" name="refreshing">{{ t('ui.loading') }}</slot>
      <slot v-else name="loading">{{ t('common.loading') }}</slot>
    </div>
    <Table
      class="table-fixed min-w-[var(--ui-table-min-width)]"
      :style="{
        '--ui-table-min-width': cssLength(tableMinimum),
        maxHeight: cssLength(maxHeight ?? 600),
        overflow: 'auto',
      }"
      role="region"
      :aria-label="label ?? t('common.viewTable')"
      tabindex="0"
    >
      <colgroup>
        <col
          v-for="(item, index) in columns"
          :key="columnId(item, index)"
          :style="{ width: cssLength(item.width ?? item.minWidth ?? 160) }"
        />
      </colgroup>
      <TableHeader>
        <TableRow v-for="group in table.getHeaderGroups()" :key="group.id">
          <TableHead
            v-for="header in group.headers"
            :key="header.id"
            class="ui-data-table-th bg-muted"
            :class="column(header.column.id).titleClassName"
            :style="cellStyle(column(header.column.id))"
            :aria-sort="ariaSort(column(header.column.id))"
          >
            <input
              v-if="column(header.column.id).type === 'selection'"
              type="checkbox"
              :checked="allChecked"
              :indeterminate="someChecked"
              :aria-checked="someChecked ? 'mixed' : allChecked"
              :aria-label="t('ui.selected')"
              :disabled="locked || !selectableRows.length"
              class="size-4 accent-primary focus-visible:outline-2 focus-visible:outline-ring"
              @change="checkAll"
              @click.stop
            />
            <template v-else>
              <button
                v-if="column(header.column.id).sorter"
                type="button"
                class="flex min-h-9 w-full items-center gap-2 rounded text-left focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
                :disabled="locked"
                @click="sortBy(column(header.column.id))"
              >
                <FlexRender :header="header" /><svg
                  v-if="order(column(header.column.id).key)"
                  aria-hidden="true"
                  viewBox="0 0 16 16"
                  class="size-4 shrink-0"
                  :class="
                    order(column(header.column.id).key) === 'descend' ? 'rotate-180' : undefined
                  "
                >
                  <path
                    d="M8 13V3M3 8l5-5 5 5"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.5"
                  />
                </svg>
              </button>
              <FlexRender v-else :header="header" />
              <select
                v-if="column(header.column.id).filterOptions"
                class="mt-1 block max-w-full rounded border border-input bg-background text-sm"
                :disabled="locked"
                :aria-label="
                  text(
                    typeof column(header.column.id).title === 'function'
                      ? undefined
                      : column(header.column.id).title,
                  )
                "
                :multiple="column(header.column.id).filterMultiple"
                @change="filterBy(column(header.column.id), $event)"
              >
                <option value="" :selected="filterSelected(column(header.column.id), '')">
                  {{ t('ui.all') }}
                </option>
                <option
                  v-for="(option, index) in column(header.column.id).filterOptions"
                  :key="index"
                  :value="index"
                  :selected="filterSelected(column(header.column.id), String(index))"
                >
                  {{ option.label }}
                </option>
              </select>
            </template>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow
          v-for="(row, index) in model"
          :key="row.id"
          v-bind="rowProps?.(row.original, index)"
          :data-row-key="String(keyOf(row.original))"
          :data-state="selected.includes(keyOf(row.original)) ? 'selected' : undefined"
          :tabindex="disabled ? undefined : 0"
          class="focus-visible:outline-2 focus-visible:outline-ring"
          @click="activate(row.original, index, $event)"
          @keydown="keyboard(row.original, index, $event)"
        >
          <TableCell
            v-for="cell in row.getAllCells()"
            :key="cell.id"
            class="ui-data-table-td"
            :class="[
              column(cell.column.id).className,
              column(cell.column.id).fixed ? 'bg-background' : undefined,
              size === 'small' ? 'py-2' : size === 'large' ? 'py-4' : 'py-3',
            ]"
            :style="cellStyle(column(cell.column.id))"
          >
            <input
              v-if="column(cell.column.id).type === 'selection'"
              type="checkbox"
              :checked="selected.includes(keyOf(row.original))"
              :aria-label="`${t('ui.selected')} ${keyOf(row.original)}`"
              :disabled="!isSelectable(row.original)"
              class="size-4 accent-primary focus-visible:outline-2 focus-visible:outline-ring"
              @change="check(row.original, $event)"
              @click.stop
            />
            <div
              v-else
              class="min-w-0"
              :class="
                column(cell.column.id).ellipsis
                  ? 'overflow-hidden text-ellipsis whitespace-nowrap'
                  : 'whitespace-normal [overflow-wrap:anywhere]'
              "
              :title="
                column(cell.column.id).ellipsis
                  ? text(fieldValue(row.original, column(cell.column.id).key))
                  : undefined
              "
            >
              <slot
                :name="`cell-${cell.column.id}`"
                :row="row.original"
                :index="index"
                :value="cell.getValue()"
                :column="column(cell.column.id)"
              >
                <slot
                  v-if="cell.column.id === 'actions' && $slots.actions"
                  name="actions"
                  :row="row.original"
                  :index="index"
                />
                <slot
                  v-else
                  name="cell"
                  :row="row.original"
                  :index="index"
                  :value="cell.getValue()"
                  :column="column(cell.column.id)"
                  ><FlexRender :cell="cell"
                /></slot>
              </slot>
            </div>
          </TableCell>
        </TableRow>
        <TableRow v-if="!model.length && !loading && !error">
          <TableCell
            class="ui-data-table-td text-center text-muted-foreground"
            :class="$slots.empty ? 'p-0' : 'py-6'"
            :colspan="Math.max(columns.length, 1)"
          >
            <slot v-if="initialized === false" name="initial">{{ t('common.search') }}</slot>
            <slot v-else name="empty">{{
              emptyText ??
              t(
                Object.values(filters ?? {}).some((value) => value !== undefined)
                  ? 'ui.emptyFiltered'
                  : 'common.empty',
              )
            }}</slot>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>
    <UiPagination
      v-if="hasPagination"
      :page="page"
      :page-size="effectivePageSize"
      :total="displayedCount"
      :page-count="resultUnavailable ? undefined : config.pageCount"
      :disabled="locked || resultUnavailable || config.disabled"
      :show-size-picker="config.showSizePicker"
      :page-sizes="config.pageSizes"
      @update:page="changePage"
      @update:page-size="changeSize"
    />
    <slot name="footer" :rows="displayed" :total="displayedCount" :page="page" />
  </section>
</template>
