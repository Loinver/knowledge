import type { GraphView, SemanticViewConfig, SemanticViewFields } from '@/api/graph'

export type SemanticBinding =
  | 'hierarchy_relation_iri'
  | 'measure_property_iri'
  | 'time_property_iri'
  | 'latitude_property_iri'
  | 'longitude_property_iri'

export type SemanticContext = {
  config: SemanticViewConfig
  fields: SemanticViewFields['fields']
  /** Frozen extraction namespace, distinct from the ontology resource namespace. */
  instanceNamespace?: string | null
  /** Only explicitly loaded old templates may retain the former heuristic display. */
  legacy?: boolean
  pending?: boolean
  stale?: boolean
}
export type SemanticNotice = { key: string; count?: number }

const hierarchyLayouts = new Set([
  'org_tree',
  'indent_tree',
  'equity_tree',
  'control_chain',
  'clan_tree',
  'impact',
])
const measureLayouts = new Set(['sunburst', 'treemap', 'pack'])

export function semanticBindings(layout: string): SemanticBinding[] {
  if (hierarchyLayouts.has(layout)) return ['hierarchy_relation_iri']
  if (measureLayouts.has(layout)) return ['measure_property_iri']
  if (['timeline', 'gantt'].includes(layout)) return ['time_property_iri']
  if (layout === 'geo') return ['latitude_property_iri', 'longitude_property_iri']
  return []
}

export function hasSemanticConfig(config: SemanticViewConfig): boolean {
  return [
    'hierarchy_relation_iri',
    'measure_property_iri',
    'time_property_iri',
    'latitude_property_iri',
    'longitude_property_iri',
  ].some((key) => config[key] != null)
}

export function fieldsFor(binding: SemanticBinding, fields: SemanticViewFields['fields']) {
  return fields.filter((field) => {
    if (binding === 'hierarchy_relation_iri') return field.kind === 'RELATION'
    const types =
      binding === 'time_property_iri'
        ? ['date', 'datetime', 'dateTime']
        : ['integer', 'decimal', 'float', 'double', 'number']
    return field.kind === 'PROPERTY' && types.includes(field.datatype ?? '')
  })
}

export function semanticValue(
  node: GraphView['nodes'][number],
  iri: string | null | undefined,
  fields: SemanticViewFields['fields'],
  instanceNamespace?: string | null,
): unknown {
  if (!iri) return undefined
  const applicable = fields.filter(
    (item) =>
      item.kind === 'PROPERTY' &&
      (item.type_iri === node.type_iri ||
        (instanceNamespace &&
          item.type_name &&
          `${instanceNamespace}${item.type_name}` === node.type_iri)),
  )
  const field = applicable.find((item) => item.iri === iri)
  if (!field) return undefined
  // attrs historically uses the frozen property name. No suffix/name guessing.
  if (Object.hasOwn(node.attrs, iri)) return node.attrs[iri]
  if (
    new Set(applicable.filter((item) => item.name === field.name).map((item) => item.iri)).size !==
    1
  )
    return undefined
  return node.attrs[field.name]
}

/** ISO date means UTC midnight; a timestamp must explicitly specify Z or an offset. */
export function utcTime(value: unknown): number | null {
  if (typeof value !== 'string') return null
  const match =
    /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?(Z|[+-]\d{2}:\d{2}))?$/.exec(
      value,
    )
  if (!match) return null
  const [, year, month, day, hour, minute, second, , zone] = match
  const date = new Date(`${year}-${month}-${day}T00:00:00Z`)
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value.slice(0, 10))
    return null
  if (hour !== undefined && (Number(hour) > 23 || Number(minute) > 59 || Number(second) > 59))
    return null
  if (zone && zone !== 'Z' && (Number(zone.slice(1, 3)) > 23 || Number(zone.slice(4)) > 59))
    return null
  const time = Date.parse(hour === undefined ? `${value}T00:00:00Z` : value)
  return Number.isFinite(time) ? time : null
}

export function numericValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function nodeTime(
  node: GraphView['nodes'][number],
  context: SemanticContext,
): number | null {
  if (context.legacy) {
    const value = Object.values(node.attrs).find(
      (item) => typeof item === 'string' && /^\d{4}-\d{2}-\d{2}/.test(item),
    )
    return utcTime(typeof value === 'string' ? value.slice(0, 10) : value)
  }
  return utcTime(
    semanticValue(
      node,
      context.config.time_property_iri,
      context.fields,
      context.instanceNamespace,
    ),
  )
}
