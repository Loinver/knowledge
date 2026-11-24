import { http } from '@/api/client'
import type { components } from '@/api/schema'

export type Namespace = components['schemas']['NamespaceOut']
export type NamespaceCreate = components['schemas']['NamespaceCreate']

export const namespacesApi = {
  list: (signal?: AbortSignal) =>
    http.get<Namespace[]>('/namespaces', { signal }).then((r) => r.data),
  create: (payload: NamespaceCreate) =>
    http.post<Namespace>('/namespaces', payload).then((r) => r.data),
  remove: (id: number) => http.delete(`/namespaces/${id}`),
}
