import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']

export type RelationTypeBrief = S['RelationTypeBrief']
export type RelationTypeDetail = S['RelationTypeOut']
export type RelationTypeCreate = S['RelationTypeCreate']
export type RelationTypeUpdate = S['RelationTypeUpdate']
export type RelationTypeUsages = S['RelationTypeUsagesOut']
export type TypeRuleUsage = S['TypeRuleUsageOut']
export type TypeDomainUsage = S['TypeDomainUsageOut']
export type TypeOntologyUsage = S['TypeOntologyUsageOut']
export type TypeRevision = S['TypeRevisionOut']
export type TypeValidation = S['TypeValidationOut']

export const relationsApi = {
  list: (params?: { q?: string; page?: number; page_size?: number }, signal?: AbortSignal) =>
    http.get<RelationTypeBrief[]>('/relations', { params, signal }).then((r) => r.data),
  /** 详情页两个页签的数据：规则 / 引用与版本（端点与基数由 get 返回）。 */
  usages: (id: number, signal?: AbortSignal) =>
    http.get<RelationTypeUsages>(`/relations/${id}/usages`, { signal }).then((r) => r.data),
  get: (id: number, signal?: AbortSignal) =>
    http.get<RelationTypeDetail>(`/relations/${id}`, { signal }).then((r) => r.data),
  create: (payload: RelationTypeCreate) => http.post('/relations', payload).then((r) => r.data),
  update: (id: number, payload: RelationTypeUpdate) =>
    http.put<RelationTypeDetail>(`/relations/${id}`, payload).then((r) => r.data),
  /** 草稿态改名：重建 IRI，同步规则引用面（B-6）。 */
  rename: (id: number, name: string) =>
    http.patch<RelationTypeDetail>(`/relations/${id}/rename`, { name }).then((r) => r.data),

  /** 发布即冻结不可变版本；草稿态的关系类型必须发布后才能被本体装配引用。 */
  publish: (id: number) =>
    http
      .post<{ revision: number; checksum: string }>(`/relations/${id}/publish`)
      .then((r) => r.data),
}
