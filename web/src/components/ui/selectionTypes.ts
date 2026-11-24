import type { ComputedRef, InjectionKey, VNodeChild } from 'vue'

export type SelectionKey = string | number
export type SelectValue = SelectionKey | SelectionKey[] | null
export interface SelectOption {
  value: SelectionKey
  label?: string | (() => VNodeChild)
  disabled?: boolean
  [key: string]: unknown
}
export interface TreeOption {
  key?: SelectionKey
  label?: string | (() => VNodeChild)
  children?: TreeOption[]
  disabled?: boolean
  checkboxDisabled?: boolean
  isLeaf?: boolean
  prefix?: () => VNodeChild
  suffix?: () => VNodeChild
  [key: string]: unknown
}
export interface TreeSelectMeta {
  node: TreeOption | null
  action: 'select' | 'unselect' | 'check' | 'uncheck'
}
export const tabsContextKey: InjectionKey<{
  value: ComputedRef<SelectionKey | undefined>
}> = Symbol('ui-tabs')
export const radioContextKey: InjectionKey<{
  disabled: ComputedRef<boolean>
  readonly: ComputedRef<boolean>
}> = Symbol('ui-radio')

export function selectionKey(value: SelectionKey): string {
  return `${typeof value}:${value}`
}
export function sameSelection(a: SelectValue | undefined, b: SelectValue | undefined): boolean {
  if (Array.isArray(a) && Array.isArray(b))
    return a.length === b.length && a.every((value, index) => value === b[index])
  return a === b
}
