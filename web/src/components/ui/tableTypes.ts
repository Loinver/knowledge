import type { HTMLAttributes, VNodeChild } from 'vue'

export type RowKey = string | number
export type ColumnKey = string | number
export type PaginationMode = 'remote' | 'local' | 'none'
export type SortOrder = 'ascend' | 'descend'
export interface DataTableSortState {
  columnKey: ColumnKey
  order: SortOrder | false
}
export type TableSort = DataTableSortState | DataTableSortState[] | null
export type FilterValue = string | number | boolean | null
export type TableFilters = Record<string, FilterValue | FilterValue[] | undefined>
export type RowKeyGetter<T> = (row: T) => RowKey
export type CellRenderer<T> = (row: T, index: number) => VNodeChild
export type RowProps<T> = (
  row: T,
  index: number,
) => HTMLAttributes & {
  [attribute: `data-${string}`]: unknown
}

/** Project-owned column contract. Business DTOs remain in api/<domain>. */
export interface DataTableColumn<T extends object> {
  key?: keyof T | ColumnKey
  title?: VNodeChild | (() => VNodeChild)
  type?: 'selection'
  render?: CellRenderer<T>
  /** Default numbers follow locale; use raw for numeric identifiers/codes. */
  format?: 'number' | 'raw'
  width?: number | string
  minWidth?: number | string
  maxWidth?: number | string
  fixed?: 'left' | 'right'
  align?: 'left' | 'center' | 'right'
  ellipsis?: boolean | { tooltip?: boolean }
  className?: string
  titleClassName?: string
  sorter?:
    | boolean
    | 'default'
    | ((a: T, b: T) => number)
    | {
        compare: (a: T, b: T) => number
        multiple?: number
      }
  filter?: boolean | 'default' | ((value: FilterValue, row: T) => boolean)
  filterOptions?: { label: string; value: FilterValue }[]
  filterMultiple?: boolean
  disabled?: boolean | ((row: T) => boolean)
}
export type DataTableColumns<T extends object> = DataTableColumn<T>[]

export interface TableCellSlot<T extends object> {
  row: T
  index: number
  value: unknown
  column: DataTableColumn<T>
}
export interface TableToolbarSlot<T> {
  rows: T[]
  total: number | undefined
  selection: RowKey[]
}
export interface DataTableSlots<T extends object> {
  [name: `cell-${string}`]: ((context: TableCellSlot<T>) => VNodeChild) | undefined
  cell?: (context: TableCellSlot<T>) => VNodeChild
  actions?: (context: { row: T; index: number }) => VNodeChild
  toolbar?: (context: TableToolbarSlot<T>) => VNodeChild
  footer?: (context: { rows: T[]; total: number | undefined; page: number }) => VNodeChild
  error?: (context: { error: string; retry: () => void }) => VNodeChild
  empty?: () => VNodeChild
  initial?: () => VNodeChild
  loading?: () => VNodeChild
  refreshing?: () => VNodeChild
}
export interface SearchFilterSlot {
  filters: TableFilters
  disabled: boolean | undefined
  update: (filters: TableFilters) => void
}
export interface SearchTableSlots<T extends object> extends DataTableSlots<T> {
  search?: (context: {
    query: string
    filters: TableFilters
    submit: (query: string, filters: TableFilters) => void
    update: (query: string) => void
  }) => VNodeChild
  filter?: (context: SearchFilterSlot) => VNodeChild
  advanced?: (context: SearchFilterSlot) => VNodeChild
  'search-actions'?: (context: {
    submit: () => void
    clear: () => void
    reset: () => void
    disabled: boolean | undefined
  }) => VNodeChild
  'toolbar-actions'?: () => VNodeChild
  'toolbar-filters'?: () => VNodeChild
}

export interface PaginationConfig {
  page?: number
  pageSize?: number
  itemCount?: number
  pageCount?: number
  pageSizes?: number[]
  showSizePicker?: boolean
  disabled?: boolean
  onChange?: (page: number) => void
  onUpdatePage?: (page: number) => void
  onUpdatePageSize?: (pageSize: number) => void
}

