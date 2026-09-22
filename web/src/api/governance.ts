import { http } from '@/api/client'
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type Rule = Schemas['RuleOut']
export type RuleInput = Schemas['RuleCreate']
export type RuleTest = Schemas['RuleTestOut']

export const rulesApi = {
  list: (
    params: { page: number; page_size: number; q: string; source_kind?: string },
    signal?: AbortSignal,
  ) => http.get<Schemas['RulePage']>('/governance/rules', { params, signal }).then((r) => r.data),
  get: (id: number, signal?: AbortSignal) =>
    http.get<Rule>(`/governance/rules/${id}`, { signal }).then((r) => r.data),
  create: (payload: RuleInput) => http.post<Rule>('/governance/rules', payload).then((r) => r.data),
  update: (rule: Rule, payload: RuleInput) =>
    http
      .put<Rule>(`/governance/rules/${rule.id}`, payload, {
        headers: { 'If-Match': String(rule.revision) },
      })
      .then((r) => r.data),
  remove: (rule: Rule) =>
    http.delete(`/governance/rules/${rule.id}`, {
      headers: { 'If-Match': String(rule.revision) },
    }),
  test: (rule: Rule) =>
    http
      .post<RuleTest>(`/governance/rules/${rule.id}/test`, null, {
        headers: { 'If-Match': String(rule.revision) },
      })
      .then((r) => r.data),
}
