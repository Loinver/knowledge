import { validate } from 'vee-validate'

import type { FormRule, FormRules, RuleResult } from '@/components/ui/formTypes'

export function readField(model: object | undefined, path: string): unknown {
  const keys = path
    .replace(/\[(\d+)\]/g, '.$1')
    .split('.')
    .filter(Boolean)
  return keys.reduce<unknown>(
    (value, key) =>
      value != null && typeof value === 'object'
        ? (value as Record<string, unknown>)[key]
        : undefined,
    model,
  )
}
export function isEmpty(value: unknown): boolean {
  return (
    value == null ||
    (typeof value === 'string' && value.trim() === '') ||
    (Array.isArray(value) && value.length === 0)
  )
}
export function fieldRules(rules: FormRules, path: string): FormRule[] {
  const rule = rules[path]
  return !rule ? [] : Array.isArray(rule) ? rule : [rule]
}
function failed(result: RuleResult, fallback: string): string | undefined {
  if (result instanceof Error) return result.message || fallback
  if (typeof result === 'string') return result || undefined
  return result === false ? fallback : undefined
}
async function check(
  value: unknown,
  rule: FormRule,
  fallback: string,
): Promise<string | undefined> {
  const message = rule.message || fallback
  if (rule.required && isEmpty(value)) return message
  if (isEmpty(value) && !rule.required && !rule.validator) return undefined
  if (rule.type === 'number' && (typeof value !== 'number' || !Number.isFinite(value)))
    return message
  if (rule.type === 'integer' && (typeof value !== 'number' || !Number.isSafeInteger(value)))
    return message
  if (rule.type === 'boolean' && typeof value !== 'boolean') return message
  if (rule.type === 'array' && !Array.isArray(value)) return message
  if (rule.type === 'string' && typeof value !== 'string') return message
  if (
    rule.type === 'object' &&
    (value == null || typeof value !== 'object' || Array.isArray(value))
  )
    return message
  if (
    rule.type === 'email' &&
    (typeof value !== 'string' || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value))
  )
    return message
  if (rule.type === 'url') {
    try {
      new URL(String(value))
    } catch {
      return message
    }
  }
  if (rule.type === 'date' && !(value instanceof Date && Number.isFinite(value.getTime())))
    return message
  const length =
    typeof value === 'number'
      ? value
      : typeof value === 'string' || Array.isArray(value)
        ? value.length
        : undefined
  if (
    length !== undefined &&
    ((rule.min !== undefined && length < rule.min) ||
      (rule.max !== undefined && length > rule.max) ||
      (rule.len !== undefined && length !== rule.len))
  )
    return message
  if (rule.pattern && typeof value === 'string') {
    rule.pattern.lastIndex = 0
    if (!rule.pattern.test(value)) return message
  }
  if (rule.validator) {
    try {
      return failed(await rule.validator(rule, value), message)
    } catch (error) {
      return error instanceof Error ? error.message || message : message
    }
  }
  return undefined
}
export async function validateFieldValue(
  value: unknown,
  rules: FormRule[],
  fallback: string,
): Promise<string | undefined> {
  const result = await validate(
    value,
    async (current) => {
      for (const rule of rules) {
        const error = await check(current, rule, fallback)
        if (error) return error
      }
      return true
    },
    { bails: true },
  )
  return result.errors[0]
}
