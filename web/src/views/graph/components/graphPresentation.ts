import type { GraphView, SemanticViewFields } from '@/api/graph'

export const iriName = (iri: string) => iri.split(/[/#]/).filter(Boolean).at(-1) || iri

/** Resolve labels only inside the result set's frozen ontology version. */
export function relationLabels(
  graph: GraphView | null,
  catalog: SemanticViewFields | null,
  locale: string,
  untranslated: string,
): Record<string, string> {
  const labels: Record<string, string> = Object.create(null)
  if (
    !graph ||
    !catalog ||
    graph.ontology_id !== catalog.ontology_id ||
    graph.ontology_revision !== catalog.ontology_revision
  )
    return labels
  const fields = catalog.fields.filter((field) => field.kind === 'RELATION')
  const byIri = new Map(fields.map((field) => [field.iri, field]))
  const names = new Map<string, Set<string>>()
  for (const field of fields) {
    const iris = names.get(field.name) ?? new Set<string>()
    iris.add(field.iri)
    names.set(field.name, iris)
  }
  for (const predicate of new Set(graph.edges.map((edge) => edge.predicate))) {
    const field =
      byIri.get(predicate) ??
      fields.find(
        (candidate) =>
          (candidate.name === predicate ||
            (graph.instance_namespace &&
              `${graph.instance_namespace}${candidate.name}` === predicate)) &&
          names.get(candidate.name)?.size === 1,
      )
    if (field)
      labels[predicate] = field.label_i18n?.[locale]?.trim() || `${field.name} · ${untranslated}`
  }
  return labels
}

const glyphs = {
  person: 'M0-1a3 3 0 1 0 0-6 3 3 0 0 0 0 6 M-6 7V5a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2',
  department: 'M-3-7h6v5h-6Z M0-2v4 M-6 2H6 M-6 2v3 M6 2v3 M-8 5h4v3h-4Z M4 5h4v3H4Z',
  company: 'M-6 8V-7H4V8 M4-1h4v9 M-8 8H9 M-3-4h1 M1-4h1 M-3 0h1 M1 0h1 M-2 8V4h3v4',
  project: 'M-8-4h6l2 2h8V7H-8Z M-8-4V-7h6l2 3 M-4 2h8',
  document: 'M-5-8h7l4 4V8H-5Z M2-8v5h4 M-2 0h5 M-2 3h5 M-2 6h3',
  entity: 'M0-8l7 4v8l-7 4-7-4v-8Z M-7-4l7 4 7-4 M0 0v8',
}
const palette = ['#526bc2', '#387f97', '#8a68b3', '#387e6b', '#b17a3c', '#61738d']

/** Familiar machine names get recognizable pictograms; custom types keep a generic entity symbol. */
export function nodeAppearance(iri: string) {
  const name = iriName(iri).toLowerCase()
  if (['person', 'employee', 'staff', 'member', 'user'].includes(name))
    return { icon: glyphs.person, color: palette[0] }
  if (['department', 'team', 'division'].includes(name))
    return { icon: glyphs.department, color: palette[2] }
  if (['company', 'enterprise', 'organization', 'customer', 'supplier'].includes(name))
    return { icon: glyphs.company, color: palette[1] }
  if (['project', 'product', 'system'].includes(name))
    return { icon: glyphs.project, color: palette[3] }
  if (['contract', 'agreement', 'document'].includes(name))
    return { icon: glyphs.document, color: palette[4] }
  const hash = [...iri].reduce((value, char) => (value * 31 + char.codePointAt(0)!) >>> 0, 0)
  return { icon: glyphs.entity, color: palette[hash % palette.length] }
}
