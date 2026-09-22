import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']
export type Clause = S['StandardClauseOut']
export type ClauseInput = S['StandardClauseCreate']
export type ClauseUpdate = Partial<Omit<S['StandardClauseCreate'], 'standard' | 'clause_number'>>

const base = '/governance/clauses'
const headers = (item: Clause) => ({ 'If-Match': String(item.revision) })

export const clausesApi = {
  list: (params: { page: number; page_size: number; q: string }, signal?: AbortSignal) =>
    http.get<S['StandardClausePage']>(base, { params, signal }).then((r) => r.data),
  get: (id: number, signal?: AbortSignal) =>
    http.get<Clause>(`${base}/${id}`, { signal }).then((r) => r.data),
  create: (payload: ClauseInput) => http.post<Clause>(base, payload).then((r) => r.data),
  update: (item: Clause, payload: ClauseUpdate) =>
    http.put<Clause>(`${base}/${item.id}`, payload, { headers: headers(item) }).then((r) => r.data),
  remove: (item: Clause) => http.delete(`${base}/${item.id}`, { headers: headers(item) }),
}
