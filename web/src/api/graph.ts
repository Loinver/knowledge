import { http } from '@/api/client'
import type { components, operations } from '@/api/schema'

type Schemas = components['schemas']
export type GraphEntity = Schemas['EntityIdentityOut']
export type GraphFact = Schemas['GraphTripleOut']
export type EvidenceItem = Schemas['EvidenceTraceItem']
export type EvidenceTrace = Schemas['FactTraceOut'] | Schemas['EntityTraceOut']
export type GraphView = Schemas['GraphViewOut']

type EntityQuery =
  operations['search_entities_api_v1_extraction_entities_get']['parameters']['query']
type ViewQuery = operations['browse_graph_api_v1_extraction_graph_view_get']['parameters']['query']

export const graphApi = {
  view: (params: ViewQuery, signal: AbortSignal) =>
    http
      .get<GraphView>('/extraction/graph-view', {
        params,
        signal,
        paramsSerializer: { indexes: null },
      })
      .then((r) => r.data),
  entities: (params: EntityQuery, signal: AbortSignal) =>
    http.get<Schemas['EntityPage']>('/extraction/entities', { params, signal }).then((r) => r.data),
  detail: (iri: string, graph_revision_id: number | undefined, signal: AbortSignal) =>
    http
      .get<Schemas['EntityDetailOut']>('/extraction/entity-detail', {
        params: { iri, graph_revision_id },
        signal,
      })
      .then((r) => r.data),
  entityEvidence: (iri: string, graph_revision_id: number | undefined, signal: AbortSignal) =>
    http
      .get<Schemas['EntityTraceOut']>('/extraction/evidence/trace/entity', {
        params: { iri, graph_revision_id },
        signal,
      })
      .then((r) => r.data),
  factEvidence: (
    fact: Schemas['FactOut'],
    graph_revision_id: number | undefined,
    signal: AbortSignal,
  ) =>
    http
      .get<Schemas['FactTraceOut']>('/extraction/evidence/trace', {
        params: { ...fact, graph_revision_id },
        signal,
      })
      .then((r) => r.data),
}
