import type { DataTypePropInput } from '@/api/entity-types'
import type { FormRules } from '@/components/ui/formTypes'

// Cardinality text stays in the draft until it has passed exact integer validation.
// Numeric bounds always stay strings, including when preparing the API payload.
export type PropertyDraft = Omit<DataTypePropInput, 'min_cardinality' | 'max_cardinality'> & {
  label_i18n: Record<string, string>
  definition_i18n: Record<string, string>
  enum_dict_id: number | null
  enum_dict_revision: number | null
  nullable: boolean
  default_value: string | null
  min_cardinality: number | string | null
  max_cardinality: number | string | null
  min_value: string | null
  max_value: string | null
  source_clause_ref: string | null
}
export interface PropertyValidationContext {
  editingName: string | null
  names: string[]
  version?: { id: number; revision: number; entries: { value: string }[] }
}

export function cardinalityValue(value: unknown): number | null | undefined {
  if (value === null) return null
  if (typeof value === 'number')
    return Number.isSafeInteger(value) && value >= 0 ? value : undefined
  if (typeof value !== 'string' || !/^[0-9]+$/.test(value) || value.trim() !== value)
    return undefined
  const integer = Number(value)
  return Number.isSafeInteger(integer) ? integer : undefined
}

function decimalParts(value: unknown, integer: boolean) {
  if (typeof value !== 'string' || value.length > 256) return undefined
  const match = /^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$/.exec(value)
  if (match?.[0] !== value) return undefined
  const unsigned = value.replace(/^[+-]/, '')
  const [whole, fraction = ''] = unsigned.split('.')
  const integral = whole.replace(/^0+/, '') || '0'
  const fractional = fraction.replace(/0+$/, '')
  if (integer && fractional) return undefined
  return {
    negative: value.startsWith('-') && (integral !== '0' || fractional !== ''),
    integral,
    fractional,
  }
}

// Compare digit sequences rather than binary floats (e.g. 9007199254740993 or 0.1...1).
function compareDecimal(left: NonNullable<ReturnType<typeof decimalParts>>, right: typeof left) {
  if (left.negative !== right.negative) return left.negative ? -1 : 1
  const width = Math.max(left.fractional.length, right.fractional.length)
  const a = left.fractional.padEnd(width, '0')
  const b = right.fractional.padEnd(width, '0')
  const absolute =
    Math.sign(left.integral.length - right.integral.length) ||
    (left.integral < right.integral ? -1 : left.integral > right.integral ? 1 : 0) ||
    (a < b ? -1 : a > b ? 1 : 0)
  return left.negative ? -absolute : absolute
}

