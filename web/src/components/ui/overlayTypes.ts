import type { ComputedRef, InjectionKey } from 'vue'
export interface SheetContext {
  close(): void
  setTitle(value: string): void
  locked: ComputedRef<boolean>
}
export const sheetContextKey: InjectionKey<SheetContext> = Symbol('knowledge-sheet')
