import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']

export type RelationTypeBrief = S['RelationTypeBrief']
export type RelationTypeDetail = S['RelationTypeOut']
export type RelationTypeCreate = S['RelationTypeCreate']
export type RelationTypeUpdate = S['RelationTypeUpdate']

export const relationsApi = {
  list: (params?: { q?: string; page?: number; page_size?: number }, signal?: AbortSignal) =>
    http.get<RelationTypeBrief[]>('/relations', { params, signal }).then((r) => r.data),
  get: (id: number, signal?: AbortSignal) =>
    http.get<RelationTypeDetail>(`/relations/${id}`, { signal }).then((r) => r.data),
  create: (payload: RelationTypeCreate) => http.post('/relations', payload).then((r) => r.data),
  update: (id: number, payload: RelationTypeUpdate) =>
    http.put<RelationTypeDetail>(`/relations/${id}`, payload).then((r) => r.data),
}
