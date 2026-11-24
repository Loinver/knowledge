import type { ComputedRef, InjectionKey, Ref } from 'vue'

export type RuleResult = boolean | string | Error | void
export interface FormRule<T = unknown> {
  required?: boolean
  type?: 'string' | 'number' | 'integer' | 'boolean' | 'array' | 'object' | 'email' | 'url' | 'date'
  min?: number
  max?: number
  len?: number
  pattern?: RegExp
  message?: string
  trigger?: string | string[]
  validator?(rule: FormRule<T>, value: T): RuleResult | Promise<RuleResult>
}
export type FormRules = Record<string, FormRule | FormRule[]>
export interface FormInst {
  validate(
    callback?: (errors: Record<string, string> | undefined) => void,
    paths?: string[],
  ): Promise<void>
  restoreValidation(): void
}
export interface FormContext {
  disabled: ComputedRef<boolean>
  readonly: ComputedRef<boolean>
  errors: Ref<Record<string, string>>
  required(path: string): boolean
  register(path: string, element: () => HTMLElement | null): () => void
  validateField(path: string, trigger?: string): Promise<void>
}
export interface FieldContext {
  id: string
  labelId?: string
  descriptionId: ComputedRef<string | undefined>
  invalid: ComputedRef<boolean>
  required: ComputedRef<boolean>
  disabled: ComputedRef<boolean>
  readonly: ComputedRef<boolean>
  validate(trigger?: string): void
}
export const formContextKey: InjectionKey<FormContext> = Symbol('knowledge-form')
export const fieldContextKey: InjectionKey<FieldContext> = Symbol('knowledge-field')
