import type { VNodeChild } from 'vue'
export interface MenuOption {
  key?: string | number
  label?: string | (() => VNodeChild)
  icon?: () => VNodeChild
  disabled?: boolean
  show?: boolean
  type?: 'divider' | 'group'
  children?: MenuOption[]
}
