import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']

export type DomainBrief = S['DomainBrief']
export type DomainCreate = S['DomainCreate']
export type DomainDetail = S['DomainOut']
export type DomainUpdate = S['DomainUpdate']
export type DomainMember = S['DomainMemberOut']
export type PublishCheckResult = S['PublishCheckResult']

export const domainsApi = {
  list: (params?: { q?: string; page?: number; page_size?: number }, signal?: AbortSignal) =>
    http.get<DomainBrief[]>('/domains', { params, signal }).then((r) => r.data),
  create: (payload: DomainCreate) => http.post('/domains', payload).then((r) => r.data),
  /** 列表只返回 brief；编辑标签与定义需要详情。 */
  get: (id: number, signal?: AbortSignal) =>
    http.get<DomainDetail>(`/domains/${id}`, { signal }).then((r) => r.data),
  /** 更新业务域的标签与定义。发布修订号与编辑令牌分别校验，两者都要带。 */
  update: (id: number, payload: DomainUpdate) =>
    http.put<DomainDetail>(`/domains/${id}`, payload).then((r) => r.data),
  remove: (id: number) => http.delete(`/domains/${id}`).then(() => undefined),
  members: (id: number, signal?: AbortSignal) =>
    http.get<DomainMember[]>(`/domains/${id}/members`, { signal }).then((r) => r.data),
  addMember: (id: number, resourceId: number, asRef = false, ifEditMatch?: number) =>
    http
      .post<DomainMember>(`/domains/${id}/members`, {
        resource_id: resourceId,
        as_ref: asRef,
        if_edit_match: ifEditMatch,
      })
      .then((r) => r.data),
  removeMember: (domainId: number, memberId: number, ifEditMatch?: number) =>
    http.delete(`/domains/${domainId}/members/${memberId}`, {
      headers: { 'If-Edit-Match': ifEditMatch },
    }),
  publishCheck: (id: number, signal?: AbortSignal) =>
    http.get<PublishCheckResult>(`/domains/${id}/publish-check`, { signal }).then((r) => r.data),
  publish: (id: number, ifEditMatch?: number) =>
    http
      .post(`/domains/${id}/publish`, undefined, { headers: { 'If-Edit-Match': ifEditMatch } })
      .then((r) => r.data),
}
