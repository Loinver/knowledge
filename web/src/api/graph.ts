import { http } from '@/api/client'
import type { components, operations } from '@/api/schema'

type Schemas = components['schemas']
export type GraphEntity = Schemas['EntityIdentityOut']
export type GraphFact = Schemas['GraphTripleOut']
export type EvidenceItem = Schemas['EvidenceTraceItem']
export type EvidenceTrace = Schemas['FactTraceOut'] | Schemas['EntityTraceOut']
export type GraphView = Schemas['GraphViewOut']
export type GraphDiff = Schemas['GraphDiffOut']
export type GraphPath = Schemas['PathOut']
export type GraphRecommendations = Schemas['GraphRecommendationOut']
export type ReverseTrace = Schemas['ReverseTraceOut']
export type EntityFusion = Schemas['EntityFusionOut']
export type ViewTemplate = Schemas['ViewTemplateOut']
export type ViewTemplatePage = Schemas['ViewTemplatePage']

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
  entityFusion: (iri: string, graph_revision_id: number | undefined, signal: AbortSignal) =>
    http
      .get<EntityFusion>('/extraction/evidence/fusion', {
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
  diff: (baseId: number, targetId: number, signal: AbortSignal) =>
    http
      .get<GraphDiff>(`/extraction/graph/${baseId}/diff/${targetId}`, { signal })
      .then((r) => r.data),
  path: (
    graphRevisionId: number,
    params: { from: string; to: string; max_hops: number; include_derived: boolean },
    signal: AbortSignal,
  ) =>
    http
      .get<GraphPath>(`/extraction/graph/${graphRevisionId}/path`, { params, signal })
      .then((r) => r.data),
  recommendations: (graphRevisionId: number, signal: AbortSignal) =>
    http
      .get<GraphRecommendations>(`/extraction/graph/${graphRevisionId}/layout-recommendations`, {
        signal,
      })
      .then((r) => r.data),
  reverseTrace: (
    params: { source_id: number; table: string; row_key: string },
    graphRevisionId: number | undefined,
    signal: AbortSignal,
  ) =>
    http
      .get<ReverseTrace>('/extraction/evidence/trace/reverse', {
        params: { ...params, graph_revision_id: graphRevisionId },
        signal,
      })
      .then((r) => r.data),
  revisions: (signal: AbortSignal) =>
    http
      .get<{ items: Schemas['GraphRevisionOut'][] }>('/extraction/graph/revisions', { signal })
      .then((r) => r.data),
  runQuarantine: (runId: number, signal: AbortSignal) =>
    http
      .get<Schemas['QuarantineOut'][]>(`/extraction/runs/${runId}/quarantine`, { signal })
      .then((r) => r.data),
}

export const viewTemplateApi = {
  list: (ontologyId: number | undefined, signal: AbortSignal) =>
    http
      .get<ViewTemplatePage>('/view-templates', {
        params: { ontology_id: ontologyId },
        signal,
      })
      .then((r) => r.data),
  create: (payload: {
    name_i18n: Record<string, string>
    layout_id: string
    config: Record<string, unknown>
    ontology_id: number
    ontology_revision: number
  }) => http.post<ViewTemplate>('/view-templates', payload).then((r) => r.data),
  remove: (id: number) => http.delete(`/view-templates/${id}`).then((r) => r.data),
}