export interface DataTableProps<T extends object> {
  rows?: T[]
  columns: DataTableColumns<T>
  rowKey?: RowKeyGetter<T> | keyof T
  rowProps?: RowProps<T>
  mode?: PaginationMode
  total?: number
  page?: number
  pageSize?: number
  pagination?: boolean | PaginationConfig
  sort?: TableSort
  filters?: TableFilters
  selection?: RowKey[]
  loading?: boolean
  error?: string | null
  initialized?: boolean
  disabled?: boolean
  scrollX?: number | string
  maxHeight?: number | string
  size?: 'small' | 'medium' | 'large'
  bordered?: boolean
  emptyText?: string
  label?: string
}

export interface SelectionMeta<T> {
  action: 'check' | 'uncheck' | 'checkAll' | 'uncheckAll'
  row?: T
}

export type RowAction<T> = {
  key: RowKey
  label: string
  onClick?: (row: T, event: MouseEvent) => void
  disabled?: boolean | ((row: T) => boolean)
  loading?: boolean
  destructive?: boolean
}

export function positiveInteger(value: number | undefined, fallback: number): number {
  return Number.isSafeInteger(value) && (value as number) > 0 ? (value as number) : fallback
}
export function lastPage(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(Math.max(0, total) / positiveInteger(pageSize, 20)))
}
export function boundedPage(page: number | undefined, total: number, pageSize: number): number {
  return Math.min(positiveInteger(page, 1), lastPage(total, pageSize))
}
export function fieldValue<T extends object>(
  row: T,
  key: keyof T | ColumnKey | undefined,
): unknown {
  if (key === undefined) return undefined
  return String(key)
    .split('.')
    .reduce<unknown>(
      (value, segment) =>
        value !== null && typeof value === 'object'
          ? (value as Record<string, unknown>)[segment]
          : undefined,
      row,
    )
}
export function columnId<T extends object>(column: DataTableColumn<T>, index: number): string {
  return String(column.key ?? (column.type === 'selection' ? '__selection' : `column-${index}`))
}

/** Only mode=local declares that the input is a complete collection. Never mutate rows. */
export function localRows<T extends object>(
  rows: T[],
  columns: DataTableColumns<T>,
  sort: TableSort,
  filters: TableFilters,
): T[] {
  let result = rows.filter((row) =>
    columns.every((column) => {
      if (!column.filter) return true
      const values = filters[String(column.key)]
      if (values === undefined || (Array.isArray(values) && values.length === 0)) return true
      return (Array.isArray(values) ? values : [values]).some((value) =>
        typeof column.filter === 'function'
          ? column.filter(value, row)
          : Object.is(fieldValue(row, column.key), value),
      )
    }),
  )
  const priority = (key: ColumnKey) => {
    const sorter = columns.find((column) => column.key === key)?.sorter
    return typeof sorter === 'object' ? (sorter.multiple ?? 0) : 0
  }
  const sorts = (Array.isArray(sort) ? sort : sort ? [sort] : [])
    .filter((item) => item.order)
    .sort((a, b) => priority(b.columnKey) - priority(a.columnKey))
  if (sorts.length) {
    result = [...result].sort((a, b) => {
      for (const item of sorts) {
        const column = columns.find((candidate) => candidate.key === item.columnKey)
        if (!column?.sorter) continue
        const sorter = column.sorter
        const left = fieldValue(a, column.key)
        const right = fieldValue(b, column.key)
        const comparison =
          typeof sorter === 'function'
            ? sorter(a, b)
            : typeof sorter === 'object'
              ? sorter.compare(a, b)
              : left === right
                ? 0
                : left == null
                  ? -1
                  : right == null
                    ? 1
                    : typeof left === 'number' && typeof right === 'number'
                      ? left - right
                      : String(left).localeCompare(String(right))
        if (comparison) return comparison * (item.order === 'descend' ? -1 : 1)
      }
      return 0
    })
  }
  return result
}
