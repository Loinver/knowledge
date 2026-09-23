import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']

export type ResourceKind = S['ResourceKind']
export type ResourceStatus = S['ResourceStatus']
export type DataTypeProp = S['DataTypePropOut']
export type DataTypePropInput = S['DataTypePropCreate']
export type EntityType = S['EntityTypeOut']
export type EntityTypeBrief = S['EntityTypeBrief']
export type EntityTypeCreate = S['EntityTypeCreate']
export type EntityTypeUpdate = S['EntityTypeUpdate']

export const entityTypesApi = {
  list: (params?: { q?: string; page?: number; page_size?: number }, signal?: AbortSignal) =>
    http.get<EntityTypeBrief[]>('/entity-types', { params, signal }).then((r) => r.data),
  get: (id: number, signal?: AbortSignal) =>
    http.get<EntityType>(`/entity-types/${id}`, { signal }).then((r) => r.data),
  create: (payload: EntityTypeCreate) =>
    http.post<EntityType>('/entity-types', payload).then((r) => r.data),
  update: (id: number, payload: EntityTypeUpdate) =>
    http.put<EntityType>(`/entity-types/${id}`, payload).then((r) => r.data),
  publish: (id: number) => http.post(`/entity-types/${id}/publish`).then((r) => r.data),
}
