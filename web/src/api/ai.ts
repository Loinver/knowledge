import { http } from '@/api/client'
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type AiSuggestion = Schemas['AiSuggestionOut']

export type SuggestionKind = 'ONTOLOGY_COMPLETION' | 'MAPPING_SUGGEST' | 'DOCUMENT_FACTS'

export const aiApi = {
  suggestCompletion: (ontologyId: number) =>
    http
      .post<AiSuggestion[]>(`/ai/ontologies/${ontologyId}/suggest-completion`)
      .then((r) => r.data),
  suggestMapping: (mappingId: number, datasourceId: number) =>
    http
      .post<AiSuggestion[]>(`/ai/mappings/${mappingId}/suggest-mapping`, null, {
        params: { datasource_id: datasourceId },
      })
      .then((r) => r.data),
  extractDocument: (ontologyId: number, text: string) =>
    http
      .post<AiSuggestion[]>('/ai/documents/extract', { ontology_id: ontologyId, text })
      .then((r) => r.data),
  list: (kind?: SuggestionKind, status?: 'PENDING' | 'APPLIED' | 'DISCARDED') =>
    http.get<AiSuggestion[]>('/ai/suggestions', { params: { kind, status } }).then((r) => r.data),
  apply: (id: number) => http.post<AiSuggestion>(`/ai/suggestions/${id}/apply`).then((r) => r.data),
  discard: (id: number) =>
    http.post<AiSuggestion>(`/ai/suggestions/${id}/discard`).then((r) => r.data),
}

export function suggestionPayloadLines(item: AiSuggestion): string[] {
  const payload = item.payload as Record<string, unknown>
  return Object.entries(payload)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : String(value)}`)
}