// Match app.iri.is_valid_any_uri: URI references stay lexical, relative and Unicode.
function isValidAnyUri(value: string): boolean {
  if (
    /[\p{White_Space}<>"{}|\\^`]/u.test(value) ||
    Array.from(value).some((char) => char.codePointAt(0)! <= 0x20 || char === '\u007f') ||
    /%(?![0-9A-Fa-f]{2})/.test(value)
  )
    return false
  const reference = value.replace(/^[A-Za-z][A-Za-z0-9+.-]*:/, '')
  if (!reference.startsWith('//')) return true
  const authority = reference.slice(2).split(/[/?#]/, 1)[0]
  // urllib.urlsplit rejects authority characters that normalize into URI delimiters.
  if (/[/?#@:]/.test(authority.replace(/[@:#?]/g, '').normalize('NFKC'))) return false
  const open = authority.includes('[')
  const close = authority.includes(']')
  if (open !== close) return false
  if (!open) return true
  const hostnameAndPort = authority.slice(authority.lastIndexOf('@') + 1)
  let hostname: string
  if (hostnameAndPort.includes('[')) {
    if (!hostnameAndPort.startsWith('[')) return false
    const end = hostnameAndPort.indexOf(']')
    if (end < 0) return false
    hostname = hostnameAndPort.slice(1, end)
    const port = hostnameAndPort.slice(end + 1)
    if (port && !port.startsWith(':')) return false
  } else hostname = hostnameAndPort.split(':', 1)[0]
  if (hostname.startsWith('v')) return /^v[0-9A-Fa-f]+\..+$/u.test(hostname)
  const [address, scope, ...extra] = hostname.split('%')
  if (scope === '' || extra.length) return false
  try {
    // Only bracketed IPv6 syntax is parsed, never the original URI or its scheme/port.
    // Python also accepts scope IDs, which the browser URL parser does not support.
    new URL(`http://[${address}]/`)
    return true
  } catch {
    return false
  }
}

export function propertyErrors(input: PropertyDraft, context: PropertyValidationContext) {
  const errors: Record<string, string> = {}
  const pattern = context.editingName === null ? /^[A-Z][A-Za-z0-9]*$/ : /^[A-Za-z][A-Za-z0-9_]*$/
  if (
    !input.name ||
    input.name.length > 128 ||
    input.name.trim() !== input.name ||
    !pattern.test(input.name) ||
    (context.editingName !== null && input.name !== context.editingName)
  )
    errors.name = 'entityProps.invalid'
  else if (context.names.some((name) => name === input.name && name !== context.editingName))
    errors.name = 'entityProps.duplicate'
  if (!input.label_i18n['zh-CN']?.trim()) errors['label_i18n.zh-CN'] = 'entityProps.invalid'
  if (
    !['string', 'integer', 'decimal', 'boolean', 'date', 'anyURI', 'enum'].includes(input.datatype)
  )
    errors.datatype = 'entityProps.invalidDatatype'
  if (typeof input.nullable !== 'boolean') errors.nullable = 'entityProps.invalidNullable'
  if (input.default_value != null && typeof input.default_value !== 'string')
    errors.default_value = 'entityProps.stringDefault'
  else if (
    input.datatype === 'anyURI' &&
    input.default_value != null &&
    !isValidAnyUri(input.default_value)
  )
    errors.default_value = 'entityProps.invalidUriDefault'
  if (input.datatype === 'enum') {
    if (!Number.isSafeInteger(input.enum_dict_id) || (input.enum_dict_id ?? 0) <= 0)
      errors.enum_dict_id = 'entityProps.chooseVersion'
    if (
      !context.version ||
      context.version.id !== input.enum_dict_id ||
      context.version.revision !== input.enum_dict_revision ||
      !Number.isSafeInteger(input.enum_dict_revision) ||
      (input.enum_dict_revision ?? 0) <= 0
    )
      errors.enum_dict_revision = 'entityProps.chooseVersion'
    else if (
      input.default_value != null &&
      !context.version.entries.some((entry) => entry.value === input.default_value)
    )
      errors.default_value = 'entityProps.invalidDefault'
  }
  const min = cardinalityValue(input.min_cardinality)
  const max = cardinalityValue(input.max_cardinality)
  if (min === undefined) errors.min_cardinality = 'entityProps.invalidCardinality'
  if (max === undefined) errors.max_cardinality = 'entityProps.invalidCardinality'
  else if (min !== undefined && max !== null && max < Math.max(min ?? 0, input.nullable ? 0 : 1))
    errors.max_cardinality = 'entityProps.cardinalityOrder'

  const numeric = input.datatype === 'integer' || input.datatype === 'decimal'
  const bounds = ['min_value', 'max_value'] as const
  for (const path of bounds) {
    if (input[path] == null) continue
    if (!numeric) errors[path] = 'entityProps.rangeDatatype'
    else if (!decimalParts(input[path], input.datatype === 'integer'))
      errors[path] = 'entityProps.invalidNumericBound'
  }
  const lower = decimalParts(input.min_value, input.datatype === 'integer')
  const upper = decimalParts(input.max_value, input.datatype === 'integer')
  if (numeric && lower && upper && compareDecimal(lower, upper) > 0)
    errors.max_value = 'entityProps.numericOrder'
  return errors
}

export function propertyRules(
  input: PropertyDraft,
  context: PropertyValidationContext,
  translate: (key: string) => string,
): FormRules {
  const errors = propertyErrors(input, context)
  return Object.fromEntries(
    [
      'name',
      'label_i18n.zh-CN',
      'datatype',
      'enum_dict_id',
      'enum_dict_revision',
      'default_value',
      'nullable',
      'min_cardinality',
      'max_cardinality',
      'min_value',
      'max_value',
    ].map((path) => [
      path,
      {
        required:
          ['name', 'label_i18n.zh-CN', 'datatype'].includes(path) ||
          (input.datatype === 'enum' && ['enum_dict_id', 'enum_dict_revision'].includes(path)),
        message: translate(errors[path] ?? 'common.required'),
        trigger: ['input', 'blur', 'change'],
        validator: () => {
          const error = propertyErrors(input, context)[path]
          return error ? translate(error) : true
        },
      },
    ]),
  )
}

export function propertyPayload(input: PropertyDraft): DataTypePropInput {
  const min = cardinalityValue(input.min_cardinality)
  const max = cardinalityValue(input.max_cardinality)
  if (min === undefined || max === undefined) throw new Error('INVALID_PROPERTY_CARDINALITY')
  return { ...input, min_cardinality: min, max_cardinality: max }
}
