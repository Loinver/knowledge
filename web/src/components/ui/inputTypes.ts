import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'vue'

export interface InputInst {
  focus(options?: FocusOptions): void
  blur(): void
  select(): void
  clear(): void
  activate(): void
  deactivate(): void
  scrollTo(options: ScrollToOptions): void
  wrapperElRef: HTMLElement | null
  inputElRef: HTMLInputElement | null
  textareaElRef: HTMLTextAreaElement | null
  isCompositing: boolean
}
export type InputValue = string | number | null
export type InputProps = InputHTMLAttributes & TextareaHTMLAttributes
export interface AutosizeOptions {
  minRows?: number
  maxRows?: number
}

export function parseNumberInput(
  text: string,
  min?: number,
  max?: number,
  precision?: number,
): number | null {
  if (!text.trim()) return null
  const value = Number(text)
  if (!Number.isFinite(value)) return null
  const rounded =
    precision === undefined ? value : Number(value.toFixed(Math.min(100, Math.max(0, precision))))
  return Math.min(max ?? Infinity, Math.max(min ?? -Infinity, rounded))
}

/** Native date fields use local calendar time; the public model remains epoch milliseconds. */
export function formatDateInput(value: number | null | undefined, datetime: boolean): string {
  if (value == null || !Number.isFinite(value)) return ''
  const date = new Date(value)
  const pad = (part: number) => String(part).padStart(2, '0')
  const day = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
  return datetime
    ? `${day}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
    : day
}
export function parseDateInput(text: string): number | null {
  if (!text) return null
  const value = new Date(text.includes('T') ? text : `${text}T00:00:00`).getTime()
  return Number.isFinite(value) ? value : null
}
