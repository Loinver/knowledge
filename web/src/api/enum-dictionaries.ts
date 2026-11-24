import { http } from '@/api/client'
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type EnumDictionary = Schemas['EnumDictionaryOut']
export type EnumDictionaryInput = Schemas['EnumDictionaryInput']
export type EnumReference = Schemas['EnumReferenceOut']
export type EnumSort = 'name' | '-name' | 'id' | '-id'

const base = '/governance/enum-dictionaries'
const headers = (item: EnumDictionary) => ({ 'If-Match': String(item.revision) })

export const enumDictionariesApi = {
  list: (
    params: { page: number; page_size: number; q: string; sort?: EnumSort },
    signal?: AbortSignal,
  ) => http.get<Schemas['EnumDictionaryPage']>(base, { params, signal }).then((r) => r.data),
  get: (id: number, signal?: AbortSignal) =>
    http.get<EnumDictionary>(`${base}/${id}`, { signal }).then((r) => r.data),
  create: (payload: EnumDictionaryInput) =>
    http.post<EnumDictionary>(base, payload).then((r) => r.data),
  update: (item: EnumDictionary, payload: EnumDictionaryInput) =>
    http
      .put<EnumDictionary>(`${base}/${item.id}`, payload, { headers: headers(item) })
      .then((r) => r.data),
  remove: (item: EnumDictionary) => http.delete(`${base}/${item.id}`, { headers: headers(item) }),
  revisions: (id: number, signal?: AbortSignal) =>
    http.get<EnumDictionary[]>(`${base}/${id}/revisions`, { signal }).then((r) => r.data),
  references: (id: number, signal?: AbortSignal) =>
    http.get<EnumReference[]>(`${base}/${id}/references`, { signal }).then((r) => r.data),
}
