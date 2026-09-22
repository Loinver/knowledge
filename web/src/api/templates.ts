import { http } from '@/api/client'
import type { components } from '@/api/schema'

type S = components['schemas']
export type Template = S['TemplateOut']
export type TemplateInput = S['TemplateCreate']
export type TemplateResource = S['TemplateResourceOption']
export type TemplateOntology = S['OntologyBrief']

const base = '/governance/templates'
const headers = (item: Template) => ({ 'If-Match': String(item.revision) })
export const templatesApi = {
  list: (params: { q: string; page: number; builtin?: boolean }, signal?: AbortSignal) =>
    http
      .get<S['TemplatePage']>(base, { params: { ...params, page_size: 20 }, signal })
      .then((r) => r.data),
  get: (id: number) => http.get<Template>(`${base}/${id}`).then((r) => r.data),
  create: (payload: TemplateInput) => http.post<Template>(base, payload).then((r) => r.data),
  update: (item: Template, payload: TemplateInput) =>
    http
      .put<Template>(`${base}/${item.id}`, payload, { headers: headers(item) })
      .then((r) => r.data),
  remove: (item: Template) => http.delete(`${base}/${item.id}`, { headers: headers(item) }),
  copy: (item: Template, payload: S['TemplateMetadata']) =>
    http
      .post<Template>(`${base}/${item.id}/copy`, payload, { headers: headers(item) })
      .then((r) => r.data),
  fromOntology: (payload: S['TemplateFromOntology']) =>
    http.post<Template>(`${base}/from-ontology`, payload).then((r) => r.data),
  instantiate: (item: Template, payload: S['TemplateInstantiate']) =>
    http
      .post<S['OntologyOut']>(`${base}/${item.id}/instantiate`, payload, { headers: headers(item) })
      .then((r) => r.data),
  resources: async (signal: AbortSignal) => {
    const items: TemplateResource[] = []
    for (let page = 1; ; page++) {
      const { data } = await http.get<S['TemplateResourcePage']>(`${base}/resources`, {
        params: { page, page_size: 200 },
        signal,
      })
      items.push(...data.items)
      if (items.length >= data.total || !data.items.length) return items
    }
  },
  ontologies: async (signal: AbortSignal) => {
    const items: TemplateOntology[] = []
    for (let page = 1; ; page++) {
      const { data } = await http.get<TemplateOntology[]>('/ontologies', {
        params: { page, page_size: 200 },
        signal,
      })
      items.push(...data)
      if (data.length < 200) return items
    }
  },
}
