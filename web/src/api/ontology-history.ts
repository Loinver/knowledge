import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']
export type RevisionContents = S['OntologyRevisionContents']
export type FrozenResource = S['OntologyHistoryResourceOut']
export type FrozenRule = S['OntologyHistoryRuleOut']

function base(ontologyId: number, revision: number) {
  return `/ontologies/${ontologyId}/revisions/${revision}`
}

export const ontologyHistoryApi = {
  contents: (ontologyId: number, revision: number, signal?: AbortSignal) =>
    http
      .get<RevisionContents>(`${base(ontologyId, revision)}/contents`, { signal })
      .then((r) => r.data),
  resource: (ontologyId: number, revision: number, id: number, signal?: AbortSignal) =>
    http
      .get<FrozenResource>(`${base(ontologyId, revision)}/resources/${id}`, { signal })
      .then((r) => r.data),
  rule: (ontologyId: number, revision: number, id: number, signal?: AbortSignal) =>
    http
      .get<FrozenRule>(`${base(ontologyId, revision)}/rules/${id}`, { signal })
      .then((r) => r.data),
}
