import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']

export type DomainBrief = S['DomainBrief']
export type DomainCreate = S['DomainCreate']
export type DomainMember = S['DomainMemberOut']
export type PublishCheckResult = S['PublishCheckResult']

export const domainsApi = {
  list: (params?: { q?: string; page?: number; page_size?: number }, signal?: AbortSignal) =>
    http.get<DomainBrief[]>('/domains', { params, signal }).then((r) => r.data),
  create: (payload: DomainCreate) => http.post('/domains', payload).then((r) => r.data),
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
