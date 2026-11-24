import type { InjectionKey } from 'vue'
import { inject } from 'vue'

export type FeedbackText = string | (() => string)
export type FeedbackKind = 'success' | 'error' | 'warning' | 'info'
export interface MessageHandle {
  destroy(): void
}
export interface MessageApi {
  success(text: FeedbackText, options?: { duration?: number }): MessageHandle
  error(text: FeedbackText, options?: { duration?: number }): MessageHandle
  warning(text: FeedbackText, options?: { duration?: number }): MessageHandle
  info(text: FeedbackText, options?: { duration?: number }): MessageHandle
}
export interface DialogOptions {
  restoreFocusTo?: HTMLElement | null
  title: FeedbackText
  content?: FeedbackText
  positiveText?: FeedbackText
  negativeText?: FeedbackText
  onPositiveClick?: () => unknown | Promise<unknown>
  onNegativeClick?: () => unknown | Promise<unknown>
}
export interface DialogApi {
  warning(options: DialogOptions): MessageHandle
}
export const messageKey: InjectionKey<MessageApi> = Symbol('knowledge-message')
export const dialogKey: InjectionKey<DialogApi> = Symbol('knowledge-dialog')
export function useMessage(): MessageApi {
  const api = inject(messageKey)
  if (!api) throw new Error('UiFeedbackProvider is required')
  return api
}
export function useDialog(): DialogApi {
  const api = inject(dialogKey)
  if (!api) throw new Error('UiFeedbackProvider is required')
  return api
}
