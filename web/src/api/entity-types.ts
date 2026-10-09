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
export type EntityTypeStats = S['EntityTypeStatsOut']
export type EntityTypeUsages = S['EntityTypeUsagesOut']
export type TypeRelationUsage = S['TypeRelationUsageOut']
export type TypeRuleUsage = S['TypeRuleUsageOut']
export type TypeDomainUsage = S['TypeDomainUsageOut']
export type TypeOntologyUsage = S['TypeOntologyUsageOut']
export type TypeRevision = S['TypeRevisionOut']
export type TypeValidation = S['TypeValidationOut']

export const entityTypesApi = {
  list: (
    params?: { q?: string; page?: number; page_size?: number; domain_id?: number },
    signal?: AbortSignal,
  ) => http.get<EntityTypeBrief[]>('/entity-types', { params, signal }).then((r) => r.data),
  /** 库级统计：不受分页影响，统计条用它而不是拿当前页去数。 */
  stats: (signal?: AbortSignal) =>
    http.get<EntityTypeStats>('/entity-types/stats', { signal }).then((r) => r.data),
  /** 详情页三个页签的数据：关联关系 / 规则 / 引用与版本。 */
  usages: (id: number, signal?: AbortSignal) =>
    http.get<EntityTypeUsages>(`/entity-types/${id}/usages`, { signal }).then((r) => r.data),
  get: (id: number, signal?: AbortSignal) =>
    http.get<EntityType>(`/entity-types/${id}`, { signal }).then((r) => r.data),
  create: (payload: EntityTypeCreate) =>
    http.post<EntityType>('/entity-types', payload).then((r) => r.data),
  update: (id: number, payload: EntityTypeUpdate) =>
    http.put<EntityType>(`/entity-types/${id}`, payload).then((r) => r.data),
  /** 草稿态改名：重建 IRI 与子资源 IRI，同步规则引用面（B-6）。 */
  rename: (id: number, name: string) =>
    http.patch<EntityType>(`/entity-types/${id}/rename`, { name }).then((r) => r.data),
  publish: (id: number) => http.post(`/entity-types/${id}/publish`).then((r) => r.data),
  remove: (id: number) => http.delete(`/entity-types/${id}`).then(() => undefined),
}
