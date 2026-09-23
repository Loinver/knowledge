import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']

export type Mapping = S['MappingBrief']
export type MappingCreate = S['MappingCreate']
export type MappingRevision = S['MappingRevisionOut']
export type MappingRevisionCreate = S['MappingRevisionCreate']
export type MappingPreview = S['MappingPreviewResult']
export type SaveDraftRequest = S['SaveDraftRequest']
export type PublishRequest = S['PublishRequest']

export const mappingsApi = {
  list: (signal?: AbortSignal) =>
    http
      .get<Mapping[]>('/mappings', { params: { page: 1, page_size: 200 }, signal })
      .then((r) => r.data),
  create: (payload: MappingCreate) => http.post<Mapping>('/mappings', payload).then((r) => r.data),
  draft: (id: number, signal?: AbortSignal) =>
    http.get<MappingRevision | null>(`/mappings/${id}/draft`, { signal }).then((r) => r.data),
  published: (id: number, signal?: AbortSignal) =>
    http.get<MappingRevision | null>(`/mappings/${id}/published`, { signal }).then((r) => r.data),
  saveDraft: (id: number, payload: SaveDraftRequest) =>
    http.put<MappingRevision>(`/mappings/${id}/draft`, payload).then((r) => r.data),
  compile: (
    id: number,
    payload: { datasource_id: number; limit: number; use_draft: boolean },
    signal?: AbortSignal,
  ) =>
    http.post<MappingPreview>(`/mappings/${id}/compile`, payload, { signal }).then((r) => r.data),
  publish: (id: number, payload: PublishRequest) =>
    http.post<MappingRevision>(`/mappings/${id}/publish`, payload).then((r) => r.data),
}
